from __future__ import annotations

from typing import Iterator

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from integrations.llm import LLMClient


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


def get_llm(request: Request) -> LLMClient:
    llm = request.app.state.llm
    if llm is None:
        raise HTTPException(status_code=503, detail="LLM이 설정되지 않았습니다 (GEMINI_API_KEY)")
    return llm
