"""테스트용 가짜 LLM. 실제 API를 호출하지 않는다."""
from __future__ import annotations

from pydantic import BaseModel

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
