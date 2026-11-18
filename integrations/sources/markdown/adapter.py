"""Markdown 폴더를 개념 소스로 읽는 어댑터.

형식 명세: docs/markdown-concept-format.md
"""
from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

import yaml

from ..base import FetchResult, RawConcept, SourceError, SourceItem

CONCEPT_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*-\d{3,}$")
LAB_ID_PATTERN = re.compile(r"^LAB-\d{3,}$")
FRONTMATTER_PATTERN = re.compile(r"\A---\n(.*?)\n---[ \t]*(?:\n(.*))?\Z", re.DOTALL)
H1_PATTERN = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
QUESTION_SECTION_PATTERN = re.compile(
    r"^##\s+질문[ \t]*\n(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL
)
LIST_ITEM_PATTERN = re.compile(r"^\s*[-*]\s+(.+?)\s*$", re.MULTILINE)

ALLOWED_KEYS = {
    "id", "title", "category", "keywords", "difficulty",
    "labs", "prerequisites", "related", "questions",
}
IGNORED_DIR_NAMES = {".git", ".obsidian", "node_modules", "templates"}


class MarkdownParseError(ValueError):
    pass


class MarkdownConceptSource:
    source_type = "markdown"

    def __init__(self, root: str | Path, max_file_bytes: int = 512_000) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise NotADirectoryError(f"개념 폴더가 없습니다: {self.root}")
        self.max_file_bytes = max_file_bytes

    # ---- ConceptSource 인터페이스 ----

    def list_items(self) -> Iterable[SourceItem]:
        for path in sorted(self.root.rglob("*.md")):
            rel = path.relative_to(self.root)
            if any(p in IGNORED_DIR_NAMES or p.startswith(("_", ".")) for p in rel.parts):
                continue
            if path.name.upper() == "README.MD":
                continue
            if path.is_symlink():  # 폴더 밖 파일을 읽지 않도록 심볼릭 링크는 건너뜀
                continue
            yield SourceItem(source_ref=rel.as_posix())

    def fetch(self, item: SourceItem) -> RawConcept:
        path = (self.root / item.source_ref).resolve()
        if self.root not in path.parents:
            raise MarkdownParseError("개념 폴더 밖의 경로입니다")
        if path.stat().st_size > self.max_file_bytes:
            raise MarkdownParseError(f"파일이 너무 큽니다 (최대 {self.max_file_bytes} bytes)")
        text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        return parse_concept(text, source_ref=item.source_ref, fallback_title=path.stem)

    def fetch_all(self) -> FetchResult:
        result = FetchResult()
        seen: dict[str, str] = {}
        for item in self.list_items():
            try:
                concept = self.fetch(item)
            except (MarkdownParseError, OSError, UnicodeDecodeError) as exc:
                result.errors.append(SourceError(item.source_ref, str(exc)))
                continue
            if concept.concept_id in seen:
                result.errors.append(SourceError(
                    item.source_ref,
                    f"id '{concept.concept_id}'가 {seen[concept.concept_id]}와 중복됩니다",
                ))
                continue
            seen[concept.concept_id] = item.source_ref
            result.concepts.append(concept)
        return result


# ---- 파싱 ----

def parse_concept(text: str, source_ref: str, fallback_title: str) -> RawConcept:
    meta, body = _split_frontmatter(text)

    unknown = set(meta) - ALLOWED_KEYS
    if unknown:
        raise MarkdownParseError(f"알 수 없는 frontmatter 키: {', '.join(sorted(unknown))}")

    concept_id = meta.get("id")
    if not isinstance(concept_id, str) or not CONCEPT_ID_PATTERN.match(concept_id):
        raise MarkdownParseError("id가 없거나 형식이 틀렸습니다 (예: NET-001)")

    title = meta.get("title")
    if title is None:
        h1 = H1_PATTERN.search(body)
        title = h1.group(1) if h1 else fallback_title
    if not isinstance(title, str) or not title.strip():
        raise MarkdownParseError("title이 비어 있습니다")

    difficulty = meta.get("difficulty")
    if difficulty is not None and (
        isinstance(difficulty, bool) or not isinstance(difficulty, int) or not 1 <= difficulty <= 5
    ):
        raise MarkdownParseError("difficulty는 1~5 정수여야 합니다")

    category = meta.get("category")
    if category is not None and not isinstance(category, str):
        raise MarkdownParseError("category는 문자열이어야 합니다")

    labs = _str_list(meta, "labs")
    for lab in labs:
        if not LAB_ID_PATTERN.match(lab):
            raise MarkdownParseError(f"실습 id 형식이 틀렸습니다: {lab}")

    prerequisites = _str_list(meta, "prerequisites")
    related = _str_list(meta, "related")
    for ref in prerequisites + related:
        if not CONCEPT_ID_PATTERN.match(ref):
            raise MarkdownParseError(f"개념 id 형식이 틀렸습니다: {ref}")
    if concept_id in prerequisites or concept_id in related:
        raise MarkdownParseError("자기 자신을 선수·연관 개념으로 지정할 수 없습니다")

    # 질문: frontmatter와 '## 질문' 섹션을 합치고, 섹션은 본문에서 제거
    questions = _str_list(meta, "questions")
    section = QUESTION_SECTION_PATTERN.search(body)
    if section:
        questions += LIST_ITEM_PATTERN.findall(section.group(1))
        body = body[: section.start()] + body[section.end():]

    content = body.strip()
    if not content:
        raise MarkdownParseError("본문이 비어 있습니다")

    concept = RawConcept(
        concept_id=concept_id,
        title=title.strip(),
        content=content,
        source_type="markdown",
        source_ref=source_ref,
        category=category,
        keywords=tuple(_dedupe(_str_list(meta, "keywords"))),
        difficulty=difficulty,
        lab_ids=tuple(_dedupe(labs)),
        prerequisites=tuple(_dedupe(prerequisites)),
        related=tuple(_dedupe(related)),
        questions=tuple(_dedupe(questions)),
    )
    return replace(concept, content_hash=concept.compute_hash())


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        raise MarkdownParseError("frontmatter(--- 블록)가 없습니다")
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise MarkdownParseError(f"frontmatter YAML 오류: {exc}") from exc
    if not isinstance(meta, dict):
        raise MarkdownParseError("frontmatter는 key: value 형식이어야 합니다")
    return meta, match.group(2) or ""


def _str_list(meta: dict[str, Any], key: str) -> list[str]:
    value = meta.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise MarkdownParseError(f"{key}는 문자열 목록이어야 합니다")
    return [v.strip() for v in value]


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
