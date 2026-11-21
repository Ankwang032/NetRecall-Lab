"""형식이 다른 .md를 표준 개념 형식으로 맞춘다. 저장하지 않는다.

AI 호출이 파일 하나에 수십 초 걸려서 두 단계로 나눈다. 여러 파일을 한 요청에서 처리하면 너무 길어진다.
1. plan_files: AI 없이 모든 파일을 본다. 이미 표준 형식이고 질문이 충분하면 그대로 둔다(standard).
   아니면 제목과 id를 정한다(convert). id는 노트 frontmatter의 id, 없으면 접두사 + 쓰인 번호 다음.
   쓰인 번호에는 DB의 모든 개념(보관·다른 소스 포함), 개념 폴더, 함께 올린 파일이 들어간다.
2. convert_file: 파일 하나를 AI로 채워 표준 .md를 만든다. plan에서 정한 다른 파일의 id·제목(batch)을 받아
   아직 저장하지 않은 파일도 선수·연관 개념으로 고를 수 있게 한다.
저장은 기존 파일 올리기(concept_upload)의 검사·저장을 그대로 쓴다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Concept
from backend.services.concept_extract import KnownConcept, extract_concept, next_concept_id
from backend.services.concept_sync import MIN_QUESTIONS
from backend.services.concept_upload import MAX_FILE_BYTES, NewFile
from integrations.llm import LLMClient
from integrations.sources.base import RawConcept
from integrations.sources.markdown import MarkdownConceptSource, MarkdownParseError, parse_concept
from integrations.sources.markdown.adapter import CONCEPT_ID_PATTERN
from integrations.sources.markdown.render import render_concept
from integrations.sources.normalize import NoteParts, split_note


@dataclass
class PlannedFile:
    name: str
    status: Literal["standard", "convert", "failed"]
    concept_id: str | None = None
    title: str | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class ConvertedFile:
    name: str
    concept_id: str
    title: str
    content: str
    warnings: list[str]


@dataclass(frozen=True)
class _Existing:
    taken_ids: frozenset[str]
    known: tuple[KnownConcept, ...]
    categories: tuple[str, ...]


def plan_files(session: Session, root: Path, files: Sequence[NewFile], prefix: str) -> list[PlannedFile]:
    """AI 없이 파일별 처리 방법과 id를 정한다. 접두사 형식이 틀리면 ValueError."""
    next_concept_id(prefix, [])  # 접두사 검사
    existing = _existing(session, root)
    taken = set(existing.taken_ids)
    planned: list[PlannedFile] = []

    for f in files:
        text = _text(f)
        if len(text.encode("utf-8")) > MAX_FILE_BYTES:
            planned.append(PlannedFile(f.name, "failed", error=f"파일이 너무 큽니다 (최대 {MAX_FILE_BYTES} bytes)"))
            continue
        if standard := _standard(text, f.name):
            planned.append(PlannedFile(f.name, "standard", standard.concept_id, standard.title))
            taken.add(standard.concept_id)
            continue
        parts = _parts(text, f.name)
        if not parts.body:
            planned.append(PlannedFile(f.name, "failed", title=parts.title, error="본문이 비어 있습니다"))
            continue
        plan = PlannedFile(f.name, "convert", title=parts.title, warnings=list(parts.warnings))
        meta_id = parts.meta.get("id")
        if isinstance(meta_id, str) and CONCEPT_ID_PATTERN.match(meta_id):
            plan.concept_id = meta_id
            taken.add(meta_id)
        elif meta_id is not None:
            plan.warnings.append("frontmatter id 형식이 틀려 새 id를 매겼습니다")
        planned.append(plan)

    for plan in planned:  # 노트에 적힌 id를 모두 모은 뒤에 새 번호를 매긴다
        if plan.status == "convert" and plan.concept_id is None:
            plan.concept_id = next_concept_id(prefix, taken)
            taken.add(plan.concept_id)
    return planned


def convert_file(
    session: Session, root: Path, llm: LLMClient, file: NewFile, concept_id: str, batch: Sequence[KnownConcept],
) -> ConvertedFile:
    """파일 하나를 AI로 채워 표준 .md로. 입력이 틀리면 ValueError, AI가 실패하면 LLMError."""
    if not CONCEPT_ID_PATTERN.match(concept_id):
        raise ValueError(f"개념 id 형식이 틀렸습니다: {concept_id}")
    text = _text(file)
    if len(text.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError(f"파일이 너무 큽니다 (최대 {MAX_FILE_BYTES} bytes)")
    parts = _parts(text, file.name)
    if not parts.body:
        raise ValueError("본문이 비어 있습니다")

    existing = _existing(session, root)  # 읽기 트랜잭션은 여기서 끝난다. AI 호출 동안 DB를 잡지 않는다
    known = {k.concept_id: k for k in batch} | {k.concept_id: k for k in existing.known}
    draft = extract_concept(
        llm, parts, concept_id=concept_id, known=list(known.values()), categories=existing.categories,
    )
    concept = RawConcept(
        concept_id=draft.concept_id, title=draft.title, content=draft.body,
        source_type=MarkdownConceptSource.source_type, source_ref=file.name,
        category=draft.category, keywords=tuple(draft.keywords), difficulty=draft.difficulty,
        lab_ids=tuple(draft.labs), prerequisites=tuple(draft.prerequisites), related=tuple(draft.related),
        questions=tuple(draft.questions),
    )
    return ConvertedFile(file.name, concept_id, draft.title, render_concept(concept), draft.warnings)


def _existing(session: Session, root: Path) -> _Existing:
    rows = session.execute(select(Concept.id, Concept.title, Concept.category, Concept.archived)).all()
    session.rollback()
    folder = MarkdownConceptSource(root).fetch_all().concepts  # 아직 동기화하지 않은 파일도 본다

    known = {r.id: r.title for r in rows if not r.archived} | {c.concept_id: c.title for c in folder}
    categories = {r.category for r in rows if r.category and not r.archived}
    categories |= {c.category for c in folder if c.category}
    return _Existing(
        taken_ids=frozenset({r.id for r in rows} | {c.concept_id for c in folder}),
        known=tuple(KnownConcept(i, t) for i, t in sorted(known.items())),
        categories=tuple(sorted(categories)),
    )


def _text(file: NewFile) -> str:
    return file.content.removeprefix("﻿").replace("\r\n", "\n")  # 어댑터와 같은 정규화


def _standard(text: str, name: str) -> RawConcept | None:
    try:
        concept = parse_concept(text, source_ref=name, fallback_title=Path(name).stem)
    except MarkdownParseError:
        return None
    return concept if len(concept.questions) >= MIN_QUESTIONS else None


def _parts(text: str, name: str) -> NoteParts:
    return split_note(text, fallback_title=Path(name).stem)
