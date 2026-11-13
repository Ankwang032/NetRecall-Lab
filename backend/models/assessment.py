"""AI 질문, 답안, 답안 평가 테이블."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.models.concept import utcnow


class Question(Base):
    """카드 질문을 AI가 변형한 질문. 난이도는 생성과 별도 호출로 평가한다."""
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("review_cards.id"), index=True)
    concept_id: Mapped[str] = mapped_column(ForeignKey("concepts.id"), index=True)
    base_question: Mapped[str] = mapped_column(Text)  # 생성 당시 카드 질문
    question: Mapped[str] = mapped_column(Text)
    relative_difficulty: Mapped[int]  # -2 훨씬 쉬움 ~ +2 훨씬 어려움
    difficulty_reason: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnswerSubmission(Base):
    __tablename__ = "answer_submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    answer: Mapped[str] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AnswerEvaluation(Base):
    __tablename__ = "answer_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("answer_submissions.id"), unique=True)
    score: Mapped[int]
    # AI 응답 전체 (항목별 점수, 피드백, 추천 실습)
    feedback_json: Mapped[dict] = mapped_column(JSON)
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
