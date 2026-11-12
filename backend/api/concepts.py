"""개념 조회와 소스 동기화 API."""
from __future__ import annotations

from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.deps import get_session
from backend.models import Concept, ConceptLab, ConceptRelation
from backend.services.concept_store import sync_source
from integrations.sources.markdown import MarkdownConceptSource

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]


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
    dangling_refs: list[DanglingRef]


@router.post("/sync/markdown")
def sync_markdown(request: Request, session: SessionDep, dry_run: bool = False) -> SyncResponse:
    try:
        source = MarkdownConceptSource(request.app.state.concepts_dir)
    except NotADirectoryError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    plan = sync_source(session, source, dry_run=dry_run)
    return SyncResponse(
        dry_run=dry_run,
        summary=plan.summary(),
        errors=[SyncIssue(source_ref=e.source_ref, message=e.message) for e in plan.errors],
        dangling_refs=[DanglingRef(concept_id=c, ref=r) for c, r in plan.dangling_refs],
    )


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
