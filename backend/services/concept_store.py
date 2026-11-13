"""동기화 계획을 DB에 반영한다.

DB 현재 상태 읽기 → 계획 수립 → 반영을 한 트랜잭션으로 처리한다.
반영 중 하나라도 실패하면 전부 되돌린다.
개념의 질문과 복습 카드도 여기서 맞춘다 (질문 1개 = 카드 1장).
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.models import Concept, ConceptLab, ConceptRelation, ReviewCard
from backend.models.concept import utcnow
from backend.services.concept_sync import ExistingConcept, SyncPlan, plan_sync
from integrations.fsrs import new_card
from integrations.sources.base import ConceptSource, RawConcept

RELATION_FIELDS = (("prerequisite", "prerequisites"), ("related", "related"))


def sync_source(session: Session, source: ConceptSource, *, dry_run: bool = False) -> SyncPlan:
    fetched = source.fetch_all()  # 파일 읽기는 트랜잭션 밖에서
    try:
        plan = plan_sync(source.source_type, fetched, load_existing(session))
        if dry_run:
            session.rollback()
        else:
            apply_plan(session, plan)
            session.commit()
    except Exception:
        session.rollback()
        raise
    return plan


def load_existing(session: Session) -> list[ExistingConcept]:
    """모든 소스의 개념. 다른 소스와의 id 충돌을 판단하려면 전부 필요하다."""
    rows = session.execute(select(
        Concept.id, Concept.source_type, Concept.source_ref, Concept.content_hash, Concept.archived,
    ))
    return [ExistingConcept(*row) for row in rows]


def apply_plan(session: Session, plan: SyncPlan) -> None:
    now = utcnow()

    for raw in plan.created:
        session.add(Concept(id=raw.concept_id, created_at=now, updated_at=now, **_fields(raw)))

    # updated는 위치 변경을 포함할 수 있으므로 source_ref까지 전부 덮어쓴다
    for raw in plan.updated + plan.restored:
        concept = session.get_one(Concept, raw.concept_id)
        for key, value in _fields(raw).items():
            setattr(concept, key, value)
        concept.archived = False
        concept.updated_at = now

    for raw in plan.relocated:
        concept = session.get_one(Concept, raw.concept_id)
        concept.source_ref = raw.source_ref
        concept.updated_at = now

    for concept_id in plan.archived:
        concept = session.get_one(Concept, concept_id)
        concept.archived = True
        concept.updated_at = now

    session.flush()  # 연결 테이블의 FK가 가리킬 개념 행을 먼저 쓴다
    for raw in plan.created + plan.updated + plan.restored:
        _replace_links(session, raw)
        _sync_cards(session, raw, now)
    session.flush()


def _fields(raw: RawConcept) -> dict:
    return {
        "source_type": raw.source_type,
        "source_ref": raw.source_ref,
        "content_hash": raw.content_hash,
        "title": raw.title,
        "category": raw.category,
        "content": raw.content,
        "difficulty": raw.difficulty,
        "keywords": list(raw.keywords),
        "seed_questions": list(raw.questions),
    }


def _replace_links(session: Session, raw: RawConcept) -> None:
    session.execute(delete(ConceptRelation).where(ConceptRelation.from_concept_id == raw.concept_id))
    session.execute(delete(ConceptLab).where(ConceptLab.concept_id == raw.concept_id))
    session.add_all(
        ConceptRelation(from_concept_id=raw.concept_id, to_concept_id=ref, relation_type=kind)
        for kind, attr in RELATION_FIELDS
        for ref in getattr(raw, attr)
    )
    session.add_all(ConceptLab(concept_id=raw.concept_id, scenario_id=lab) for lab in raw.lab_ids)


def question_hash(question: str) -> str:
    return hashlib.sha256(question.encode("utf-8")).hexdigest()


def _sync_cards(session: Session, raw: RawConcept, now: datetime) -> None:
    """질문마다 카드 한 장. 사라진 질문의 카드는 비활성화하고, 다시 생기면 되살린다."""
    cards = {
        c.question_hash: c
        for c in session.scalars(select(ReviewCard).where(ReviewCard.concept_id == raw.concept_id))
    }
    wanted = {question_hash(q): q for q in raw.questions}

    for h, question in wanted.items():
        card = cards.get(h)
        if card is None:
            card_json, due_at = new_card(now)
            session.add(ReviewCard(
                concept_id=raw.concept_id, question_hash=h, question=question,
                card_json=card_json, due_at=due_at, created_at=now, updated_at=now,
            ))
        elif not card.active:
            card.active = True
            card.updated_at = now

    for h, card in cards.items():
        if h not in wanted and card.active:
            card.active = False
            card.updated_at = now
