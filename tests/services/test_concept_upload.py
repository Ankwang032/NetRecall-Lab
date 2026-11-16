import pytest
from sqlalchemy import select

from backend.database import init_db, make_engine, make_session_factory
from backend.models import Concept, ReviewCard
from backend.services.concept_store import sync_source
from backend.services.concept_upload import NewFile, check_files, list_folders, save_files
from integrations.sources.markdown import MarkdownConceptSource


def concept_md(concept_id="NET-020", questions="Q1, Q2, Q3", title="OSPF"):
    return f"---\nid: {concept_id}\ntitle: {title}\nquestions: [{questions}]\n---\n{title} 본문\n"


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
    (d / "network").mkdir(parents=True)
    (d / "network" / "static.md").write_text(concept_md("NET-010", title="Static Routing"), encoding="utf-8")
    return d


def errors_of(checks):
    return [c.errors for c in checks]


def test_valid_file_is_checked_without_writing(session, root):
    (check,) = check_files(session, root, "network", [NewFile("ospf.md", concept_md())])
    assert (check.path, check.concept_id, check.title, check.question_count) == ("network/ospf.md", "NET-020", "OSPF", 3)
    assert check.errors == []
    assert not (root / "network" / "ospf.md").exists()


@pytest.mark.parametrize("name", ["../x.md", "a/b.md", "a\\b.md", "x.txt", "X.MD", ".hidden.md", "_draft.md", "README.md"])
def test_bad_file_names_are_rejected(session, root, name):
    (check,) = check_files(session, root, "", [NewFile(name, concept_md())])
    assert check.errors


@pytest.mark.parametrize("content, message", [
    ("본문만 있음", "frontmatter"),
    (concept_md(questions="Q1, Q2"), "질문이 3개 이상"),  # 동기화와 같은 규칙
    (concept_md("NET-010"), "중복"),  # 폴더에 이미 있는 id
])
def test_invalid_content_is_reported(session, root, content, message):
    (check,) = check_files(session, root, "", [NewFile("new.md", content)])
    assert any(message in e for e in check.errors)


def test_existing_file_name_and_duplicates_in_batch(session, root):
    checks = check_files(session, root, "network", [
        NewFile("static.md", concept_md("NET-030")),  # 같은 이름의 파일이 있음
        NewFile("a.md", concept_md("NET-031")),
        NewFile("a.md", concept_md("NET-032")),  # 함께 올린 파일과 이름이 같음
        NewFile("b.md", concept_md("NET-031")),  # 함께 올린 파일과 id가 같음
    ])
    assert [bool(e) for e in errors_of(checks)] == [True, False, True, True]


def test_save_writes_files_and_syncs(session, root):
    sync_source(session, MarkdownConceptSource(root))
    checks, plan = save_files(session, root, "network", [NewFile("ospf.md", concept_md())])
    assert errors_of(checks) == [[]]
    assert (root / "network" / "ospf.md").read_text(encoding="utf-8") == concept_md()
    assert plan.summary()["created"] == 1
    assert session.get(Concept, "NET-020").source_ref == "network/ospf.md"
    cards = session.scalars(select(ReviewCard).where(ReviewCard.concept_id == "NET-020")).all()
    assert len(cards) == 3


def test_save_with_any_error_writes_nothing(session, root):
    checks, plan = save_files(session, root, "", [
        NewFile("ok.md", concept_md()), NewFile("bad.md", "frontmatter 없음"),
    ])
    assert plan is None and errors_of(checks)[1]
    assert not (root / "ok.md").exists()


def test_archived_concept_can_be_added_back(session, root):
    sync_source(session, MarkdownConceptSource(root))
    (root / "network" / "static.md").unlink()
    sync_source(session, MarkdownConceptSource(root))  # NET-010 보관
    _, plan = save_files(session, root, "", [NewFile("static.md", concept_md("NET-010", title="Static Routing"))])
    assert plan.summary()["restored"] == 1


def test_list_folders_skips_ignored(root):
    for name in (".obsidian", "_drafts", "templates", "network/sub"):
        (root / name).mkdir(parents=True)
    assert list_folders(root) == ["", "network", "network/sub"]


def test_unknown_folder_is_rejected(session, root):
    with pytest.raises(ValueError):
        check_files(session, root, "../outside", [NewFile("a.md", concept_md())])
