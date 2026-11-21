"""Notion 페이지 가져오기 API. Notion을 읽기만 한다.

흐름: GET /notion/pages?parent=… (하위 페이지 고르기) → POST /notion/files (.md 내용으로 가져오기)
     → POST /concepts/normalize/plan → POST /concepts/normalize/convert → POST /concepts/files (검사·저장)
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.deps import get_notion
from backend.services.notion_import import fetch_files, list_pages
from integrations.sources.notion import NotionClient, NotionError

router = APIRouter()
NotionDep = Annotated[NotionClient, Depends(get_notion)]


class NotionPage(BaseModel):
    page_id: str
    title: str


class NotionPagesResponse(BaseModel):
    parent: NotionPage
    pages: list[NotionPage]


class NotionFilesRequest(BaseModel):
    page_ids: list[str] = Field(min_length=1, max_length=50, description="페이지 id 또는 주소")


class NotionFileOut(BaseModel):
    page_id: str
    title: str
    name: str = Field(description="제안하는 파일 이름. 저장할 때 바꿀 수 있다")
    content: str | None = Field(description="# 제목 + 페이지 Markdown. 실패하면 null")
    warnings: list[str]
    error: str | None


class NotionFilesResponse(BaseModel):
    files: list[NotionFileOut]


@router.get("/notion/pages")
def notion_pages(parent: str, notion: NotionDep) -> NotionPagesResponse:
    """페이지와 그 바로 아래 하위 페이지. Notion 오류는 502."""
    try:
        result = list_pages(notion, parent)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except NotionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return NotionPagesResponse(
        parent=NotionPage(**vars(result.parent)), pages=[NotionPage(**vars(p)) for p in result.pages],
    )


@router.post("/notion/files")
def notion_files(body: NotionFilesRequest, notion: NotionDep) -> NotionFilesResponse:
    """고른 페이지를 .md 파일 내용으로. 페이지별 실패는 error에 담고 나머지는 계속 가져온다."""
    try:
        files = fetch_files(notion, body.page_ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return NotionFilesResponse(files=[NotionFileOut(**vars(f)) for f in files])
