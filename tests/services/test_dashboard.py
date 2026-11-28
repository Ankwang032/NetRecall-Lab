from datetime import UTC, date, datetime, timedelta

import pytest

from backend.core.time import KST
from backend.database import init_db, make_engine, make_session_factory
from backend.models import AnswerEvaluation, AnswerSubmission, Concept, Question, ReviewCard, ReviewLog
from backend.services.dashboard import CategoryStat, DayDue, DayReviews, Lapse, Stages, Today, summary
from integrations import fsrs

# KST 11월 28일 0시 30분 = UTC 11월 27일 15시 30분. UTC 날짜로 나누면 "오늘"이 하루 어긋난다
NOW = datetime(2026, 11, 28, 0, 30, tzinfo=KST)
TODAY = date(2026, 11, 28)


@pytest.fixture
def session(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)
    with make_session_factory(engine)() as s:
        yield s
    engine.dispose()


def kst(month: int, day: int, hour: int = 0, minute: int = 10) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=KST)


def add_concept(session, cid, cards=1, category="라우팅", archived=False) -> list[ReviewCard]:
    session.add(Concept(id=cid, source_type="markdown", source_ref=f"{cid}.md", content_hash="h",
                        title=f"{cid} 제목", category=category, content="", archived=archived))
    added = []
    for i in range(cards):
        card_json, due = fsrs.new_card(NOW)
        added.append(ReviewCard(concept_id=cid, question_hash=f"{cid}-{i}", question=f"{cid} 질문 {i}",
                                card_json=card_json, due_at=due.astimezone(UTC)))
    session.add_all(added)
    session.flush()
    return added


def add_log(session, card, rating, at):
    # DB에는 UTC로 저장한다 (앱은 utcnow()로 남긴다)
    session.add(ReviewLog(card_id=card.id, rating=rating, reviewed_at=at.astimezone(UTC),
                          next_due_at=at.astimezone(UTC), log_json={}))
    session.flush()


def add_evaluation(session, card, score, at, kind="original", missing=()):
    q = Question(card_id=card.id, concept_id=card.concept_id, base_question=card.question, question=card.question, kind=kind)
    session.add(q)
    session.flush()
    sub = AnswerSubmission(question_id=q.id, answer="답", submitted_at=at.astimezone(UTC))
    session.add(sub)
    session.flush()
    session.add(AnswerEvaluation(submission_id=sub.id, score=score, feedback_json={"missing_points": list(missing)},
                                 model="fake", prompt_version="1"))
    session.flush()


def test_empty_database_gives_zeros_and_full_date_ranges(session):
    s = summary(session, NOW)
    assert s.today == Today(due=0, overdue=0, reviewed=0, concepts=0, cards=0, streak_days=0)
    assert [d.date for d in s.reviews_by_day] == [date(2026, 11, 1) + timedelta(days=i) for i in range(28)]
    assert all(d == DayReviews(d.date, 0, 0, 0, 0) for d in s.reviews_by_day)
    assert s.due_by_day == [DayDue(TODAY + timedelta(days=i), 0) for i in range(7)]
    assert [(w.start, w.end, w.reviews, w.wrong) for w in s.errors_by_week] == [
        (date(2026, 11, 1), date(2026, 11, 7), 0, 0), (date(2026, 11, 8), date(2026, 11, 14), 0, 0),
        (date(2026, 11, 15), date(2026, 11, 21), 0, 0), (date(2026, 11, 22), TODAY, 0, 0),
    ]
    assert s.stages == Stages(0, 0, 0, 0)
    assert s.categories == [] and s.weak_concepts == []


def test_due_overdue_and_forecast_split_at_kst_midnight(session):
    cards = add_concept(session, "NET-001", cards=6)
    dues = [kst(11, 27, 23, 50), kst(11, 28, 0, 10), kst(11, 28, 9), kst(11, 30), kst(12, 4), kst(12, 5)]
    for card, due in zip(cards, dues):
        card.due_at = due.astimezone(UTC)
    inactive = add_concept(session, "NET-002")[0]
    inactive.active = False
    add_concept(session, "NET-003", archived=True)  # 보관된 개념의 카드는 복습할 수 없다

    s = summary(session, NOW)
    # 밀린 복습 = 오늘 0시 전에 예정이었던 카드. 0시 10분 카드는 지금 복습할 카드지만 밀리지는 않았다
    assert (s.today.due, s.today.overdue, s.today.cards, s.today.concepts) == (2, 1, 6, 2)
    assert [d.cards for d in s.due_by_day] == [3, 0, 1, 0, 0, 0, 1]  # 오늘 칸에 밀린 카드도 넣고, 7일째(12/5)는 뺀다


def test_reviewed_today_and_volume_by_kst_day(session):
    card = add_concept(session, "NET-001")[0]
    add_log(session, card, 3, kst(11, 27, 23, 59))  # 어제 (UTC로는 같은 11월 27일)
    add_log(session, card, 1, kst(11, 28, 0, 1))
    add_log(session, card, 3, kst(11, 28, 0, 20))
    add_log(session, card, 4, kst(11, 1, 0, 0))     # 4주의 첫날
    add_log(session, card, 2, kst(10, 31, 23, 59))  # 4주 밖

    s = summary(session, NOW)
    assert s.today.reviewed == 2
    assert s.reviews_by_day[-1] == DayReviews(TODAY, again=1, hard=0, good=1, easy=0)
    assert s.reviews_by_day[-2] == DayReviews(date(2026, 11, 27), 0, 0, 1, 0)
    assert s.reviews_by_day[0] == DayReviews(date(2026, 11, 1), 0, 0, 0, 1)
    assert sum(d.again + d.hard + d.good + d.easy for d in s.reviews_by_day) == 4


@pytest.mark.parametrize(("days_ago", "streak"), [
    ([0, 1, 2, 4], 3),
    ([1, 2], 2),          # 오늘 아직 복습하지 않았으면 어제부터 센다
    ([2, 3], 0),
    ([], 0),
    (list(range(40)), 40),  # 4주보다 길어도 끝까지 센다
])
def test_streak_counts_consecutive_review_days(session, days_ago, streak):
    card = add_concept(session, "NET-001")[0]
    for n in days_ago:
        add_log(session, card, 3, kst(11, 28, 0, 5) - timedelta(days=n))
    assert summary(session, NOW).today.streak_days == streak


def test_weekly_error_rate_counts_again_and_hard(session):
    card = add_concept(session, "NET-001")[0]
    for rating in (1, 2, 3, 4):
        add_log(session, card, rating, kst(11, 22))
    add_log(session, card, 2, kst(11, 7, 23, 59))
    add_log(session, card, 3, kst(11, 8))

    weeks = summary(session, NOW).errors_by_week
    assert [(w.reviews, w.wrong) for w in weeks] == [(1, 1), (1, 0), (0, 0), (4, 2)]


def test_stages_and_categories_count_reviewable_cards(session):
    now = NOW.astimezone(UTC)  # py-fsrs는 UTC 시각만 받는다
    new_json, _ = fsrs.new_card(now)
    learning = fsrs.review(new_json, 3, now).card_json
    review = fsrs.review(new_json, 4, now).card_json
    routing = add_concept(session, "NET-001", cards=3, category="라우팅")
    routing[1].card_json = learning
    routing[2].card_json = {**review, "stability": 30.0}
    basics = add_concept(session, "NET-002", category="기본")
    basics[0].card_json = {**review, "stability": 5.0}
    add_concept(session, "NET-003", category=None)
    archived = add_concept(session, "NET-004", category="라우팅", archived=True)
    gone = add_concept(session, "NET-005", category="기본")[0]
    gone.active = False

    add_log(session, routing[0], 1, kst(11, 27))
    add_log(session, routing[1], 3, kst(10, 30))    # 최근 30일의 첫날
    add_log(session, routing[0], 1, kst(10, 29))    # 30일 밖
    add_log(session, basics[0], 2, kst(11, 20))
    add_log(session, archived[0], 1, kst(11, 27))   # 보관된 개념은 카테고리에 넣지 않는다
    add_log(session, gone, 1, kst(11, 27))          # 사라진 질문도

    s = summary(session, NOW)
    assert s.stages == Stages(new=2, learning=1, review=1, mature=1)
    assert s.categories == [
        CategoryStat("라우팅", Stages(new=1, learning=1, review=0, mature=1), reviews=2, wrong=1),
        CategoryStat(None, Stages(new=1, learning=0, review=0, mature=0), reviews=0, wrong=0),
        CategoryStat("기본", Stages(new=0, learning=0, review=1, mature=0), reviews=1, wrong=1),
    ]
    assert s.reviews_by_day[-2].again == 3  # 복습량은 남긴 기록을 모두 센다


def test_weak_concept_signals_and_thresholds(session):
    forgot = add_concept(session, "NET-001", cards=2)
    for card, at in ((forgot[0], kst(11, 20)), (forgot[1], kst(11, 27))):
        add_log(session, card, 1, at)                           # Again 2 → 잊음 (Again+Hard 2라 힘들게 떠올림은 아님)
    struggled = add_concept(session, "NET-002")[0]
    for rating in (1, 2, 2):
        add_log(session, struggled, rating, kst(11, 25))        # Again 1 + Hard 2 = 3 → 힘들게 떠올림
    fine = add_concept(session, "NET-003")[0]
    add_log(session, fine, 1, kst(11, 25))
    add_log(session, fine, 2, kst(11, 25))                      # 2회는 기준 아래
    low = add_concept(session, "NET-004")[0]
    add_evaluation(session, low, 59, kst(11, 20), missing=["왕복 경로"])
    add_evaluation(session, low, 40, kst(11, 26), missing=["다음 홉", "관리 거리"])
    add_evaluation(session, low, 60, kst(11, 26))               # 60점은 낮은 평가가 아니다
    add_evaluation(session, low, 30, kst(11, 26), kind="variant")  # 변형 질문은 세지 않는다
    one_low = add_concept(session, "NET-005")[0]
    add_evaluation(session, one_low, 10, kst(11, 26))
    add_evaluation(session, one_low, 10, kst(10, 29))           # 30일 밖
    old = add_concept(session, "NET-006")[0]
    add_log(session, old, 1, kst(10, 29))
    add_log(session, old, 1, kst(10, 29))
    archived = add_concept(session, "NET-007", archived=True)[0]
    for _ in range(3):
        add_log(session, archived, 1, kst(11, 27))

    weak = summary(session, NOW).weak_concepts
    assert [(w.concept_id, w.signals, w.again, w.hard, w.low_scores) for w in weak] == [
        ("NET-001", ["forgot"], 2, 0, 0),
        ("NET-002", ["struggled"], 1, 2, 0),
        ("NET-004", ["low_score"], 0, 0, 2),
    ]
    assert weak[0].lapses == [Lapse("NET-001 질문 1", 1, kst(11, 27)), Lapse("NET-001 질문 0", 1, kst(11, 20))]
    assert [(e.score, e.missing_points) for e in weak[2].low_evaluations] == [(40, ["다음 홉", "관리 거리"]), (59, ["왕복 경로"])]
    assert weak[2].last_reviewed_at is None and weak[2].next_due_at == NOW


def test_weak_concepts_order_by_again_then_low_scores_then_oldest_review(session):
    def weak_concept(cid, last_review, low_scores=0):
        card = add_concept(session, cid)[0]
        add_log(session, card, 1, kst(11, 10))
        add_log(session, card, 1, last_review)
        for _ in range(low_scores):
            add_evaluation(session, card, 30, kst(11, 26))
        return card

    weak_concept("NET-001", kst(11, 27))
    weak_concept("NET-002", kst(11, 20))
    weak_concept("NET-003", kst(11, 27), low_scores=2)
    more = weak_concept("NET-004", kst(11, 27))
    add_log(session, more, 1, kst(11, 12))
    add_log(session, more, 3, kst(11, 27, 20))  # Good도 마지막 복습이다

    weak = summary(session, NOW).weak_concepts
    assert [w.concept_id for w in weak] == ["NET-004", "NET-003", "NET-002", "NET-001"]
    assert weak[0].last_reviewed_at == kst(11, 27, 20)
