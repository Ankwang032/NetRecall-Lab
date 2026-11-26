"""실습 웹 터미널 API (설계서 §D-8, 조건은 backend/services/lab_terminal.py).

흐름: POST /lab-runs/{id}/terminal-tickets {"node": "r1", "shell": "vtysh"} → {"ticket": ...} (30초, 1회용)
     → WebSocket /lab-runs/{id}/terminal?ticket=...
메시지: 브라우저 → 서버는 텍스트 JSON {"type": "input", "data": "..."} · {"type": "resize", "cols": 80, "rows": 24}
       서버 → 브라우저는 바이너리(터미널 출력)와, 닫기 직전 텍스트 JSON {"type": "closed", "message": "..."}
자기 터미널에서 `docker exec`로 접속하는 방법은 그대로 쓸 수 있다. 둘 다 같은 노드에 붙는다.
"""
from __future__ import annotations

import asyncio
import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.api.deps import get_lab_runtime, get_session
from backend.core.time import to_kst
from backend.models import LabRun
from backend.models.concept import utcnow
from backend.services import lab_service as labs
from backend.services.lab_terminal import MAX_TERMINALS, SHELLS, TerminalProcess, same_origin
from integrations.labs.base import LabRuntime

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]
RuntimeDep = Annotated[LabRuntime, Depends(get_lab_runtime)]
POLICY_VIOLATION = 1008  # WebSocket 닫기 코드: Origin·발급표·실행 상태가 맞지 않음
TRY_AGAIN_LATER = 1013


class TicketRequest(BaseModel):
    node: str
    shell: Literal["sh", "vtysh"] | None = None  # 없으면 노드 종류의 기본 (Linux sh, 라우터 vtysh)


class TicketResponse(BaseModel):
    ticket: str
    node: str
    shell: str


@router.post("/lab-runs/{run_id}/terminal-tickets", status_code=201)
def issue_ticket(run_id: int, body: TicketRequest, request: Request, session: SessionDep,
                 runtime: RuntimeDep) -> TicketResponse:
    try:
        run = labs.live_run(session, runtime, run_id, utcnow())
    except labs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except labs.RunNotActive as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    kind = _node_kind(run, body.node)
    if kind is None:
        raise HTTPException(status_code=404, detail=f"이 실습에 없는 노드입니다: {body.node}")
    shell = body.shell or SHELLS[kind][0]
    if shell not in SHELLS[kind]:
        raise HTTPException(status_code=422, detail=f"{body.node}에서는 {', '.join(SHELLS[kind])}만 열 수 있습니다")
    ticket = request.app.state.terminal_tickets.issue(run_id, body.node, shell)
    return TicketResponse(ticket=ticket, node=body.node, shell=shell)


@router.websocket("/lab-runs/{run_id}/terminal")
async def terminal(websocket: WebSocket, run_id: int, ticket: str = "") -> None:
    state = websocket.app.state
    if not same_origin(websocket.headers):
        await websocket.close(code=POLICY_VIOLATION)
        return
    t = state.terminal_tickets.take(ticket, run_id)
    if t is None:
        await websocket.close(code=POLICY_VIOLATION)
        return
    if state.terminal_count >= MAX_TERMINALS:
        await websocket.close(code=TRY_AGAIN_LATER)
        return

    # 시간 제한 정리는 docker를 부를 수 있어 스레드에서 한다. DB 세션은 확인하는 동안만 연다
    # (터미널이 열려 있는 내내 SQLite 읽기 트랜잭션을 잡고 있으면 검증·끝내기가 쓰지 못한다)
    def check() -> float:
        with state.session_factory() as session:
            run = labs.live_run(session, state.lab_runtime, run_id, utcnow())
            return (to_kst(run.expires_at) - utcnow()).total_seconds()

    try:
        seconds_left = await run_in_threadpool(check)
    except labs.LabError:
        await websocket.close(code=POLICY_VIOLATION)
        return

    await websocket.accept()
    try:
        process = TerminalProcess(state.lab_runtime.terminal_argv(f"nr-{run_id}", t.node, t.shell))
    except OSError as exc:
        await _closed(websocket, f"터미널을 열지 못했습니다: {exc}")
        return
    state.terminal_count += 1
    try:
        reason = await _bridge(websocket, process, seconds_left)
        await _closed(websocket, reason)
    finally:
        state.terminal_count -= 1
        await run_in_threadpool(process.close)


async def _bridge(websocket: WebSocket, process: TerminalProcess, seconds_left: float) -> str | None:
    """PTY 출력 → 브라우저, 브라우저 입력 → PTY. 한쪽이 끝나면 닫는 이유를 돌려준다 (브라우저가 끊었으면 None)."""
    loop = asyncio.get_running_loop()
    output: asyncio.Queue[bytes] = asyncio.Queue()

    def readable() -> None:
        data = process.read()
        if not data:
            loop.remove_reader(process.fd)
        output.put_nowait(data)

    async def send() -> str | None:
        try:
            while data := await output.get():
                await websocket.send_bytes(data)
        except (WebSocketDisconnect, RuntimeError):  # 브라우저가 이미 끊었다
            return None
        return "터미널이 끝났습니다 (실습을 끝냈거나 셸에서 나왔습니다)"

    async def receive() -> str | None:
        while True:
            try:
                message = json.loads(await websocket.receive_text())
            except WebSocketDisconnect:
                return None
            except (ValueError, KeyError):  # JSON이 아니거나 바이너리
                return "알 수 없는 메시지를 받아 닫았습니다"
            if not isinstance(message, dict):
                return "알 수 없는 메시지를 받아 닫았습니다"
            if message.get("type") == "input" and isinstance(message.get("data"), str):
                try:
                    process.write(message["data"].encode()[:65536])
                except OSError:  # 프로세스가 끝났다. send()가 알린다
                    pass
            elif message.get("type") == "resize":
                cols, rows = message.get("cols"), message.get("rows")
                if isinstance(cols, int) and isinstance(rows, int) and 0 < cols <= 500 and 0 < rows <= 200:
                    process.resize(cols, rows)

    loop.add_reader(process.fd, readable)
    tasks = {asyncio.ensure_future(send()), asyncio.ensure_future(receive())}
    try:
        done, _ = await asyncio.wait(tasks, timeout=max(seconds_left, 0), return_when=asyncio.FIRST_COMPLETED)
        if not done:
            return "시간 제한이 지나 터미널을 닫았습니다"
        return done.pop().result()
    finally:
        loop.remove_reader(process.fd)
        for task in tasks:
            task.cancel()


async def _closed(websocket: WebSocket, reason: str | None) -> None:
    if reason is None:  # 브라우저가 먼저 끊었다
        return
    try:
        await websocket.send_text(json.dumps({"type": "closed", "message": reason}, ensure_ascii=False))
        await websocket.close()
    except (WebSocketDisconnect, RuntimeError):
        pass


def _node_kind(run: LabRun, node: str) -> str | None:
    return next((n.kind for n in labs.rendered_lab(run).topology.nodes if n.name == node), None)
