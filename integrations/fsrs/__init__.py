"""FSRS 라이브러리(py-fsrs) 감싸기.

라이브러리를 직접 쓰는 곳은 이 모듈뿐이다. 나머지 코드는 카드 상태를 dict(JSON)로만 다룬다.
라이브러리 버전이 바뀌면 이 파일과 직렬화 형식만 확인하면 된다 (develop-memo D4).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fsrs import Card, Rating, Scheduler, State

DEFAULT_SCHEDULER = Scheduler()


@dataclass(frozen=True)
class ReviewResult:
    card_json: dict
    due_at: datetime
    log_json: dict


def new_card(now: datetime) -> tuple[dict, datetime]:
    """바로 복습할 수 있는 새 카드. (card_json, due_at)"""
    card = Card(due=now)
    return card.to_dict(), card.due


def review(
    card_json: dict,
    rating: int,
    now: datetime,
    scheduler: Scheduler = DEFAULT_SCHEDULER,
) -> ReviewResult:
    """rating: 1=Again, 2=Hard, 3=Good, 4=Easy"""
    card, log = scheduler.review_card(Card.from_dict(card_json), Rating(rating), now)
    return ReviewResult(card_json=card.to_dict(), due_at=card.due, log_json=log.to_dict())


def stage(card_json: dict, mature_days: float) -> str:
    """학습 단계: new(아직 복습하지 않음) | learning(Learning·Relearning) | review | mature(기억 안정성 mature_days일 이상)."""
    card = Card.from_dict(card_json)
    if card.last_review is None:
        return "new"
    if card.state == State.Review:
        return "mature" if card.stability >= mature_days else "review"
    return "learning"
