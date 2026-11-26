"""개념 보기 화면에 쓰는 기록 조회 (설계서 §E-2). 새 기록을 만들지 않고 저장된 기록에서 계산만 한다."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import AnswerEvaluation, AnswerSubmission, LabRun, Question, ReviewCard, ReviewLog
from backend.services.lab_scenario import Scenario


@dataclass(frozen=True)
class CardStat:
    card: ReviewCard
    reviews: int
    last_rating: int | None
    last_reviewed_at: datetime | None
    last_score: int | None         # 원래 질문의 가장 최근 평가 점수 (변형 질문은 난이도가 달라 넣지 않는다)
    last_scored_at: datetime | None


def card_counts(session: Session, concept_ids: list[str]) -> dict[str, tuple[int, datetime]]:
    """개념 id → (활성 카드 수, 가장 가까운 다음 복습일). 카드가 없는 개념은 없다."""
    rows = session.execute(
        select(ReviewCard.concept_id, func.count(), func.min(ReviewCard.due_at))
        .where(ReviewCard.active.is_(True), ReviewCard.concept_id.in_(concept_ids))
        .group_by(ReviewCard.concept_id)
    )
    return {concept_id: (count, due) for concept_id, count, due in rows}


def card_stats(session: Session, concept_id: str) -> list[CardStat]:
    """활성 카드마다 복습 횟수·마지막 등급·원래 질문의 최근 평가 점수."""
    cards = session.scalars(
        select(ReviewCard).where(ReviewCard.concept_id == concept_id, ReviewCard.active.is_(True)).order_by(ReviewCard.id)
    ).all()
    ids = [c.id for c in cards]
    logs: dict[int, list[ReviewLog]] = defaultdict(list)
    for log in session.scalars(select(ReviewLog).where(ReviewLog.card_id.in_(ids))
                               .order_by(ReviewLog.reviewed_at, ReviewLog.id)):
        logs[log.card_id].append(log)
    scores: dict[int, tuple[int, datetime]] = {}
    rows = session.execute(
        select(Question.card_id, AnswerEvaluation.score, AnswerSubmission.submitted_at)
        .join(AnswerSubmission, AnswerSubmission.question_id == Question.id)
        .join(AnswerEvaluation, AnswerEvaluation.submission_id == AnswerSubmission.id)
        .where(Question.card_id.in_(ids), Question.kind == "original")
        .order_by(AnswerSubmission.submitted_at, AnswerSubmission.id)
    )
    for card_id, score, submitted_at in rows:  # 시간순이라 마지막 것이 남는다
        scores[card_id] = (score, submitted_at)
    return [
        CardStat(
            card=c,
            reviews=len(logs[c.id]),
            last_rating=logs[c.id][-1].rating if logs[c.id] else None,
            last_reviewed_at=logs[c.id][-1].reviewed_at if logs[c.id] else None,
            last_score=scores[c.id][0] if c.id in scores else None,
            last_scored_at=scores[c.id][1] if c.id in scores else None,
        )
        for c in cards
    ]


def lab_ids(concept_id: str, own_labs: list[str], scenarios: list[Scenario]) -> list[str]:
    """이 개념과 연결된 실습: 개념 원본의 labs(Notion "실습" 속성 등)와, 시나리오 concepts에 이 개념이 든 실습."""
    return sorted(set(own_labs) | {s.id for s in scenarios if concept_id in s.concepts})


def runs_by_scenario(session: Session, scenario_ids: list[str]) -> dict[str, list[LabRun]]:
    """시나리오 id → 실행 (최근 것부터)."""
    runs: dict[str, list[LabRun]] = defaultdict(list)
    for run in session.scalars(select(LabRun).where(LabRun.scenario_id.in_(scenario_ids)).order_by(LabRun.id.desc())):
        runs[run.scenario_id].append(run)
    return runs
