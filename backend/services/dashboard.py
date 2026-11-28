"""대시보드 지표 (설계서 §E-3·§E-4). 저장된 기록에서 그때그때 계산하고 따로 저장하지 않는다 (D3).

날짜는 KST로 나눈다 (D7). 복습량·주별 오답률은 지금까지 남긴 복습 기록 전부를 센다. 카테고리·학습 현황·취약 개념은
지금 복습할 수 있는 카드(활성 카드, 보관되지 않은 개념)만 센다. 눌러서 복습을 시작하는 곳이기 때문이다.
오답률은 (Again + Hard) / 복습 수다.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.time import KST, to_kst
from backend.models import AnswerEvaluation, AnswerSubmission, Concept, LabRun, Question, ReviewCard, ReviewLog
from integrations import fsrs

VOLUME_DAYS = 28    # 복습량·주별 오답률: 오늘까지 4주
FORECAST_DAYS = 7   # 복습 예정: 오늘부터 7일
AGAIN, HARD = 1, 2


@dataclass(frozen=True)
class Rules:
    """기간과 기준값 (설계서 §E-4). 바꾸면 설계서 표와 테스트를 같이 고친다."""
    recent_days: int = 30        # 취약 개념·카테고리별 오답률을 보는 기간 (오늘 포함)
    forgot: int = 2              # 잊음: Again 2회 이상
    struggled: int = 3           # 힘들게 떠올림: Again + Hard 3회 이상
    low_score: int = 60          # 낮은 평가: 원래 질문 평가 점수가 이 값 미만인 것이
    low_score_count: int = 2     #   2회 이상
    mature_days: float = 21      # 학습 현황 "익숙함": 기억 안정성(FSRS stability) 21일 이상


RULES = Rules()


@dataclass(frozen=True)
class Today:
    due: int          # 지금 복습할 카드
    overdue: int      # 그중 오늘 0시 전에 예정이었던 카드 (밀린 복습)
    reviewed: int     # 오늘 남긴 복습 기록 수
    concepts: int     # 활성 개념
    cards: int        # 활성 카드
    streak_days: int  # 오늘(오늘 기록이 없으면 어제)부터 거꾸로 복습한 날이 이어진 수


@dataclass(frozen=True)
class DayReviews:
    date: date
    again: int
    hard: int
    good: int
    easy: int


@dataclass(frozen=True)
class DayDue:
    date: date
    cards: int  # 오늘 칸에는 밀린 카드도 들어간다


@dataclass(frozen=True)
class WeekErrors:
    start: date
    end: date
    reviews: int
    wrong: int  # Again + Hard


@dataclass(frozen=True)
class Stages:
    new: int       # 아직 복습하지 않음
    learning: int  # FSRS Learning·Relearning
    review: int    # Review, 기억 안정성 mature_days 미만
    mature: int    # Review, 기억 안정성 mature_days 이상


@dataclass(frozen=True)
class CategoryStat:
    category: str | None
    stages: Stages
    reviews: int  # 최근 recent_days일 복습 수
    wrong: int    # 그중 Again + Hard


@dataclass(frozen=True)
class Lapse:
    question: str
    rating: int  # 1=Again, 2=Hard
    reviewed_at: datetime


@dataclass(frozen=True)
class LowScore:
    question: str
    score: int
    submitted_at: datetime
    missing_points: list[str]


@dataclass(frozen=True)
class WeakConcept:
    concept_id: str
    title: str
    category: str | None
    signals: list[str]  # forgot(잊음) | struggled(힘들게 떠올림) | low_score(낮은 평가)
    again: int
    hard: int
    low_scores: int
    last_reviewed_at: datetime | None
    next_due_at: datetime | None
    lapses: list[Lapse]               # 근거: 최근 recent_days일 Again·Hard 기록 (최근 것부터)
    low_evaluations: list[LowScore]   # 근거: 낮은 평가와 그 missing_points (최근 것부터)


@dataclass(frozen=True)
class Summary:
    today: Today
    reviews_by_day: list[DayReviews]  # 오래된 날부터, 마지막이 오늘
    due_by_day: list[DayDue]          # 오늘부터
    errors_by_week: list[WeekErrors]  # 복습량과 같은 4주를 7일씩, 오래된 주부터
    stages: Stages
    categories: list[CategoryStat]    # 카드가 많은 순
    weak_concepts: list[WeakConcept]
    rules: Rules


def summary(session: Session, now: datetime, rules: Rules = RULES) -> Summary:
    today = to_kst(now).date()
    recent_start = today - timedelta(days=rules.recent_days - 1)
    volume_start = today - timedelta(days=VOLUME_DAYS - 1)

    live = session.execute(
        select(ReviewCard, Concept).join(Concept, ReviewCard.concept_id == Concept.id)
        .where(ReviewCard.active.is_(True), Concept.archived.is_(False))
        .order_by(ReviewCard.id)
    ).all()
    live_cards = {card.id: (card, concept) for card, concept in live}
    logs = session.scalars(
        select(ReviewLog).where(ReviewLog.reviewed_at >= _utc(min(recent_start, volume_start)))
        .order_by(ReviewLog.reviewed_at.desc(), ReviewLog.id.desc())
    ).all()

    reviews_by_day = _reviews_by_day(logs, volume_start, today)
    return Summary(
        today=Today(
            due=sum(to_kst(card.due_at) <= to_kst(now) for card, _ in live),
            overdue=sum(to_kst(card.due_at).date() < today for card, _ in live),
            reviewed=sum(to_kst(log.reviewed_at).date() == today for log in logs),
            concepts=session.scalar(select(func.count()).select_from(Concept).where(Concept.archived.is_(False))) or 0,
            cards=len(live),
            streak_days=_streak(session, today),
        ),
        reviews_by_day=reviews_by_day,
        due_by_day=_due_by_day([card for card, _ in live], today),
        errors_by_week=[_week(reviews_by_day[i:i + 7]) for i in range(0, VOLUME_DAYS, 7)],
        stages=_stages([card for card, _ in live], rules),
        categories=_categories(live, [log for log in logs if to_kst(log.reviewed_at).date() >= recent_start], rules),
        weak_concepts=_weak_concepts(session, live_cards, logs, recent_start, rules),
        rules=rules,
    )


def run_counts(session: Session) -> dict[str, int]:
    """시나리오 id → 실행 수."""
    return dict(session.execute(select(LabRun.scenario_id, func.count()).group_by(LabRun.scenario_id)).all())


def _utc(day: date) -> datetime:
    """KST 날짜의 0시. DB에는 UTC로 저장하므로 UTC로 바꿔 비교한다."""
    return datetime.combine(day, time(), KST).astimezone(UTC)


def _streak(session: Session, today: date) -> int:
    days = {to_kst(at).date() for at in session.scalars(select(ReviewLog.reviewed_at))}
    day = today if today in days else today - timedelta(days=1)
    streak = 0
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    return streak


def _reviews_by_day(logs: list[ReviewLog], start: date, today: date) -> list[DayReviews]:
    counts = Counter((to_kst(log.reviewed_at).date(), log.rating) for log in logs)
    days = [start + timedelta(days=i) for i in range((today - start).days + 1)]
    return [DayReviews(d, counts[d, 1], counts[d, 2], counts[d, 3], counts[d, 4]) for d in days]


def _week(days: list[DayReviews]) -> WeekErrors:
    return WeekErrors(start=days[0].date, end=days[-1].date,
                      reviews=sum(d.again + d.hard + d.good + d.easy for d in days),
                      wrong=sum(d.again + d.hard for d in days))


def _due_by_day(cards: list[ReviewCard], today: date) -> list[DayDue]:
    counts = Counter(max(to_kst(card.due_at).date(), today) for card in cards)
    return [DayDue(d, counts[d]) for d in (today + timedelta(days=i) for i in range(FORECAST_DAYS))]


def _stages(cards: list[ReviewCard], rules: Rules) -> Stages:
    counts = Counter(fsrs.stage(card.card_json, rules.mature_days) for card in cards)
    return Stages(new=counts["new"], learning=counts["learning"], review=counts["review"], mature=counts["mature"])


def _categories(live: list[tuple[ReviewCard, Concept]], recent_logs: list[ReviewLog], rules: Rules) -> list[CategoryStat]:
    cards: dict[str | None, list[ReviewCard]] = defaultdict(list)
    category_of = {}
    for card, concept in live:
        cards[concept.category].append(card)
        category_of[card.id] = concept.category
    reviews = Counter(category_of[log.card_id] for log in recent_logs if log.card_id in category_of)
    wrong = Counter(category_of[log.card_id] for log in recent_logs
                    if log.card_id in category_of and log.rating in (AGAIN, HARD))
    order = sorted(cards, key=lambda c: (-len(cards[c]), c or ""))
    return [CategoryStat(category=c, stages=_stages(cards[c], rules), reviews=reviews[c], wrong=wrong[c]) for c in order]


def _weak_concepts(session: Session, live_cards: dict[int, tuple[ReviewCard, Concept]], logs: list[ReviewLog],
                   recent_start: date, rules: Rules) -> list[WeakConcept]:
    """취약 개념 규칙 (설계서 §E-4). 신호가 하나라도 걸리면 취약 개념이다."""
    lapses: dict[str, list[Lapse]] = defaultdict(list)
    for log in logs:  # 최근 것부터
        if log.card_id in live_cards and log.rating in (AGAIN, HARD) and to_kst(log.reviewed_at).date() >= recent_start:
            card, concept = live_cards[log.card_id]
            lapses[concept.id].append(Lapse(card.question, log.rating, to_kst(log.reviewed_at)))

    low: dict[str, list[LowScore]] = defaultdict(list)
    rows = session.execute(
        select(Question.card_id, Question.question, AnswerEvaluation.score, AnswerEvaluation.feedback_json,
               AnswerSubmission.submitted_at)
        .join(AnswerSubmission, AnswerSubmission.question_id == Question.id)
        .join(AnswerEvaluation, AnswerEvaluation.submission_id == AnswerSubmission.id)
        .where(Question.kind == "original",  # 변형 질문은 난이도가 달라 세지 않는다
               AnswerEvaluation.score < rules.low_score, AnswerSubmission.submitted_at >= _utc(recent_start))
        .order_by(AnswerSubmission.submitted_at.desc(), AnswerSubmission.id.desc())
    )
    for card_id, question, score, feedback, submitted_at in rows:
        if card_id in live_cards:
            low[live_cards[card_id][1].id].append(
                LowScore(question, score, to_kst(submitted_at), list(feedback.get("missing_points", []))))

    weak = []
    for concept_id in sorted(set(lapses) | set(low)):
        again = sum(lapse.rating == AGAIN for lapse in lapses[concept_id])
        hard = len(lapses[concept_id]) - again
        signals = [name for name, hit in (("forgot", again >= rules.forgot),
                                          ("struggled", again + hard >= rules.struggled),
                                          ("low_score", len(low[concept_id]) >= rules.low_score_count)) if hit]
        if signals:
            weak.append((concept_id, again, hard, signals))
    if not weak:
        return []

    ids = [w[0] for w in weak]
    last_reviewed = dict(session.execute(
        select(ReviewCard.concept_id, func.max(ReviewLog.reviewed_at))
        .join(ReviewLog, ReviewLog.card_id == ReviewCard.id)
        .where(ReviewCard.active.is_(True), ReviewCard.concept_id.in_(ids))
        .group_by(ReviewCard.concept_id)
    ).all())
    next_due: dict[str, datetime] = {}
    concepts: dict[str, Concept] = {}
    for card, concept in live_cards.values():
        concepts[concept.id] = concept
        due = to_kst(card.due_at)
        if concept.id not in next_due or due < next_due[concept.id]:
            next_due[concept.id] = due

    result = [
        WeakConcept(
            concept_id=cid, title=concepts[cid].title, category=concepts[cid].category, signals=signals,
            again=again, hard=hard, low_scores=len(low[cid]),
            last_reviewed_at=to_kst(last_reviewed[cid]) if cid in last_reviewed else None,
            next_due_at=next_due.get(cid), lapses=lapses[cid], low_evaluations=low[cid],
        )
        for cid, again, hard, signals in weak
    ]
    # Again 수 → 낮은 평가 수 → 마지막 복습이 오래된 순 (복습한 적 없으면 가장 오래된 것으로 본다)
    return sorted(result, key=lambda w: (-w.again, -w.low_scores, w.last_reviewed_at is not None,
                                         w.last_reviewed_at or datetime.min.replace(tzinfo=KST), w.concept_id))
