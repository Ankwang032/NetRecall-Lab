import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.database import init_db, make_engine, make_session_factory
from backend.models import Concept, ConceptLab, ConceptRelation, ReviewCard
from backend.services import concept_store
from backend.services.concept_store import sync_source
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


def write(root, rel, cid, body="본문", extra="", questions="Q1, Q2, Q3"):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nid: {cid}\nquestions: [{questions}]\n{extra}---\n{body}\n",
                    encoding="utf-8")
    return path


def sync(session, root, **kw):
    return sync_source(session, MarkdownConceptSource(root), **kw)


def links(session, cid):
    rels = session.scalars(select(ConceptRelation).where(ConceptRelation.from_concept_id == cid))
    labs = session.scalars(select(ConceptLab).where(ConceptLab.concept_id == cid))
    return ({(r.relation_type, r.to_concept_id) for r in rels}, {l.scenario_id for l in labs})


def test_creates_concepts_with_relations_and_labs(session, root):
    write(root, "a.md", "NET-001", "# OSI\n본문\n\n## 질문\n- Q4",
          "keywords: [OSI]\nprerequisites: [NET-002]\nrelated: [NET-003]\nlabs: [LAB-001]\n")
    write(root, "b.md", "NET-002")
    plan = sync(session, root)
    assert plan.summary()["created"] == 2

    c = session.get(Concept, "NET-001")
    assert (c.title, c.keywords, c.seed_questions, c.archived) == ("OSI", ["OSI"], ["Q1", "Q2", "Q3", "Q4"], False)
    assert links(session, "NET-001") == (
        {("prerequisite", "NET-002"), ("related", "NET-003")}, {"LAB-001"})


def test_dangling_relation_and_unknown_lab_are_stored(session, root):
    write(root, "a.md", "NET-001", extra="prerequisites: [NET-999]\nlabs: [LAB-404]\n")
    plan = sync(session, root)
    assert plan.dangling_refs == [("NET-001", "NET-999")]
    assert links(session, "NET-001") == ({("prerequisite", "NET-999")}, {"LAB-404"})


def test_second_sync_changes_nothing(session, root):
    write(root, "a.md", "NET-001")
    sync(session, root)
    before = session.get(Concept, "NET-001").updated_at
    plan = sync(session, root)
    assert plan.unchanged == ["NET-001"] and not plan.has_changes
    assert session.get(Concept, "NET-001").updated_at == before


def test_content_change_updates_fields_and_replaces_links(session, root):
    write(root, "a.md", "NET-001", "옛 본문", "labs: [LAB-001, LAB-002]\nrelated: [NET-002]\n")
    sync(session, root)
    write(root, "a.md", "NET-001", "새 본문", "labs: [LAB-002]\n")
    plan = sync(session, root)
    assert [c.concept_id for c in plan.updated] == ["NET-001"]
    assert session.get(Concept, "NET-001").content == "새 본문"
    assert links(session, "NET-001") == (set(), {"LAB-002"})


def test_move_keeps_row_and_updates_location(session, root):
    path = write(root, "a.md", "NET-001", "# 제목\n본문", "labs: [LAB-001]\n")
    sync(session, root)
    created_at = session.get(Concept, "NET-001").created_at
    (root / "net").mkdir()
    path.rename(root / "net" / "moved.md")
    plan = sync(session, root)
    c = session.get(Concept, "NET-001")
    assert [r.concept_id for r in plan.relocated] == ["NET-001"]
    assert (c.source_ref, c.created_at) == ("net/moved.md", created_at)
    assert links(session, "NET-001") == (set(), {"LAB-001"})


def test_renaming_untitled_file_changes_title_but_keeps_row(session, root):
    # 제목이 없으면 파일 이름이 제목이 되므로, 이름 변경은 내용 변경으로 본다
    path = write(root, "a.md", "NET-001")
    sync(session, root)
    created_at = session.get(Concept, "NET-001").created_at
    path.rename(root / "renamed.md")
    plan = sync(session, root)
    c = session.get(Concept, "NET-001")
    assert [r.concept_id for r in plan.updated] == ["NET-001"]
    assert (c.title, c.source_ref, c.created_at) == ("renamed", "renamed.md", created_at)


def test_move_with_content_change_updates_location(session, root):
    path = write(root, "a.md", "NET-001", "옛")
    sync(session, root)
    path.unlink()
    write(root, "b.md", "NET-001", "새")
    sync(session, root)
    c = session.get(Concept, "NET-001")
    assert (c.source_ref, c.content) == ("b.md", "새")


def test_delete_archives_then_reappear_restores(session, root):
    path = write(root, "a.md", "NET-001", extra="labs: [LAB-001]\n")
    sync(session, root)
    path.unlink()
    sync(session, root)
    assert session.get(Concept, "NET-001").archived is True
    assert links(session, "NET-001") == (set(), {"LAB-001"})  # 보관해도 연결은 남는다

    write(root, "a.md", "NET-001", "돌아옴")
    plan = sync(session, root)
    c = session.get(Concept, "NET-001")
    assert [r.concept_id for r in plan.restored] == ["NET-001"]
    assert (c.archived, c.content) == (False, "돌아옴")


def test_unreadable_file_keeps_existing_concept(session, root):
    path = write(root, "a.md", "NET-001")
    sync(session, root)
    path.write_text("---\nid: NET-001\ntittle: 오타\n---\n본문\n", encoding="utf-8")
    plan = sync(session, root)
    assert plan.kept_due_to_error == ["NET-001"]
    assert session.get(Concept, "NET-001").archived is False


def test_other_source_concept_is_not_overwritten(session, root):
    session.add(Concept(id="NET-001", source_type="notion", source_ref="page-1",
                        content_hash="h", title="Notion 개념", content="원본"))
    session.commit()
    write(root, "a.md", "NET-001")
    plan = sync(session, root)
    assert "notion" in plan.errors[0].message
    c = session.get(Concept, "NET-001")
    assert (c.source_type, c.title) == ("notion", "Notion 개념")


def test_dry_run_writes_nothing(session, root):
    write(root, "a.md", "NET-001")
    plan = sync(session, root, dry_run=True)
    assert plan.summary()["created"] == 1
    assert session.scalars(select(Concept)).all() == []


def test_failure_during_apply_rolls_back_everything(session, root, monkeypatch):
    write(root, "a.md", "NET-001")
    write(root, "b.md", "NET-002")
    calls = []

    def failing(session_, raw):
        calls.append(raw.concept_id)
        if len(calls) == 2:
            raise RuntimeError("반영 중 실패")

    monkeypatch.setattr(concept_store, "_replace_links", failing)
    with pytest.raises(RuntimeError):
        sync(session, root)
    assert session.scalars(select(Concept)).all() == []
    assert session.scalars(select(ReviewCard)).all() == []


def test_sqlite_foreign_keys_are_enforced(session):
    session.add(ConceptLab(concept_id="NET-404", scenario_id="LAB-001"))
    with pytest.raises(IntegrityError):
        session.commit()


# ---- 복습 카드 ----

def cards(session, cid="NET-001"):
    """{질문: (카드 id, active)}"""
    rows = session.scalars(select(ReviewCard).where(ReviewCard.concept_id == cid))
    return {c.question: (c.id, c.active) for c in rows}


def test_new_concept_gets_one_due_card_per_question(session, root):
    write(root, "a.md", "NET-001")
    sync(session, root)
    rows = session.scalars(select(ReviewCard)).all()
    assert sorted(c.question for c in rows) == ["Q1", "Q2", "Q3"]
    assert all(c.active and c.card_json["state"] == 1 for c in rows)
    assert all(c.due_at == c.created_at for c in rows)  # 만들자마자 복습 대상


def test_changed_question_deactivates_old_card_and_adds_new_one(session, root):
    write(root, "a.md", "NET-001")
    sync(session, root)
    before = cards(session)
    write(root, "a.md", "NET-001", questions="Q1, Q2, Q4")
    sync(session, root)
    after = cards(session)
    assert after["Q1"] == before["Q1"] and after["Q2"] == before["Q2"]
    assert after["Q3"] == (before["Q3"][0], False)  # 이력 보존을 위해 행은 남는다
    assert after["Q4"][1] is True


def test_question_added_back_reactivates_same_card(session, root):
    write(root, "a.md", "NET-001")
    sync(session, root)
    q3_id = cards(session)["Q3"][0]
    write(root, "a.md", "NET-001", questions="Q1, Q2, Q4")
    sync(session, root)
    write(root, "a.md", "NET-001", questions="Q3, Q2, Q1")
    sync(session, root)
    after = cards(session)
    assert after["Q3"] == (q3_id, True)
    assert after["Q4"][1] is False


def test_reordering_questions_keeps_cards(session, root):
    write(root, "a.md", "NET-001")
    sync(session, root)
    before = cards(session)
    write(root, "a.md", "NET-001", questions="Q3, Q1, Q2")
    plan = sync(session, root)
    assert [c.concept_id for c in plan.updated] == ["NET-001"]
    assert cards(session) == before


def test_archive_and_restore_keep_cards(session, root):
    path = write(root, "a.md", "NET-001")
    sync(session, root)
    before = cards(session)
    path.unlink()
    sync(session, root)
    assert cards(session) == before  # 보관만으로는 카드를 건드리지 않는다
    write(root, "a.md", "NET-001", "돌아옴")
    sync(session, root)
    assert cards(session) == before


def test_move_keeps_cards(session, root):
    path = write(root, "a.md", "NET-001", "# 제목\n본문")
    sync(session, root)
    before = cards(session)
    path.rename(root / "moved.md")
    sync(session, root)
    assert cards(session) == before


def test_dry_run_creates_no_cards(session, root):
    write(root, "a.md", "NET-001")
    sync(session, root, dry_run=True)
    assert session.scalars(select(ReviewCard)).all() == []
