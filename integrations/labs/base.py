"""실행 환경 인터페이스(LabRuntime)와 실행 환경이 받는 토폴로지 타입.

토폴로지에는 시나리오를 렌더링한 결과 중 실행 환경이 알아야 하는 것(노드 종류와 링크)만 담는다.
이미지·자원 제한처럼 실행 환경마다 다른 것은 각 실행기가 정한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

NODE_KINDS = ("host", "router")  # host: Linux, router: FRRouting
MAX_NODES = 6


@dataclass(frozen=True, order=True)
class Endpoint:
    node: str
    interface: str

    def __str__(self) -> str:
        return f"{self.node}:{self.interface}"


@dataclass(frozen=True)
class TopologyNode:
    name: str
    kind: str


@dataclass(frozen=True)
class TopologyLink:
    a: Endpoint
    b: Endpoint


@dataclass(frozen=True)
class RenderedTopology:
    nodes: tuple[TopologyNode, ...]
    links: tuple[TopologyLink, ...]


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str


class LabRuntimeError(RuntimeError):
    """실행 환경을 쓰지 못함 (배포 실패, 노드 없음, 명령 시간 초과 등)."""


class LabRuntime(Protocol):
    """오케스트레이터와 검증기는 Containerlab을 직접 부르지 않고 이것만 호출한다.

    exec는 셸을 거치지 않고 argv 그대로 실행한다. 실패하면 LabRuntimeError.
    """

    def deploy(self, run_name: str, topology: RenderedTopology) -> None: ...

    def exec(self, run_name: str, node: str, argv: list[str]) -> ExecResult: ...

    def destroy(self, run_name: str) -> None: ...

    def list_runs(self) -> list[str]: ...  # 남은 실습 정리용
