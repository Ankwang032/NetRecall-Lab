from datetime import timedelta

import pytest
from sqlalchemy import select

from backend.database import init_db, make_engine, make_session_factory
from backend.models import ReviewCard, ReviewLog
from backend.models.concept import utcnow
from backend.services.concept_store import sync_source
from backend.services.review_service import (
    CardNotFound, CardNotReviewable, due_cards, submit_review,
)
from integrations.sources.markdown import MarkdownConceptSource


@pytest.fixture
def session(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)
    with make_session_factory(engine)() as s:
        yield s
    engine.dispose()


@pytest.fixture
def root(tmp_path):
    d = tmp_path / "concepts"
    d.mkdir()
    return d


def write(root, rel, cid, questions="Q1, Q2, Q3"):
    path = root / rel
    path.write_text(f"---\nid: {cid}\nquestions: [{questions}]\n---\n본문\n", encoding="utf-8")
    return path


def sync(session, root):
    sync_source(session, MarkdownConceptSource(root))


def card_id(session, cid, question):
    return session.scalars(select(ReviewCard.id).where(
        ReviewCard.concept_id == cid, ReviewCard.question == question)).one()


def due_questions(session, now=None):
    return [(c.concept_id, c.question) for c, _ in due_cards(session, now or utcnow())]


def test_new_cards_are_due_immediately(session, root):
    write(root, "a.md", "NET-001")
    write(root, "b.md", "NET-002")
    sync(session, root)
    assert len(due_questions(session)) == 6
    assert due_questions(session, utcnow() - timedelta(hours=1)) == []
    _, concept = due_cards(session, utcnow())[0]
    assert concept.id == "NET-001"


def test_inactive_cards_and_archived_concepts_are_not_due(session, root):
    write(root, "a.md", "NET-001", questions="Q1, Q2, Q4")
    b = write(root, "b.md", "NET-002")
    sync(session, root)
    write(root, "a.md", "NET-001")  # Q4 제거, Q3 추가
    b.unlink()                       # NET-002 보관
    sync(session, root)
    assert sorted(due_questions(session)) == [("NET-001", "Q1"), ("NET-001", "Q2"), ("NET-001", "Q3")]


def test_review_moves_due_date_and_records_log(session, root):
    write(root, "a.md", "NET-001")
    sync(session, root)
    cid = card_id(session, "NET-001", "Q1")
    now = utcnow()

    log = submit_review(session, cid, 3, now)

    session.expire_all()  # DB에 저장된 값으로 확인한다 (SQLite는 시간대 없는 UTC로 돌려준다)
    card = session.get(ReviewCard, cid)
    assert card.due_at > now.replace(tzinfo=None)
    assert card.card_json["last_review"] is not None
    assert (log.card_id, log.rating, log.next_due_at) == (cid, 3, card.due_at)
    assert log.log_json["rating"] == 3
    assert ("NET-001", "Q1") not in due_questions(session, now)


def test_better_rating_is_scheduled_later(session, root):
    write(root, "a.md", "NET-001")
    sync(session, root)
    now = utcnow()
    again = submit_review(session, card_id(session, "NET-001", "Q1"), 1, now).next_due_at
    easy = submit_review(session, card_id(session, "NET-001", "Q2"), 4, now).next_due_at
    assert easy > again


def test_unknown_card_raises(session):
    with pytest.raises(CardNotFound):
        submit_review(session, 999, 3, utcnow())


def test_inactive_card_cannot_be_reviewed_but_keeps_history(session, root):
    write(root, "a.md", "NET-001")
    sync(session, root)
    cid = card_id(session, "NET-001", "Q3")
    submit_review(session, cid, 3, utcnow())
    write(root, "a.md", "NET-001", questions="Q1, Q2, Q4")
    sync(session, root)

    with pytest.raises(CardNotReviewable):
        submit_review(session, cid, 3, utcnow())
    assert len(session.scalars(select(ReviewLog).where(ReviewLog.card_id == cid)).all()) == 1


def test_archived_concept_cannot_be_reviewed(session, root):
    path = write(root, "a.md", "NET-001")
    sync(session, root)
    cid = card_id(session, "NET-001", "Q1")
    path.unlink()
    sync(session, root)
    with pytest.raises(CardNotReviewable):
        submit_review(session, cid, 3, utcnow())


def test_invalid_rating_changes_nothing(session, root):
    write(root, "a.md", "NET-001")
    sync(session, root)
    cid = card_id(session, "NET-001", "Q1")
    before = session.get(ReviewCard, cid).card_json
    with pytest.raises(ValueError):
        submit_review(session, cid, 5, utcnow())
    assert session.get(ReviewCard, cid).card_json == before
    assert session.scalars(select(ReviewLog)).all() == []
