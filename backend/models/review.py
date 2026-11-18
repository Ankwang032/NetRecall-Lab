"""FSRS 복습 카드와 복습 이력 테이블."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.models.concept import utcnow


class ReviewCard(Base):
    """개념의 질문 하나 = 카드 하나. 질문 문장 해시로 카드를 식별한다."""
    __tablename__ = "review_cards"
    __table_args__ = (UniqueConstraint("concept_id", "question_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    concept_id: Mapped[str] = mapped_column(ForeignKey("concepts.id"), index=True)
    question_hash: Mapped[str] = mapped_column(String(64))
    question: Mapped[str] = mapped_column(Text)
    # 개념 파일에서 질문이 사라지면 false. 이력을 지키기 위해 행은 지우지 않는다.
    active: Mapped[bool] = mapped_column(default=True)
    # py-fsrs Card.to_dict() 그대로 (develop-memo D4)
    card_json: Mapped[dict] = mapped_column(JSON)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReviewLog(Base):
    __tablename__ = "review_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("review_cards.id"), index=True)
    rating: Mapped[int]  # 1=Again, 2=Hard, 3=Good, 4=Easy
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    next_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # py-fsrs ReviewLog.to_dict() 그대로. 나중에 FSRS 파라미터 최적화에 쓴다.
    log_json: Mapped[dict] = mapped_column(JSON)
