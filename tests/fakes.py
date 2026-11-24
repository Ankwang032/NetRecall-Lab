"""테스트용 가짜 LLM·실습 런타임. 실제 API·Docker를 호출하지 않는다."""
from __future__ import annotations

from pydantic import BaseModel

from integrations.labs.base import ExecResult, RenderedTopology
from integrations.llm import LLMError


class FakeLLM:
    model = "fake-model"

    def __init__(self, *responses: BaseModel | Exception) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def generate(self, *, system, prompt, schema):
        self.calls.append({"system": system, "prompt": prompt, "schema": schema})
        if not self.responses:
            raise LLMError("준비된 응답이 없습니다")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        assert isinstance(response, schema), f"{schema.__name__}를 기대했지만 {type(response).__name__}"
        return response


class FakeLabRuntime:
    """(노드, argv)마다 준비한 결과를 돌려준다. 준비하지 않은 명령은 실패(종료 코드 1)로 답한다."""

    def __init__(self, responses: dict[tuple[str, tuple[str, ...]], ExecResult | Exception] | None = None) -> None:
        self.responses = dict(responses or {})
        self.calls: list[tuple[str, str, tuple[str, ...]]] = []
        self.deployed: dict[str, RenderedTopology] = {}

    def deploy(self, run_name: str, topology: RenderedTopology) -> None:
        self.deployed[run_name] = topology

    def exec(self, run_name: str, node: str, argv: list[str]) -> ExecResult:
        self.calls.append((run_name, node, tuple(argv)))
        response = self.responses.get((node, tuple(argv)), ExecResult(1, "", "준비된 응답 없음"))
        if isinstance(response, Exception):
            raise response
        return response

    def destroy(self, run_name: str) -> None:
        self.deployed.pop(run_name, None)

    def list_runs(self) -> list[str]:
        return sorted(self.deployed)

