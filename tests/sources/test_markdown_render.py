from pathlib import Path

import pytest

from integrations.sources.base import RawConcept
from integrations.sources.markdown import parse_concept
from integrations.sources.markdown.render import render_concept

SAMPLES = Path(__file__).resolve().parents[2] / "samples" / "concepts"


def concept(**overrides) -> RawConcept:
    fields = dict(
        concept_id="NET-011", title="정적 라우팅", content="# 정적 라우팅\n\n본문", source_type="markdown",
        source_ref="x.md", questions=("질문 1", "질문 2", "질문 3"),
    )
    return RawConcept(**(fields | overrides))


def parse(text: str) -> RawConcept:
    return parse_concept(text, source_ref="x.md", fallback_title="x")


@pytest.mark.parametrize(
    "path", sorted(p for p in SAMPLES.rglob("*.md") if p.name != "README.md"), ids=lambda p: p.name,
)
def test_samples_round_trip(path):
    original = parse_concept(path.read_text(encoding="utf-8"), source_ref="x.md", fallback_title=path.stem)
    again = parse(render_concept(original))
    assert again == original
    assert again.content_hash == original.content_hash  # 다시 써도 동기화에서 '변경 없음'


def test_full_concept_text():
    text = render_concept(concept(
        title="정적 라우팅: 기초", category="라우팅", keywords=("SSH", "22", "yes", "2024-01-01"), difficulty=2,
        prerequisites=("NET-001", "NET-005"), related=("NET-020",), lab_ids=("LAB-002",),
    ))
    assert text == """---
id: NET-011
title: '정적 라우팅: 기초'
category: 라우팅
keywords: [SSH, '22', 'yes', '2024-01-01']
difficulty: 2
prerequisites: [NET-001, NET-005]
related: [NET-020]
labs: [LAB-002]
---

# 정적 라우팅

본문

## 질문

- 질문 1
- 질문 2
- 질문 3
"""
    parsed = parse(text)
    assert parsed.keywords == ("SSH", "22", "yes", "2024-01-01")  # YAML이 숫자·참거짓·날짜로 읽지 않는다
    assert parsed.title == "정적 라우팅: 기초"


def test_empty_fields_are_omitted_and_title_heading_is_added():
    text = render_concept(concept(content="본문만", questions=()))
    assert text == "---\nid: NET-011\ntitle: 정적 라우팅\n---\n\n# 정적 라우팅\n\n본문만\n"


def test_question_is_written_on_one_line():
    text = render_concept(concept(questions=("첫 줄\n둘째 줄", "  공백  많은   질문 ", "셋")))
    assert parse(text).questions == ("첫 줄 둘째 줄", "공백 많은 질문", "셋")
