from __future__ import annotations

from typing import Iterator

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from integrations.labs.base import LabRuntime
from integrations.llm import LLMClient
from integrations.sources.notion import NotionClient


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


def get_llm(request: Request) -> LLMClient:
    llm = request.app.state.llm
    if llm is None:
        raise HTTPException(status_code=503, detail="LLM이 설정되지 않았습니다 (GEMINI_API_KEY)")
    return llm


def get_notion(request: Request) -> NotionClient:
    notion = request.app.state.notion
    if notion is None:
        raise HTTPException(status_code=503, detail="Notion이 설정되지 않았습니다 (NOTION_TOKEN)")
    return notion


def get_lab_runtime(request: Request) -> LabRuntime:
    return request.app.state.lab_runtime
