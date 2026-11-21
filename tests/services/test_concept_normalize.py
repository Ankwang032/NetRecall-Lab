import pytest

from backend.database import init_db, make_engine, make_session_factory
from backend.services.concept_extract import ConceptExtraction, KnownConcept
from backend.services.concept_normalize import convert_file, plan_files
from backend.services.concept_store import sync_source
from backend.services.concept_upload import MAX_FILE_BYTES, NewFile
from integrations.llm import LLMError
from integrations.sources.markdown import MarkdownConceptSource, parse_concept
from tests.fakes import FakeLLM


def concept_md(concept_id, title, category="Routing", questions="Q1, Q2, Q3"):
    return f"---\nid: {concept_id}\ntitle: {title}\ncategory: {category}\nquestions: [{questions}]\n---\n{title} 본문\n"


FREE_NOTE = """# 🛤️ 정적 라우팅

> **선행 지식**: Static Routing 기초

본문

## 이해 확인 질문

- Q1. 기본 관리 거리는?
- Q2. 돌아오는 경로가 필요한 이유는?
- Q3. 블랙홀 경로는 언제 쓰나?
"""

EXTRACTION = ConceptExtraction(
    category="Routing", keywords=["Static Route", "Next Hop"], difficulty=2,
    prerequisites=["NET-010", "NET-070"], related=["NET-050"], extra_questions=[],
)


@pytest.fixture
def session(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)
    with make_session_factory(engine)() as s:
        yield s
    engine.dispose()


@pytest.fixture
def root(tmp_path, session):
    """동기화된 NET-010, 보관된 NET-050, 아직 동기화하지 않은 NET-030이 있는 개념 폴더."""
    d = tmp_path / "concepts"
    d.mkdir()
    (d / "static.md").write_text(concept_md("NET-010", "Static Routing"), encoding="utf-8")
    (d / "old.md").write_text(concept_md("NET-050", "Old", category="Legacy"), encoding="utf-8")
    sync_source(session, MarkdownConceptSource(d))
    (d / "old.md").unlink()
    sync_source(session, MarkdownConceptSource(d))  # NET-050 보관
    (d / "ospf.md").write_text(concept_md("NET-030", "OSPF", category="Dynamic Routing"), encoding="utf-8")
    return d


# ---- plan ----

def test_standard_file_is_kept_and_free_note_gets_next_id(session, root):
    planned = plan_files(session, root, [
        NewFile("bgp.md", concept_md("NET-040", "BGP")),
        NewFile("static-note.md", FREE_NOTE),
    ], "NET")
    assert [(p.name, p.status, p.concept_id, p.title, p.error) for p in planned] == [
        ("bgp.md", "standard", "NET-040", "BGP", None),
        ("static-note.md", "convert", "NET-051", "정적 라우팅", None),  # 보관된 NET-050도 쓰인 번호
    ]


def test_note_ids_are_reserved_before_numbering(session, root):
    planned = plan_files(session, root, [
        NewFile("a.md", "A 본문"),
        NewFile("b.md", "---\nid: NET-090\n---\nB 본문"),  # 질문이 없어 standard가 아니지만 id는 쓴다
        NewFile("c.md", "C 본문"),
        NewFile("d.md", "---\nid: NET-1\n---\nD 본문"),
    ], "NET")
    assert [p.concept_id for p in planned] == ["NET-091", "NET-090", "NET-092", "NET-093"]
    assert planned[3].warnings == ["frontmatter id 형식이 틀려 새 id를 매겼습니다"]


def test_other_prefixes_start_from_one(session, root):
    (plan,) = plan_files(session, root, [NewFile("ls.md", "본문")], "LNX")
    assert plan.concept_id == "LNX-001"


def test_standard_format_with_too_few_questions_is_converted(session, root):
    (plan,) = plan_files(session, root, [NewFile("x.md", concept_md("NET-060", "X", questions="Q1"))], "NET")
    assert (plan.status, plan.concept_id) == ("convert", "NET-060")


def test_failed_and_rule_warnings(session, root):
    planned = plan_files(session, root, [
        NewFile("big.md", "가" * (MAX_FILE_BYTES // 3 + 1)),
        NewFile("empty.md", "## 질문\n- a\n- b\n- c"),
        NewFile("obsidian.md", "---\naliases: [x]\n---\n본문"),
    ], "NET")
    assert [(p.status, p.error) for p in planned] == [
        ("failed", f"파일이 너무 큽니다 (최대 {MAX_FILE_BYTES} bytes)"),
        ("failed", "본문이 비어 있습니다"),
        ("convert", None),
    ]
    assert planned[2].warnings == ["frontmatter의 알 수 없는 키를 뺐습니다: aliases"]


@pytest.mark.parametrize("prefix", ["", "net", "N-1"])
def test_bad_prefix(session, root, prefix):
    with pytest.raises(ValueError):
        plan_files(session, root, [NewFile("a.md", "본문")], prefix)


# ---- convert ----

def test_convert_renders_standard_markdown(session, root):
    llm = FakeLLM(EXTRACTION)
    batch = [KnownConcept("NET-070", "Route Summarization"), KnownConcept("NET-051", "정적 라우팅")]
    converted = convert_file(session, root, llm, NewFile("static-note.md", FREE_NOTE), "NET-051", batch)

    prompt = llm.calls[0]["prompt"]
    assert "- NET-010: Static Routing" in prompt  # DB
    assert "- NET-030: OSPF" in prompt  # 동기화 전 폴더 파일
    assert "- NET-070: Route Summarization" in prompt  # 함께 올린 파일
    assert "NET-050" not in prompt and "NET-051" not in prompt  # 보관된 개념, 자기 자신
    assert "[기존 카테고리]\nDynamic Routing, Routing" in prompt  # 보관된 개념의 Legacy는 빠진다

    c = parse_concept(converted.content, source_ref="static-note.md", fallback_title="x")
    assert (converted.concept_id, converted.title) == ("NET-051", "정적 라우팅")
    assert (c.concept_id, c.title, c.category, c.difficulty) == ("NET-051", "정적 라우팅", "Routing", 2)
    assert c.keywords == ("Static Route", "Next Hop")
    assert c.prerequisites == ("NET-010", "NET-070")
    assert c.related == ()
    assert c.questions == ("기본 관리 거리는?", "돌아오는 경로가 필요한 이유는?", "블랙홀 경로는 언제 쓰나?")
    assert c.content == "# 🛤️ 정적 라우팅\n\n> **선행 지식**: Static Routing 기초\n\n본문"
    assert converted.warnings == ["AI가 고른 연관 개념 중 알 수 없는 id를 뺐습니다: NET-050"]


def test_convert_errors(session, root):
    with pytest.raises(LLMError):
        convert_file(session, root, FakeLLM(LLMError("과부하")), NewFile("a.md", FREE_NOTE), "NET-051", [])
    with pytest.raises(ValueError, match="개념 id 형식"):
        convert_file(session, root, FakeLLM(), NewFile("a.md", FREE_NOTE), "NET-1", [])
    with pytest.raises(ValueError, match="본문이 비어"):
        convert_file(session, root, FakeLLM(), NewFile("a.md", "## 질문\n- a"), "NET-051", [])
