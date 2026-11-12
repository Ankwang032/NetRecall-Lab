import pytest

from integrations.sources.markdown import MarkdownParseError, parse_concept


def parse(text: str):
    return parse_concept(text, source_ref="network/x.md", fallback_title="x")


def fm(meta: str, body: str = "본문") -> str:
    return f"---\n{meta}\n---\n{body}\n"


FULL = """---
id: NET-010
title: Static Routing
category: Routing
keywords: [Routing Table, Next Hop, Default Route]
difficulty: 2
prerequisites: [NET-005]
related: [NET-001]
labs: [LAB-002]
questions:
  - 직접 쓴 질문
---

# Static Routing

본문 설명

## 질문

- 섹션 질문
"""


def test_parses_all_fields():
    c = parse(FULL)
    assert c.concept_id == "NET-010"
    assert c.title == "Static Routing"
    assert c.category == "Routing"
    assert c.keywords == ("Routing Table", "Next Hop", "Default Route")
    assert c.difficulty == 2
    assert c.prerequisites == ("NET-005",)
    assert c.related == ("NET-001",)
    assert c.lab_ids == ("LAB-002",)
    assert c.questions == ("직접 쓴 질문", "섹션 질문")
    assert c.source_type == "markdown"
    assert c.source_ref == "network/x.md"
    assert c.content_hash == c.compute_hash() != ""


def test_question_section_removed_from_body_but_later_sections_kept():
    c = parse(fm("id: NET-001", "앞 내용\n\n## 질문\n\n- Q1\n* Q2\n\n## 참고\n\n뒤 내용"))
    assert c.questions == ("Q1", "Q2")
    assert "Q1" not in c.content
    assert "## 참고" in c.content and "뒤 내용" in c.content


@pytest.mark.parametrize("text, message", [
    ("본문만 있음\n", "frontmatter"),
    (fm("id: [NET-001"), "YAML"),
    (fm("- a\n- b"), "key: value"),
    (fm("id: NET-001\ntittle: 오타"), "알 수 없는"),
    (fm("title: id 없음"), "id"),
    (fm("id: net-001"), "id"),
    (fm("id: NET-01"), "id"),
    (fm("id: NET-001\nlabs: [LAB-1]"), "실습 id"),
    (fm("id: NET-001\nprerequisites: [network]"), "개념 id"),
    (fm("id: NET-001\nrelated: [NET-001]"), "자기 자신"),
    (fm("id: NET-001\ncategory: 3"), "category"),
    (fm("id: NET-001\nkeywords: [SSH, 22]"), "keywords"),
    (fm("id: NET-001\nkeywords: [yes]"), "keywords"),
    (fm("id: NET-001\nkeywords: ['']"), "keywords"),
    (fm("id: NET-001", ""), "본문"),
    (fm("id: NET-001", "## 질문\n- Q만 있음"), "본문"),
])
def test_rejects_invalid_concepts(text, message):
    with pytest.raises(MarkdownParseError, match=message):
        parse(text)


@pytest.mark.parametrize("value", ["0", "6", "'2'", "true", "2.5"])
def test_rejects_invalid_difficulty(value):
    with pytest.raises(MarkdownParseError, match="difficulty"):
        parse(fm(f"id: NET-001\ndifficulty: {value}"))


def test_title_falls_back_to_h1_then_filename():
    assert parse(fm("id: NET-001", "# 본문 제목\n내용")).title == "본문 제목"
    assert parse(fm("id: NET-001", "내용")).title == "x"


def test_accepts_other_category_prefixes():
    assert parse(fm("id: LNX-001\nprerequisites: [CLD-123]")).concept_id == "LNX-001"


def test_single_string_is_treated_as_list_and_duplicates_removed():
    c = parse(fm("id: NET-001\nlabs: LAB-001\nkeywords: [OSI, OSI, ' TCP ']"))
    assert c.lab_ids == ("LAB-001",)
    assert c.keywords == ("OSI", "TCP")


def test_empty_frontmatter_values_are_allowed():
    c = parse(fm("id: NET-001\ncategory:\nkeywords:"))
    assert c.category is None and c.keywords == ()
