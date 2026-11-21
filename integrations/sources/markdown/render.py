"""RawConcept를 Markdown 개념 파일로 쓴다. adapter.parse_concept의 반대 방향.

형식 명세: docs/markdown-concept-format.md
- frontmatter 키 순서: id, title, category, keywords, difficulty, prerequisites, related, labs. 빈 값은 쓰지 않는다.
- 문자열은 YAML이 필요할 때 따옴표로 감싼다 (`"22"`, `"yes"`, `"a: b"` 등이 글자로 읽히게).
- 본문이 `# 제목`으로 시작하지 않으면 붙인다. 질문은 맨 끝 `## 질문` 섹션에 쓴다.
"""
from __future__ import annotations

import re

import yaml

from ..base import RawConcept

STARTS_WITH_H1 = re.compile(r"\A#[ \t]+\S")


def render_concept(concept: RawConcept) -> str:
    meta: dict[str, object] = {"id": concept.concept_id, "title": concept.title}
    if concept.category:
        meta["category"] = concept.category
    if concept.keywords:
        meta["keywords"] = list(concept.keywords)
    if concept.difficulty is not None:
        meta["difficulty"] = concept.difficulty
    for key, values in (
        ("prerequisites", concept.prerequisites), ("related", concept.related), ("labs", concept.lab_ids),
    ):
        if values:
            meta[key] = list(values)
    front = "\n".join(f"{key}: {_yaml_value(value)}" for key, value in meta.items())

    body = concept.content.strip()
    if not STARTS_WITH_H1.match(body):
        body = f"# {concept.title}\n\n{body}".rstrip()
    text = f"---\n{front}\n---\n\n{body}\n"
    if concept.questions:
        items = "\n".join(f"- {' '.join(q.split())}" for q in concept.questions)  # 질문은 한 줄
        text += f"\n## 질문\n\n{items}\n"
    return text


def _yaml_value(value: object) -> str:
    # 키마다 한 줄. 목록은 [a, b] 모양 (한꺼번에 덤프하면 값이 모두 글자일 때 매핑 전체가 {…} 한 줄이 된다)
    dumped = yaml.safe_dump(value, allow_unicode=True, default_flow_style=True, width=1_000_000)
    return dumped.removesuffix("\n").removesuffix("\n...")
