"""개념과 개념 간 연결 테이블."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Concept(Base):
    __tablename__ = "concepts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(16), index=True)
    source_ref: Mapped[str] = mapped_column(String(1024))
    content_hash: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(300))
    category: Mapped[str | None] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[int | None]
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    # 개념 파일에 직접 쓴 질문. AI가 생성한 질문(questions 테이블)과 구분한다.
    seed_questions: Mapped[list[str]] = mapped_column(JSON, default=list)
    archived: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConceptRelation(Base):
    __tablename__ = "concept_relations"

    from_concept_id: Mapped[str] = mapped_column(ForeignKey("concepts.id"), primary_key=True)
    # FK 없음: 아직 없는 개념도 가리킬 수 있다 (develop-memo D2)
    to_concept_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    relation_type: Mapped[str] = mapped_column(String(16), primary_key=True)  # prerequisite | related


class ConceptLab(Base):
    __tablename__ = "concept_labs"

    concept_id: Mapped[str] = mapped_column(ForeignKey("concepts.id"), primary_key=True)
    # FK 없음: 실습 시나리오는 Phase 5에서 생긴다 (develop-memo D1)
    scenario_id: Mapped[str] = mapped_column(String(32), primary_key=True)
