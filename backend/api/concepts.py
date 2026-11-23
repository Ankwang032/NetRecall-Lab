"""개념 조회와 소스 동기화 API."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.deps import get_llm, get_notion, get_session
from backend.models import Concept, ConceptLab, ConceptRelation
from backend.services.concept_extract import KnownConcept
from backend.services.concept_normalize import convert_file, plan_files
from backend.services.concept_store import sync_source
from backend.services.concept_sync import SyncPlan
from backend.services.concept_upload import NewFile, check_files, list_folders, save_files
from integrations.llm import LLMClient, LLMError
from integrations.sources.markdown import MarkdownConceptSource
from integrations.sources.notion import NotionClient, NotionConceptSource, NotionError

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]
LLMDep = Annotated[LLMClient, Depends(get_llm)]
NotionDep = Annotated[NotionClient, Depends(get_notion)]


class ConceptSummary(BaseModel):
    id: str
    title: str
    category: str | None
    difficulty: int | None
    keywords: list[str]
    source_type: str
    source_ref: str
    archived: bool
    prerequisites: list[str]
    related: list[str]
    labs: list[str]


class ConceptDetail(ConceptSummary):
    content: str
    questions: list[str]


class SyncIssue(BaseModel):
    source_ref: str
    message: str


class DanglingRef(BaseModel):
    concept_id: str
    ref: str


class SyncResponse(BaseModel):
    dry_run: bool
    summary: dict[str, int]
    errors: list[SyncIssue]
    warnings: list[SyncIssue]  # 반영은 했지만 알릴 것 (Notion: 빠진 블록, 끊긴 연결 등)
    dangling_refs: list[DanglingRef]


class UploadFileIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    content: str


class UploadRequest(BaseModel):
    folder: str = Field(default="", description="개념 폴더 기준 상대 경로. GET /concepts/folders 중 하나")
    files: list[UploadFileIn] = Field(min_length=1, max_length=50)


class FileCheckOut(BaseModel):
    name: str
    path: str
    concept_id: str | None
    title: str | None
    question_count: int
    errors: list[str]


class UploadResponse(BaseModel):
    saved: bool
    files: list[FileCheckOut]
    sync: SyncResponse | None  # 저장했을 때만


class NormalizePlanRequest(BaseModel):
    files: list[UploadFileIn] = Field(min_length=1, max_length=50)
    prefix: str = Field(default="NET", max_length=16, description="새 id의 접두사 (예: NET → NET-011)")


class PlannedFileOut(BaseModel):
    name: str
    status: Literal["standard", "convert", "failed"] = Field(
        description="standard: 이미 표준 형식이라 그대로 쓴다. convert: /concepts/normalize/convert로 바꾼다",
    )
    concept_id: str | None
    title: str | None
    warnings: list[str]
    error: str | None


class NormalizePlanResponse(BaseModel):
    files: list[PlannedFileOut]


class BatchConcept(BaseModel):
    concept_id: str = Field(max_length=32)
    title: str = Field(max_length=300)


class ConvertRequest(BaseModel):
    file: UploadFileIn
    concept_id: str = Field(max_length=32, description="plan에서 정한 id")
    batch: list[BatchConcept] = Field(
        default_factory=list, max_length=50, description="함께 올린 다른 파일의 id·제목 (plan 결과)",
    )


class ConvertResponse(BaseModel):
    name: str
    concept_id: str
    title: str
    content: str
    warnings: list[str]


@router.post("/sync/markdown")
def sync_markdown(request: Request, session: SessionDep, dry_run: bool = False) -> SyncResponse:
    try:
        source = MarkdownConceptSource(request.app.state.concepts_dir)
    except NotADirectoryError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    plan = sync_source(session, source, dry_run=dry_run)
    return _sync_response(plan, dry_run)


@router.post("/sync/notion")
def sync_notion(request: Request, session: SessionDep, notion: NotionDep, dry_run: bool = False) -> SyncResponse:
    """NETRECALL_NOTION_DATABASE 데이터베이스를 동기화한다. 설정이 없으면 503, Notion 조회가 실패하면 502."""
    database = request.app.state.notion_database
    if not database:
        raise HTTPException(
            status_code=503, detail="동기화할 Notion 데이터베이스가 설정되지 않았습니다 (NETRECALL_NOTION_DATABASE)",
        )
    try:
        source = NotionConceptSource(notion, database)
    except ValueError as exc:
        raise HTTPException(
            status_code=503, detail="NETRECALL_NOTION_DATABASE가 Notion 데이터베이스 주소나 id가 아닙니다",
        ) from exc
    try:
        plan = sync_source(session, source, dry_run=dry_run)
    except NotionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _sync_response(plan, dry_run)


@router.get("/concepts/folders")
def folders(request: Request) -> list[str]:
    """개념 파일을 올릴 수 있는 폴더 ("" = 개념 폴더 자체)."""
    return list_folders(_concepts_root(request))


@router.post("/concepts/files")
def upload_files(
    body: UploadRequest, request: Request, session: SessionDep, dry_run: bool = False,
) -> UploadResponse:
    """Markdown 개념 파일을 검사하고, 모두 통과하면 개념 폴더에 저장한 뒤 동기화한다.

    하나라도 실패하면 아무것도 저장하지 않는다 (saved=false, 파일별 errors 확인).
    """
    root = _concepts_root(request)
    files = [NewFile(f.name, f.content) for f in body.files]
    try:
        if dry_run:
            checks, plan = check_files(session, root, body.folder, files), None
        else:
            checks, plan = save_files(session, root, body.folder, files)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return UploadResponse(
        saved=plan is not None,
        files=[FileCheckOut(**vars(c)) for c in checks],
        sync=_sync_response(plan, False) if plan else None,
    )


@router.post("/concepts/normalize/plan")
def normalize_plan(body: NormalizePlanRequest, request: Request, session: SessionDep) -> NormalizePlanResponse:
    """형식이 다른 .md를 표준 형식으로 맞추기 1단계. AI 없이 파일별 처리 방법과 id를 정한다. 저장하지 않는다."""
    root = _concepts_root(request)
    try:
        planned = plan_files(session, root, [NewFile(f.name, f.content) for f in body.files], body.prefix)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return NormalizePlanResponse(files=[PlannedFileOut(**vars(p)) for p in planned])


@router.post("/concepts/normalize/convert")
def normalize_convert(body: ConvertRequest, request: Request, session: SessionDep, llm: LLMDep) -> ConvertResponse:
    """2단계. 파일 하나를 AI로 채워 표준 .md 내용을 돌려준다. 저장은 POST /concepts/files로 한다.

    AI가 실패하면 502, LLM이 설정되지 않았으면 503.
    """
    root = _concepts_root(request)
    batch = [KnownConcept(b.concept_id, b.title) for b in body.batch]
    try:
        converted = convert_file(
            session, root, llm, NewFile(body.file.name, body.file.content), body.concept_id, batch,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ConvertResponse(**vars(converted))


@router.get("/concepts")
def list_concepts(session: SessionDep, include_archived: bool = False) -> list[ConceptSummary]:
    query = select(Concept).order_by(Concept.id)
    if not include_archived:
        query = query.where(Concept.archived.is_(False))
    concepts = session.scalars(query).all()
    links = _load_links(session, [c.id for c in concepts])
    return [ConceptSummary(**_summary_fields(c, links)) for c in concepts]


@router.get("/concepts/{concept_id}")
def get_concept(concept_id: str, session: SessionDep) -> ConceptDetail:
    concept = session.get(Concept, concept_id)
    if concept is None:
        raise HTTPException(status_code=404, detail="개념이 없습니다")
    links = _load_links(session, [concept.id])
    return ConceptDetail(
        **_summary_fields(concept, links),
        content=concept.content,
        questions=concept.seed_questions,
    )


def _concepts_root(request: Request) -> Path:
    """개념 폴더. 없으면 500과 함께 경로를 알려 준다 (동기화의 "개념 폴더가 없습니다"와 같은 문구)."""
    root = request.app.state.concepts_dir.resolve()
    if not root.is_dir():
        raise HTTPException(status_code=500, detail=f"개념 폴더가 없습니다: {root}")
    return root


def _sync_response(plan: SyncPlan, dry_run: bool) -> SyncResponse:
    return SyncResponse(
        dry_run=dry_run,
        summary=plan.summary(),
        errors=[SyncIssue(source_ref=e.source_ref, message=e.message) for e in plan.errors],
        warnings=[SyncIssue(source_ref=w.source_ref, message=w.message) for w in plan.warnings],
        dangling_refs=[DanglingRef(concept_id=c, ref=r) for c, r in plan.dangling_refs],
    )


def _summary_fields(c: Concept, links: dict[str, dict[str, list[str]]]) -> dict:
    own = links[c.id]
    return {
        "id": c.id, "title": c.title, "category": c.category, "difficulty": c.difficulty,
        "keywords": c.keywords, "source_type": c.source_type, "source_ref": c.source_ref,
        "archived": c.archived, "prerequisites": own["prerequisite"],
        "related": own["related"], "labs": own["lab"],
    }


def _load_links(session: Session, ids: list[str]) -> dict[str, dict[str, list[str]]]:
    links: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    relations = session.scalars(
        select(ConceptRelation).where(ConceptRelation.from_concept_id.in_(ids))
        .order_by(ConceptRelation.to_concept_id)
    )
    for r in relations:
        links[r.from_concept_id][r.relation_type].append(r.to_concept_id)
    labs = session.scalars(
        select(ConceptLab).where(ConceptLab.concept_id.in_(ids)).order_by(ConceptLab.scenario_id)
    )
    for lab in labs:
        links[lab.concept_id]["lab"].append(lab.scenario_id)
    return links
