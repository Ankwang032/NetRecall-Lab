from pathlib import Path

import pytest

from integrations.sources.markdown import parse_concept
from integrations.sources.normalize import notion_to_markdown, split_note

SAMPLES = Path(__file__).resolve().parents[2] / "samples" / "concepts"

# 사용자 Notion 노트의 틀(한 줄 요약 → 선행 지식 → 번호 섹션 → 이해 확인 질문 토글 → 체크리스트)을 흉내 낸 것
NOTION_NOTE = """<callout icon="💡" color="yellow_bg">
<b>한 줄 요약</b>: 정적 라우팅은 관리자가 경로를 <b>직접</b> 넣는 방식이에요.
</callout>

<callout icon="📌" color="gray_bg">
<b>선행 지식</b>: 라우팅 테이블 읽는 법, Longest Prefix Match
</callout>

<table-of-contents />

---

## 1. 정적 경로의 구성

| 형태 | 예시 (FRR) |
| --- | --- |
| 다음 홉 IP 지정 | <code>ip route 192.168.3.0/24 10.0.12.2</code> |

```bash
# 커널 라우팅 테이블
ip route add 192.168.3.0/24 via 10.0.12.2   # <b>는 그대로
```

<toggle>
더 알아보기

플로팅 정적 경로는 <i>백업</i> 경로예요.
</toggle>

<unknown url="https://app.notion.com/p/abc" alt="bookmark"/>

---

## 13. 이해 확인 질문

### 기초

<toggle>
Q1. 정적 경로의 기본 관리 거리는?

<b>1</b>이에요.
</toggle>

<toggle>
Q2. <code>10.1.0.0/22</code>로 요약할 때 블랙홀 경로가 필요한 이유는?

루프를 막기 위해서예요.
</toggle>

### 응용

<toggle>
Q3. r2에는 왜 정적 경로가 두 개 필요할까?

양쪽 LAN을 모르기 때문이에요.
</toggle>

---

## 14. 체크리스트

- [ ] 정적 경로의 구성 요소를 안다
"""

NOTION_BODY = """> **한 줄 요약**: 정적 라우팅은 관리자가 경로를 **직접** 넣는 방식이에요.

> **선행 지식**: 라우팅 테이블 읽는 법, Longest Prefix Match

---

## 1. 정적 경로의 구성

| 형태 | 예시 (FRR) |
| --- | --- |
| 다음 홉 IP 지정 | `ip route 192.168.3.0/24 10.0.12.2` |

```bash
# 커널 라우팅 테이블
ip route add 192.168.3.0/24 via 10.0.12.2   # <b>는 그대로
```

- 더 알아보기

  플로팅 정적 경로는 *백업* 경로예요.

---

## 14. 체크리스트

- [ ] 정적 경로의 구성 요소를 안다"""


def test_notion_note_is_split_into_title_body_and_questions():
    parts = split_note(NOTION_NOTE, fallback_title="x", title="정적 라우팅")
    assert parts.title == "정적 라우팅"
    assert parts.questions == (
        "정적 경로의 기본 관리 거리는?",
        "`10.1.0.0/22`로 요약할 때 블랙홀 경로가 필요한 이유는?",
        "r2에는 왜 정적 경로가 두 개 필요할까?",
    )
    assert parts.body == NOTION_BODY  # 질문 섹션과 답이 빠지고, 코드 블록은 그대로
    assert parts.meta == {}
    assert parts.warnings == ("Notion이 내보내지 못한 블록 1개를 뺐습니다",)


# ---- 인라인 ----

@pytest.mark.parametrize("text, expected", [
    ("<b>굵게</b> <i>기울임</i> <s>취소</s> <u>밑줄</u>", "**굵게** *기울임* ~~취소~~ 밑줄"),
    ('<span color="red"><span color="blue">겹친</span> 색</span>', "겹친 색"),
    ("<b><i>둘 다</i></b>", "***둘 다***"),
    ("앞<b> 공백 </b>뒤", "앞 **공백** 뒤"),
    ("`<b>코드</b>` 밖은 <b>굵게</b>", "`<b>코드</b>` 밖은 **굵게**"),
    ("<code>a`b</code>", "`` a`b ``"),
    ('<mention url="https://app.notion.com/p/1">정적 라우팅</mention> 참고', "정적 라우팅 참고"),
    ('<mention url="https://app.notion.com/p/1"/>끝', "끝"),
    ('<date start="2026-11-21" />', "2026-11-21"),
    ('<date start="2026-11-21" end="2026-11-22" />', "2026-11-21~2026-11-22"),
    (r"\<b>글자\</b>", r"\<b>글자\</b>"),  # 이스케이프한 태그는 글자
])
def test_inline_tags(text, expected):
    assert notion_to_markdown(text) == (expected, 0)


# ---- 블록 ----

@pytest.mark.parametrize("text, expected", [
    ('<callout icon="💡">\n요약\n\n- 항목\n</callout>\n다음', "> 요약\n>\n> - 항목\n\n다음"),
    ('<callout icon="💡">한 줄</callout>', "> 한 줄"),
    ("<quote>\n인용\n</quote>", "> 인용"),
    ("<toggle>\n제목\n\n내용\n\n- 하위\n</toggle>", "- 제목\n\n  내용\n\n  - 하위"),
    ("<toggle>한 줄 토글</toggle>", "- 한 줄 토글"),
    ('<toggle heading="h2">\n제목\n\n내용\n</toggle>', "## 제목\n\n내용"),
    ("<callout>\n<toggle>\n질문\n\n답\n</toggle>\n</callout>", "> - 질문\n>\n>   답"),
    ("<callout>\n```html\n<b>x</b>\n```\n</callout>", "> ```html\n> <b>x</b>\n> ```"),
    ('<columns>\n<column ratio="50">\n왼쪽\n</column>\n<column>\n오른쪽\n</column>\n</columns>', "왼쪽\n\n오른쪽"),
    ('<toggle>\n제목\n\n<synced-block-reference url="u">\n동기화\n</synced-block-reference>\n</toggle>\n밖',
     "- 제목\n\n  동기화\n\n밖"),
    ("앞\n\n\n\n뒤", "앞\n\n뒤"),
])
def test_blocks(text, expected):
    assert notion_to_markdown(text) == (expected, 0)


def test_child_pages_databases_and_unknown_blocks_are_removed():
    text = (
        '앞\n\n<page url="https://x">\n하위 페이지\n</page>\n\n'
        '<page url="https://y">한 줄 페이지</page>\n'
        '<database url="z" inline="true">\nDB\n</database>\n'
        "<table-of-contents />\n"
        '<unknown url="w" alt="embed"/>\n<unknown url="v" alt="bookmark"/>\n'
        "<p />\n뒤"
    )
    assert notion_to_markdown(text) == ("앞\n\n뒤", 2)


def test_code_block_is_not_converted():
    text = "```\n<callout>\n<b>x</b>\n</callout>\n```"
    assert notion_to_markdown(text) == (text, 0)


# ---- 질문 섹션 ----

def test_question_section_items():
    text = (
        "본문\n\n## 질문\n\n"
        "- 첫째\n* 둘째\n+ 셋째\n1. 넷째\n2) 다섯째\nQ6. 여섯째\n"
        "  - 들여쓴 답은 버린다\n"
        "- **Q7.** 굵은 번호\n"
        "### 소제목은 버린다\n"
        "그냥 문장도 버린다\n"
        "- 첫째\n"
    )
    parts = split_note(text, fallback_title="x")
    assert parts.questions == ("첫째", "둘째", "셋째", "넷째", "다섯째", "여섯째", "굵은 번호")
    assert parts.body == "본문"


@pytest.mark.parametrize("heading", ["## 질문", "## 이해 확인 질문", "## 13. 이해 확인 질문", "## 2) 질문"])
def test_question_heading_variants(heading):
    assert split_note(f"{heading}\n- q", fallback_title="x").questions == ("q",)


def test_other_headings_are_not_question_sections():
    parts = split_note("## 자주 묻는 질문\n- 이건 본문\n### 질문\n- 이것도", fallback_title="x")
    assert parts.questions == ()
    assert "이건 본문" in parts.body and "이것도" in parts.body


def test_question_section_ends_at_h1_or_h2_and_can_repeat():
    parts = split_note("## 질문\n- 하나\n# 다음 장\n내용\n## 2. 질문\n- 둘\n## 끝\n마무리", fallback_title="x")
    assert parts.questions == ("하나", "둘")
    assert parts.body == "# 다음 장\n내용\n## 끝\n마무리"


def test_code_blocks_are_not_headings_or_questions():
    text = "본문\n\n```md\n## 질문\n- 코드 안\n```\n\n## 질문\n```\n- 이것도 코드\n```\n- 진짜"
    parts = split_note(text, fallback_title="x")
    assert parts.questions == ("진짜",)
    assert parts.body == "본문\n\n```md\n## 질문\n- 코드 안\n```"


def test_trailing_divider_left_by_removed_section_is_dropped():
    assert split_note("본문\n\n---\n\n## 질문\n\n- a", fallback_title="x").body == "본문"


# ---- frontmatter와 제목 ----

def test_frontmatter_keeps_standard_keys_and_merges_questions():
    text = """---
title: 🛤️ 정적 라우팅
id: NET-020
tags: [routing, "#static"]
aliases: [static]
created: 2026-11-01
questions: [앞 질문]
---
# 다른 제목

본문

## 질문

- 섹션 질문
- 앞 질문
"""
    parts = split_note(text, fallback_title="x")
    assert parts.title == "정적 라우팅"
    assert parts.meta == {"id": "NET-020", "keywords": ["routing", "static"]}
    assert parts.questions == ("앞 질문", "섹션 질문")
    assert parts.body == "# 다른 제목\n\n본문"
    assert parts.warnings == ("frontmatter의 알 수 없는 키를 뺐습니다: aliases, created",)


def test_tags_are_dropped_when_keywords_exist():
    parts = split_note("---\nkeywords: [a]\ntags: [b]\n---\n본문", fallback_title="x")
    assert parts.meta == {"keywords": ["a"]}
    assert parts.warnings == ("frontmatter의 알 수 없는 키를 뺐습니다: tags",)


@pytest.mark.parametrize("text, warning", [
    ("---\nid: [NET-001\n---\n본문", "frontmatter YAML을 읽지 못해 뺐습니다"),
    ("---\n- 목록\n---\n본문", "frontmatter가 key: value 형식이 아니어서 뺐습니다"),
])
def test_broken_frontmatter_is_dropped_with_warning(text, warning):
    parts = split_note(text, fallback_title="x")
    assert parts.meta == {}
    assert parts.body == "본문"
    assert parts.warnings == (warning,)


@pytest.mark.parametrize("text, given, expected", [
    ("```bash\n# 주석\n```\n\n# 🌐 진짜 제목\n\n본문", None, "진짜 제목"),
    ("# 본문 제목\n\n본문", "Notion 제목", "Notion 제목"),
    ("---\ntitle: 앞 제목\n---\n# 본문 제목", "Notion 제목", "앞 제목"),
    ("본문만", None, "file-name"),
    ("# 🌐\n\n본문", None, "file-name"),  # 이모지만 있는 제목은 건너뛴다
])
def test_title_precedence(text, given, expected):
    assert split_note(text, fallback_title="file-name", title=given).title == expected


def test_bom_and_crlf():
    parts = split_note("﻿---\r\nid: NET-001\r\n---\r\n본문\r\n", fallback_title="x")
    assert parts.meta == {"id": "NET-001"}
    assert parts.body == "본문"


@pytest.mark.parametrize(
    "path", sorted(p for p in SAMPLES.rglob("*.md") if p.name != "README.md"), ids=lambda p: p.name,
)
def test_standard_files_split_like_markdown_parser(path):
    text = path.read_text(encoding="utf-8")
    concept = parse_concept(text, source_ref=path.name, fallback_title=path.stem)
    parts = split_note(text, fallback_title=path.stem)
    assert parts.title == concept.title
    assert parts.body == concept.content
    assert parts.questions == concept.questions
    assert parts.meta["id"] == concept.concept_id
    assert parts.warnings == ()
