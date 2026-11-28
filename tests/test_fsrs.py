import json
from datetime import UTC, datetime, timedelta

import pytest
from fsrs import Scheduler

from integrations.fsrs import new_card, review, stage

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
FIXED = Scheduler(enable_fuzzing=False)


def test_new_card_is_due_now_and_json_serializable():
    card_json, due_at = new_card(NOW)
    assert due_at == NOW
    assert json.loads(json.dumps(card_json)) == card_json


def test_better_rating_gives_later_due_date():
    card_json, _ = new_card(NOW)
    dues = [review(card_json, rating, NOW, FIXED).due_at for rating in (1, 2, 3, 4)]
    assert all(due > NOW for due in dues)
    assert dues == sorted(dues) and len(set(dues)) == 4


def test_repeated_good_reviews_grow_interval():
    card_json, _ = new_card(NOW)
    now, intervals = NOW, []
    for _ in range(4):
        result = review(card_json, 3, now, FIXED)
        intervals.append(result.due_at - now)
        card_json, now = result.card_json, result.due_at
    assert intervals == sorted(intervals)
    assert intervals[-1] > timedelta(days=1)


def test_review_log_records_rating_and_time():
    card_json, _ = new_card(NOW)
    log = review(card_json, 2, NOW, FIXED).log_json
    assert log["rating"] == 2
    assert datetime.fromisoformat(log["review_datetime"]) == NOW


@pytest.mark.parametrize("rating", [0, 5])
def test_invalid_rating_is_rejected(rating):
    card_json, _ = new_card(NOW)
    with pytest.raises(ValueError):
        review(card_json, rating, NOW, FIXED)


def test_stage_follows_reviews_and_stability():
    card_json, _ = new_card(NOW)
    assert stage(card_json, 21) == "new"
    learning = review(card_json, 3, NOW, FIXED).card_json  # 첫 Good은 아직 학습 단계
    assert stage(learning, 21) == "learning"
    reviewing = review(card_json, 4, NOW, FIXED).card_json  # Easy는 바로 복습 단계
    assert stage(reviewing, 21) == "review"
    assert stage({**reviewing, "stability": 21.0}, 21) == "mature"
    assert stage({**reviewing, "stability": 20.9}, 21) == "review"
    relearning = review(reviewing, 1, NOW + timedelta(days=10), FIXED).card_json  # 잊으면 다시 학습
    assert stage(relearning, 21) == "learning"
