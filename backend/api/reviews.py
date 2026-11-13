"""FSRS 복습 API."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.deps import get_session
from backend.core.time import to_kst
from backend.models.concept import utcnow
from backend.services.review_service import (
    CardNotFound, CardNotReviewable, due_cards, submit_review,
)

router = APIRouter(prefix="/reviews")
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


@router.get("/due")
def list_due(session: SessionDep) -> list[DueCard]:
    return [
        DueCard(card_id=card.id, concept_id=concept.id, concept_title=concept.title,
                question=card.question, due_at=to_kst(card.due_at))
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
                          reviewed_at=to_kst(log.reviewed_at), next_due_at=to_kst(log.next_due_at))
