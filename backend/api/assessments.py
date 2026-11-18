"""AI 변형 질문과 답안 평가 API.

흐름: GET /reviews/due → POST /cards/{id}/questions/original (원래 질문) → POST /questions/{id}/answers
     → (필요하면) POST /cards/{id}/questions (AI 변형 질문) → POST /questions/{id}/answers
     → (피드백을 보고 사용자가 등급 선택) POST /reviews
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.deps import get_llm, get_session
from backend.core.time import to_kst
from backend.models.concept import utcnow
from backend.services.assessment_service import (
    QuestionNotFound, create_original_question, evaluate_answer, generate_question,
)
from backend.services.review_service import CardNotFound, CardNotReviewable
from integrations.llm import LLMClient, LLMError

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]
LLMDep = Annotated[LLMClient, Depends(get_llm)]


class QuestionResponse(BaseModel):
    question_id: int
    card_id: int
    concept_id: str
    base_question: str
    question: str
    kind: Literal["original", "variant"]
    # 변형 질문에만 있다
    relative_difficulty: int | None = Field(description="-2 훨씬 쉬움, -1 쉬움, 0 비슷함, 1 어려움, 2 훨씬 어려움")
    difficulty_reason: str | None
    created_at: datetime


class AnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=10_000)


class EvaluationResponse(BaseModel):
    submission_id: int
    score: int
    accuracy: int
    completeness: int
    logic: int
    technical_validity: int
    application: int
    strengths: list[str]
    missing_points: list[str]
    technical_errors: list[str]
    recommended_lab: str | None
    model: str
    submitted_at: datetime


@router.post("/cards/{card_id}/questions/original", status_code=201)
def create_original(card_id: int, session: SessionDep) -> QuestionResponse:
    """카드 질문 그대로 출제한다. AI를 부르지 않으므로 키가 없어도 된다."""
    try:
        q = create_original_question(session, card_id, utcnow())
    except CardNotFound as exc:
        raise HTTPException(status_code=404, detail="카드가 없습니다") from exc
    except CardNotReviewable as exc:
        raise HTTPException(status_code=409, detail="질문이 삭제됐거나 보관된 개념의 카드입니다") from exc
    return _question_response(q)


@router.post("/cards/{card_id}/questions", status_code=201)
def create_question(card_id: int, session: SessionDep, llm: LLMDep) -> QuestionResponse:
    try:
        q = generate_question(session, llm, card_id, utcnow())
    except CardNotFound as exc:
        raise HTTPException(status_code=404, detail="카드가 없습니다") from exc
    except CardNotReviewable as exc:
        raise HTTPException(status_code=409, detail="질문이 삭제됐거나 보관된 개념의 카드입니다") from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _question_response(q)


def _question_response(q) -> QuestionResponse:
    return QuestionResponse(
        question_id=q.id, card_id=q.card_id, concept_id=q.concept_id,
        base_question=q.base_question, question=q.question, kind=q.kind,
        relative_difficulty=q.relative_difficulty, difficulty_reason=q.difficulty_reason,
        created_at=to_kst(q.created_at),
    )


@router.post("/questions/{question_id}/answers", status_code=201)
def submit_answer(
    question_id: int, body: AnswerRequest, session: SessionDep, llm: LLMDep,
) -> EvaluationResponse:
    try:
        submission, evaluation = evaluate_answer(session, llm, question_id, body.answer, utcnow())
    except QuestionNotFound as exc:
        raise HTTPException(status_code=404, detail="질문이 없습니다") from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return EvaluationResponse(
        submission_id=submission.id, **evaluation.feedback_json,
        model=evaluation.model, submitted_at=to_kst(submission.submitted_at),
    )
