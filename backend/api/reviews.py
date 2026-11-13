"""FSRS 복습 API."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.deps import get_session
from backend.models.concept import utcnow
from backend.services.review_service import (
    CardNotFound, CardNotReviewable, due_cards, submit_review,
)

router = APIRouter(prefix="/reviews")
# 한국은 일광 절약 시간이 없어 고정 오프셋으로 충분하다 (Windows에 tzdata가 없어도 동작)
KST = timezone(timedelta(hours=9), "KST")
SessionDep = Annotated[Session, Depends(get_session)]


class DueCard(BaseModel):
    card_id: int
    concept_id: str
    concept_title: str
    question: str
    due_at: datetime


class ReviewRequest(BaseModel):
    card_id: int
    rating: int = Field(ge=1, le=4, description="1=Again, 2=Hard, 3=Good, 4=Easy")


class ReviewResponse(BaseModel):
    card_id: int
    rating: int
    reviewed_at: datetime
    next_due_at: datetime


def _kst(value: datetime) -> datetime:
    # DB에는 UTC로 저장한다. SQLite에서 읽은 값은 시간대가 없으므로 UTC로 보고 KST로 바꾼다.
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(KST)


@router.get("/due")
def list_due(session: SessionDep) -> list[DueCard]:
    return [
        DueCard(card_id=card.id, concept_id=concept.id, concept_title=concept.title,
                question=card.question, due_at=_kst(card.due_at))
        for card, concept in due_cards(session, utcnow())
    ]


@router.post("")
def review(body: ReviewRequest, session: SessionDep) -> ReviewResponse:
    try:
        log = submit_review(session, body.card_id, body.rating, utcnow())
    except CardNotFound as exc:
        raise HTTPException(status_code=404, detail="카드가 없습니다") from exc
    except CardNotReviewable as exc:
        raise HTTPException(
            status_code=409, detail="질문이 삭제됐거나 보관된 개념의 카드입니다",
        ) from exc
    return ReviewResponse(card_id=log.card_id, rating=log.rating,
                          reviewed_at=_kst(log.reviewed_at), next_due_at=_kst(log.next_due_at))
