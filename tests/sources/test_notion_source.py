"""NotionConceptSource: 데이터베이스 행 → 개념. 가짜 클라이언트로 Notion 없이 확인한다."""
import pytest

from integrations.sources.notion import NotionConceptSource, NotionError, PageMarkdown

DATABASE = "41fd0d99-b2e0-81ce-b08c-ff964280e202"

BODY = """<callout icon="💡" color="yellow_bg">
<b>한 줄 요약</b>: 경로를 직접 넣어요.
</callout>

## 1. 구성

본문이에요.

## 13. 이해 확인 질문

<toggle>
Q1. 정적 경로의 기본 관리 거리는?

1이에요.
</toggle>
<toggle>
Q2. 가장 큰 단점은?

자동으로 대응하지 못해요.
</toggle>
- 다음 홉과 출구 인터페이스의 차이는?
"""


def text(value, type_):
    return {"type": type_, type_: [{"plain_text": value}] if value else []}


def row(page_id, title, concept_id, **props):
    """속성 이름은 앱이 읽는 이름 그대로. 값이 dict이면 Notion 속성 원형으로 쓴다."""
    properties = {"이름": text(title, "title"), "개념 ID": text(concept_id, "rich_text")}
    simple = {
        "카테고리": lambda v: {"type": "select", "select": {"name": v} if v else None},
        "키워드": lambda v: {"type": "multi_select", "multi_select": [{"name": n} for n in v]},
        "실습": lambda v: {"type": "multi_select", "multi_select": [{"name": n} for n in v]},
        "난이도": lambda v: {"type": "number", "number": v},
        "선수 개념": lambda v: {"type": "relation", "relation": [{"id": i} for i in v], "has_more": False},
        "연관 개념": lambda v: {"type": "relation", "relation": [{"id": i} for i in v], "has_more": False},
    }
    for name, value in props.items():
        name = name.replace("_", " ")
        properties[name] = value if isinstance(value, dict) else simple[name](value)
    return {"object": "page", "id": page_id, "in_trash": False, "properties": properties}


class FakeClient:
    def __init__(self, rows, bodies=None, failing=()):
        self.rows = rows
        self.bodies = bodies or {}
        self.failing = set(failing)
        self.markdown_calls = []

    def database_rows(self, database):
        assert database == DATABASE
        if isinstance(self.rows, Exception):
            raise self.rows
        return self.rows

    def page_markdown(self, page_id):
        self.markdown_calls.append(page_id)
        if page_id in self.failing:
            raise NotionError("Notion 서버가 응답하지 않습니다 (502).")
        body = self.bodies.get(page_id, BODY)
        truncated = isinstance(body, tuple)
        return PageMarkdown(page_id, body[0] if truncated else body, truncated, ())


def fetch(rows, **kw):
    return NotionConceptSource(FakeClient(rows, **kw), f"https://app.notion.com/p/{DATABASE.replace('-', '')}").fetch_all()


def messages(items):
    return [i.message for i in items]


def test_row_becomes_concept_with_properties_body_and_questions():
    result = fetch([
        row("p1", "정적 라우팅", "NET-111", 카테고리="라우팅", 키워드=["Next Hop", "AD", "AD"], 난이도=3,
            실습=["LAB-002"], 선수_개념=["p2"], 연관_개념=[], 학습_상태={"type": "status", "status": {}}),
        row("p2", "라우팅 테이블 읽는 법", "NET-108"),
    ])
    assert result.errors == [] and result.warnings == []
    c = result.concepts[0]
    assert (c.concept_id, c.title, c.source_type, c.source_ref) == ("NET-111", "정적 라우팅", "notion", "p1")
    assert (c.category, c.keywords, c.difficulty, c.lab_ids) == ("라우팅", ("Next Hop", "AD"), 3, ("LAB-002",))
    assert c.prerequisites == ("NET-108",) and c.related == ()  # 연결한 행의 개념 ID
    assert c.questions == ("정적 경로의 기본 관리 거리는?", "가장 큰 단점은?", "다음 홉과 출구 인터페이스의 차이는?")
    assert c.content.startswith("> **한 줄 요약**: 경로를 직접 넣어요.")
    assert "이해 확인 질문" not in c.content and "1이에요" not in c.content  # 질문 섹션과 답은 본문에서 빠진다
    assert c.content_hash == c.compute_hash()


def test_same_rows_give_same_hash():
    rows = [row("p1", "정적 라우팅", "NET-111", 난이도=2)]
    assert fetch(rows).concepts[0].content_hash == fetch(rows).concepts[0].content_hash


def test_optional_properties_may_be_missing_or_empty():
    result = fetch([row("p1", "정적 라우팅", "NET-111", 카테고리=None, 난이도=None)])
    c = result.concepts[0]
    assert (c.category, c.keywords, c.difficulty, c.lab_ids, c.prerequisites) == (None, (), None, (), ())


@pytest.mark.parametrize("props, message", [
    ({"난이도": 6}, "난이도는 1~5 정수여야 합니다"),
    ({"난이도": 2.5}, "난이도는 1~5 정수여야 합니다"),
    ({"실습": ["lab-2"]}, "실습 id 형식이 틀렸습니다: lab-2 (예: LAB-002)"),
    ({"난이도": {"type": "select", "select": {"name": "3"}}}, "'난이도' 속성은 숫자 유형이어야 합니다"),
    ({"선수_개념": ["p1"]}, "자기 자신을 선수·연관 개념으로 연결할 수 없습니다"),
])
def test_invalid_row_is_error_with_title(props, message):
    result = fetch([row("p1", "정적 라우팅", "NET-111", **props)])
    assert result.concepts == []
    assert messages(result.errors) == [f"정적 라우팅: {message}"]
    assert result.errors[0].source_ref == "p1"  # 이미 저장된 개념은 동기화 계획이 보관하지 않고 유지한다


def test_missing_or_bad_concept_id_is_error():
    no_property = row("p1", "정적 라우팅", "NET-111")
    del no_property["properties"]["개념 ID"]
    result = fetch([no_property, row("p2", "IPv4 주소", "NET 1")])
    assert messages(result.errors) == [
        "정적 라우팅: '개념 ID' 속성이 없습니다",
        "IPv4 주소: 개념 ID가 없거나 형식이 틀렸습니다 (예: NET-101)",
    ]


def test_duplicate_concept_id_keeps_first_created_row():
    client_rows = [row("p1", "먼저 만든 행", "NET-111"), row("p2", "나중 행", "NET-111")]
    result = fetch(client_rows)
    assert [c.source_ref for c in result.concepts] == ["p1"]
    assert messages(result.errors) == ["나중 행: 개념 ID NET-111가 '먼저 만든 행' 행과 겹칩니다. 먼저 만든 행만 반영합니다"]


def test_relation_to_unreadable_row_is_dropped_with_warning():
    result = fetch([
        row("p1", "정적 라우팅", "NET-111", 선수_개념=["p2", "gone"], 연관_개념=["p2"]),
        row("p2", "개념 ID 없음", ""),
    ])
    c = result.concepts[0]
    assert c.prerequisites == () and c.related == ()
    assert messages(result.warnings) == [
        "정적 라우팅: 선수 개념으로 연결한 행 2개는 개념 ID를 읽지 못해 뺐습니다",
        "정적 라우팅: 연관 개념으로 연결한 행 1개는 개념 ID를 읽지 못해 뺐습니다",
    ]


def test_body_problems_are_warned_or_errors():
    result = fetch(
        [row("p1", "잘림", "NET-111"), row("p2", "빈 본문", "NET-112"), row("p3", "읽기 실패", "NET-113"),
         row("p4", "모르는 블록", "NET-114")],
        bodies={"p1": (BODY,), "p2": "## 질문\n- 하나\n- 둘\n- 셋\n", "p4": BODY + "\n<unknown/>\n"},
        failing={"p3"},
    )
    assert [c.concept_id for c in result.concepts] == ["NET-111", "NET-114"]
    assert messages(result.errors) == [
        "빈 본문: 본문이 비어 있습니다",
        "읽기 실패: Notion 서버가 응답하지 않습니다 (502).",
    ]
    assert messages(result.warnings) == [
        "잘림: Notion이 페이지를 끝까지 돌려주지 못했습니다 (블록이 너무 많음). 뒷부분이 빠졌을 수 있습니다",
        "모르는 블록: Notion이 내보내지 못한 블록 1개를 뺐습니다",
    ]


def test_database_failure_stops_the_whole_sync():
    with pytest.raises(NotionError):
        fetch(NotionError("Notion 페이지를 찾지 못했습니다."))


def test_bad_database_address_is_value_error():
    with pytest.raises(ValueError):
        NotionConceptSource(FakeClient([]), "개념 데이터베이스")


def test_fetch_one_item():
    source = NotionConceptSource(FakeClient([row("p1", "정적 라우팅", "NET-111")]), DATABASE)
    assert [i.source_ref for i in source.list_items()] == ["p1"]
    assert source.fetch(next(iter(source.list_items()))).concept_id == "NET-111"
