"""실습 웹 터미널: 노드 접속 명령을 PTY에서 실행하고, 브라우저와 바이트를 주고받는다.

설계서 §D-8의 조건을 따른다.
- 실행하는 명령은 런타임이 정한 접속 명령뿐이다(`docker exec -it <노드> sh|vtysh`). 브라우저는 키 입력만 보낸다.
- WebSocket에는 CORS가 없으므로 Origin을 검사하고, 접속마다 짧게 쓰는 1회용 발급표(ticket)를 요구한다.
  발급표는 일반 API로 받는다. 다른 사이트의 스크립트는 그 응답을 읽을 수 없다.
- 진행 중인 실행의 노드에만 연다. 실행을 끝내 노드가 지워지면 접속 명령도 끝나 터미널이 닫힌다.
"""
from __future__ import annotations

import fcntl
import os
import pty
import secrets
import signal
import struct
import subprocess
import termios
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

SHELLS = {"host": ("sh",), "router": ("vtysh", "sh")}  # 노드 종류 → 열 수 있는 셸. 앞이 기본
TICKET_SECONDS = 30
MAX_TERMINALS = 8  # 동시에 열린 터미널 (실습은 하나뿐이고 노드는 6개까지다)


@dataclass(frozen=True)
class Ticket:
    run_id: int
    node: str
    shell: str
    expires: float  # time.monotonic()


class Tickets:
    """1회용 발급표. 앱 프로세스 메모리에만 둔다 (서버를 다시 켜면 새로 받는다)."""

    def __init__(self, seconds: float = TICKET_SECONDS) -> None:
        self.seconds = seconds
        self._items: dict[str, Ticket] = {}

    def issue(self, run_id: int, node: str, shell: str) -> str:
        now = time.monotonic()
        self._items = {k: t for k, t in self._items.items() if t.expires > now}
        key = secrets.token_urlsafe(32)
        self._items[key] = Ticket(run_id, node, shell, now + self.seconds)
        return key

    def take(self, key: str, run_id: int) -> Ticket | None:
        """쓰면 없어진다. 다른 실행의 발급표나 시간이 지난 발급표는 None."""
        ticket = self._items.pop(key, None)
        if ticket is None or ticket.run_id != run_id or ticket.expires <= time.monotonic():
            return None
        return ticket


def same_origin(headers) -> bool:
    """WebSocket 요청의 Origin이 이 서버 주소인가. 포트 전달(Codespaces 등)을 거치면 X-Forwarded-Host를 본다.

    브라우저 스크립트는 WebSocket 요청에 Host·X-Forwarded-Host를 넣을 수 없다.
    """
    origin = headers.get("origin")
    if not origin:
        return False
    hosts = {headers.get("host")} | {h.strip() for h in headers.get("x-forwarded-host", "").split(",") if h.strip()}
    return urlsplit(origin).netloc in hosts


class TerminalProcess:
    """argv를 새 PTY에서 실행한다. 셸을 거치지 않는다."""

    def __init__(self, argv: list[str], cols: int = 80, rows: int = 24) -> None:
        master, slave = pty.openpty()
        _set_size(slave, cols, rows)
        try:
            self.process = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave,
                                            start_new_session=True, close_fds=True)
        except OSError:
            os.close(master)
            raise
        finally:
            os.close(slave)
        self.fd = master

    def write(self, data: bytes) -> None:
        os.write(self.fd, data)

    def read(self) -> bytes:
        """읽을 것이 없으면(프로세스가 끝나 PTY가 닫히면) b''."""
        try:
            return os.read(self.fd, 65536)
        except OSError:  # Linux는 끝난 PTY를 읽으면 EIO
            return b""

    def resize(self, cols: int, rows: int) -> None:
        _set_size(self.fd, cols, rows)
        # 제어 터미널이 없어 커널이 알려 주지 않는다. docker exec -it는 SIGWINCH를 받으면 크기를 다시 읽어 넘긴다
        try:
            os.kill(self.process.pid, signal.SIGWINCH)
        except ProcessLookupError:
            pass

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        os.close(self.fd)


def _set_size(fd: int, cols: int, rows: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
