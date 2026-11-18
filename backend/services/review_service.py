"""FSRS 복습 흐름: 복습할 카드 조회와 평가 반영."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Concept, ReviewCard, ReviewLog
from integrations import fsrs


class CardNotFound(LookupError):
    pass


class CardNotReviewable(ValueError):
    """질문이 사라졌거나(비활성) 개념이 보관된 카드."""


def due_cards(session: Session, now: datetime) -> list[tuple[ReviewCard, Concept]]:
    """지금 복습할 카드. 기한이 오래된 것부터."""
    rows = session.execute(
        select(ReviewCard, Concept)
        .join(Concept, ReviewCard.concept_id == Concept.id)
        .where(ReviewCard.active.is_(True), Concept.archived.is_(False), ReviewCard.due_at <= now)
        .order_by(ReviewCard.due_at, ReviewCard.id)
    )
    return [tuple(row) for row in rows]


def submit_review(session: Session, card_id: int, rating: int, now: datetime) -> ReviewLog:
    """평가를 반영하고 복습 기록을 남긴다. 카드 갱신과 기록 추가는 한 트랜잭션이다."""
    try:
        card = session.get(ReviewCard, card_id)
        if card is None:
            raise CardNotFound(card_id)
        if not card.active or session.get_one(Concept, card.concept_id).archived:
            raise CardNotReviewable(card_id)

        result = fsrs.review(card.card_json, rating, now)
        card.card_json = result.card_json
        card.due_at = result.due_at
        card.updated_at = now
        log = ReviewLog(
            card_id=card.id, rating=rating, reviewed_at=now,
            next_due_at=result.due_at, log_json=result.log_json,
        )
        session.add(log)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return log
