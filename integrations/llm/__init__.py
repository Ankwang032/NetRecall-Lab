"""LLM 공통 인터페이스.

서비스 계층은 LLMClient만 보고, 어떤 제공자(Gemini 등)인지는 알지 못한다.
응답은 항상 Pydantic 스키마로 검증된 객체로 돌려준다 (설계서 §2.2-C).
"""
from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """LLM 호출 실패 또는 스키마에 맞지 않는 응답."""


class LLMClient(Protocol):
    model: str

    def generate(self, *, system: str, prompt: str, schema: type[T]) -> T: ...
