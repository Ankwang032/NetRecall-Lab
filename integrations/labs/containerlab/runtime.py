"""Containerlab 실행기 (LabRuntime 첫 구현).

- containerlab은 고정 인자로만 부른다: `deploy -t <파일>`, `destroy --name <실습> --cleanup`. sudo 없이 돈다.
  실행하는 사용자가 clab_admins·docker 그룹에 있어야 한다.
- 노드 명령은 `docker exec`로 argv 그대로 실행한다. 셸을 거치지 않는다.
- 실습 이름은 nr-<실행 id>, 컨테이너 이름은 clab-<실습 이름>-<노드>. 남은 실습은 컨테이너 라벨
  `containerlab=<실습 이름>`으로 찾고, 이 접두사가 아닌 실습은 건드리지 않는다.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

import yaml

from ..base import ExecResult, LabRuntimeError, RenderedTopology
from .topology import RUN_NAME_PATTERN, clab_topology

NODE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9]{0,14}$")
DEPLOY_TIMEOUT = 300   # 이미지를 처음 받을 때 오래 걸린다
DESTROY_TIMEOUT = 120
EXEC_TIMEOUT = 15      # 검사 명령은 3초 안팎. 끝나지 않는 명령이 검증을 붙잡지 않게 한다
ROUTER_READY_TIMEOUT = 30
DOCKER_ERRORS = ("Error response from daemon:", "OCI runtime exec failed")  # 명령이 아니라 docker가 실패함


class ContainerlabRuntime:
    def __init__(self, work_dir: str | Path, *, containerlab: str = "containerlab", docker: str = "docker") -> None:
        self.work_dir = Path(work_dir)  # 토폴로지 파일과 Containerlab의 실습 폴더가 생기는 곳
        self.containerlab = containerlab
        self.docker = docker

    def deploy(self, run_name: str, topology: RenderedTopology) -> None:
        doc = clab_topology(run_name, topology)  # 배포 전 정적 검사. 통과하지 못하면 TopologyError
        self.work_dir.mkdir(parents=True, exist_ok=True)
        path = self._topology_file(run_name)
        path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
        try:
            self._run([self.containerlab, "deploy", "-t", str(path)], DEPLOY_TIMEOUT, "배포")
            for node in topology.nodes:
                if node.kind == "router":
                    self._prepare_router(run_name, node.name)
        except LabRuntimeError:
            try:  # 반쯤 뜬 컨테이너를 남기지 않는다
                self.destroy(run_name)
            except LabRuntimeError:
                pass
            raise

    def exec(self, run_name: str, node: str, argv: list[str]) -> ExecResult:
        _check_run_name(run_name)
        if not NODE_NAME_PATTERN.match(node):
            raise LabRuntimeError(f"노드 이름이 틀렸습니다: {node}")
        container = f"clab-{run_name}-{node}"
        try:
            p = subprocess.run([self.docker, "exec", container, *argv], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=EXEC_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise LabRuntimeError(f"{node}에서 명령이 {EXEC_TIMEOUT}초 안에 끝나지 않았습니다: {' '.join(argv)}") from None
        except OSError as exc:
            raise LabRuntimeError(f"docker를 실행하지 못했습니다: {exc}") from None
        if p.returncode != 0 and p.stderr.lstrip().startswith(DOCKER_ERRORS):
            raise LabRuntimeError(f"{node}: {p.stderr.strip()}")
        return ExecResult(p.returncode, p.stdout, p.stderr)

    def destroy(self, run_name: str) -> None:
        _check_run_name(run_name)
        if run_name in self.list_runs():  # 없는 실습을 지우면 containerlab이 오류를 낸다. 여러 번 불러도 되게 한다
            self._run([self.containerlab, "destroy", "--name", run_name, "--cleanup"], DESTROY_TIMEOUT, "정리")
        self._topology_file(run_name).unlink(missing_ok=True)

    def list_runs(self) -> list[str]:
        p = self._run([self.docker, "ps", "-a", "--filter", "label=containerlab", "--format", '{{.Label "containerlab"}}'],
                      DESTROY_TIMEOUT, "실습 목록 조회")
        return sorted({name for name in p.stdout.split() if RUN_NAME_PATTERN.match(name)})

    # ---- 내부 ----

    def _prepare_router(self, run_name: str, node: str) -> None:
        # FRR 이미지에 vtysh.conf가 없어 vtysh마다 경고가 난다. 호스트 경로를 마운트하지 않고 컨테이너 안에서 만든다
        r = self.exec(run_name, node, ["touch", "/etc/frr/vtysh.conf"])
        if r.exit_code != 0:
            raise LabRuntimeError(f"{node}: vtysh.conf를 만들지 못했습니다: {r.stderr.strip()}")
        # zebra가 뜨기 전에는 preset과 검사의 vtysh가 실패한다
        deadline = time.monotonic() + ROUTER_READY_TIMEOUT
        while True:
            r = self.exec(run_name, node, ["vtysh", "-c", "show ip route json"])
            if r.exit_code == 0 and _is_json(r.stdout):
                return
            if time.monotonic() > deadline:
                raise LabRuntimeError(f"{node}: FRRouting이 {ROUTER_READY_TIMEOUT}초 안에 준비되지 않았습니다")
            time.sleep(0.5)

    def _topology_file(self, run_name: str) -> Path:
        return self.work_dir / f"{run_name}.clab.yml"

    def _run(self, argv: list[str], timeout: int, what: str) -> subprocess.CompletedProcess:
        try:
            p = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=timeout)
        except subprocess.TimeoutExpired:
            raise LabRuntimeError(f"{what}가 {timeout}초 안에 끝나지 않았습니다") from None
        except OSError as exc:
            raise LabRuntimeError(f"{argv[0]}를 실행하지 못했습니다: {exc}") from None
        if p.returncode != 0:
            raise LabRuntimeError(f"{what}에 실패했습니다: {_tail(p.stderr or p.stdout)}")
        return p


def _check_run_name(run_name: str) -> None:
    if not RUN_NAME_PATTERN.match(run_name):
        raise LabRuntimeError(f"실습 이름은 nr-<실행 id>여야 합니다: {run_name}")


def _is_json(text: str) -> bool:
    try:
        json.loads(text)
    except ValueError:
        return False
    return True


def _tail(text: str, lines: int = 5) -> str:
    kept = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(kept[-lines:])
