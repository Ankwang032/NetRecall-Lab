"""Notion 데이터베이스 동기화 소스. 행 하나가 개념 하나다. AI를 쓰지 않는다.

동기화할 때마다 결과가 같아야 질문과 카드가 흔들리지 않는다. 규칙은 docs/notion-concept-source.md.
- 속성은 이름으로 찾는다. 유형이 표와 다르면 그 행은 오류다. 표에 없는 속성은 읽지 않는다
  (학습 상태 같은 개인 속성을 둘 수 있게. Markdown frontmatter가 모르는 키를 오류로 보는 것과 다르다).
- 선수·연관 개념은 연결한 행의 개념 ID로 바꾼다. 연결한 행을 찾지 못하면 그 연결만 빼고 경고한다.
- 본문은 페이지 Markdown을 정리 규칙(normalize.split_note)으로 정리하고, 질문 섹션에서 질문을 읽는다.
- 같은 개념 ID가 여러 행에 있으면 먼저 만든 행만 반영한다.
- 데이터베이스 조회가 실패하면 NotionError로 동기화 전체를 멈춘다. 모든 개념이 보관되면 안 되기 때문이다.
  행 하나의 본문을 읽지 못하면 그 행만 오류이고, 이미 저장된 개념은 보관하지 않고 유지된다.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable

from integrations.sources.base import FetchResult, RawConcept, SourceError, SourceItem
from integrations.sources.markdown.adapter import CONCEPT_ID_PATTERN, LAB_ID_PATTERN
from integrations.sources.normalize import split_note

from .client import NotionClient, NotionError, page_id_from

# 속성 이름 → Notion 유형
PROPERTIES = {
    "이름": "title",
    "개념 ID": "rich_text",
    "카테고리": "select",
    "키워드": "multi_select",
    "난이도": "number",
    "선수 개념": "relation",
    "연관 개념": "relation",
    "실습": "multi_select",
}
REQUIRED = ("이름", "개념 ID")
TYPE_LABELS = {
    "title": "제목", "rich_text": "텍스트", "select": "선택", "multi_select": "다중 선택",
    "number": "숫자", "relation": "관계형",
}


class RowError(ValueError):
    """행 하나를 개념으로 바꿀 수 없음. 그 행만 오류로 보고한다."""


@dataclass(frozen=True)
class _Row:
    page_id: str
    title: str
    concept_id: str
    category: str | None
    keywords: tuple[str, ...]
    difficulty: int | None
    labs: tuple[str, ...]
    prerequisite_pages: tuple[str, ...]
    related_pages: tuple[str, ...]
    warnings: tuple[str, ...]


class NotionConceptSource:
    source_type = "notion"

    def __init__(self, client: NotionClient, database: str) -> None:
        """database는 데이터베이스 주소나 id. 형식이 틀리면 ValueError."""
        self._client = client
        self._database = page_id_from(database)

    def list_items(self) -> Iterable[SourceItem]:
        return [SourceItem(row["id"]) for row in self._client.database_rows(self._database)]

    def fetch(self, item: SourceItem) -> RawConcept:
        """선수·연관 개념을 개념 ID로 바꾸려면 모든 행이 필요해 전체를 읽는다."""
        result = self.fetch_all()
        for concept in result.concepts:
            if concept.source_ref == item.source_ref:
                return concept
        message = next((e.message for e in result.errors if e.source_ref == item.source_ref), "행을 찾지 못했습니다")
        raise RowError(message)

    def fetch_all(self) -> FetchResult:
        rows = self._client.database_rows(self._database)  # 실패하면 NotionError로 멈춘다
        result = FetchResult()
        parsed: list[_Row] = []
        for row in rows:
            try:
                parsed.append(_parse_row(row))
            except RowError as exc:
                result.errors.append(SourceError(row["id"], _labelled(_title_of(row), str(exc))))

        ids_by_page = {r.page_id: r.concept_id for r in parsed}
        first_title: dict[str, str] = {}
        for r in parsed:  # 만든 순서다
            if r.concept_id in first_title:
                result.errors.append(SourceError(r.page_id, _labelled(
                    r.title, f"개념 ID {r.concept_id}가 '{first_title[r.concept_id]}' 행과 겹칩니다. 먼저 만든 행만 반영합니다",
                )))
                continue
            first_title[r.concept_id] = r.title
            try:
                concept, warnings = self._concept(r, ids_by_page)
            except (RowError, NotionError) as exc:
                result.errors.append(SourceError(r.page_id, _labelled(r.title, str(exc))))
                continue
            result.concepts.append(concept)
            result.warnings += [SourceError(r.page_id, _labelled(r.title, w)) for w in warnings]
        return result

    def _concept(self, row: _Row, ids_by_page: dict[str, str]) -> tuple[RawConcept, list[str]]:
        warnings = list(row.warnings)
        prerequisites = _concept_ids(row.prerequisite_pages, ids_by_page, "선수 개념", warnings)
        related = _concept_ids(row.related_pages, ids_by_page, "연관 개념", warnings)
        if row.concept_id in prerequisites or row.concept_id in related:
            raise RowError("자기 자신을 선수·연관 개념으로 연결할 수 없습니다")

        page = self._client.page_markdown(row.page_id)
        if page.truncated:
            warnings.append("Notion이 페이지를 끝까지 돌려주지 못했습니다 (블록이 너무 많음). 뒷부분이 빠졌을 수 있습니다")
        parts = split_note(page.markdown, fallback_title=row.title, title=row.title)
        warnings += parts.warnings
        content = parts.body.strip()
        if not content:
            raise RowError("본문이 비어 있습니다")

        concept = RawConcept(
            concept_id=row.concept_id,
            title=parts.title,
            content=content,
            source_type=self.source_type,
            source_ref=row.page_id,
            category=row.category,
            keywords=row.keywords,
            difficulty=row.difficulty,
            lab_ids=row.labs,
            prerequisites=prerequisites,
            related=related,
            questions=parts.questions,
        )
        return replace(concept, content_hash=concept.compute_hash()), warnings


def _parse_row(row: dict[str, Any]) -> _Row:
    props = row.get("properties", {})
    warnings: list[str] = []

    def prop(name: str) -> dict[str, Any] | None:
        value = props.get(name)
        if value is None:
            if name in REQUIRED:
                raise RowError(f"'{name}' 속성이 없습니다")
            return None
        expected = PROPERTIES[name]
        if value.get("type") != expected:
            raise RowError(f"'{name}' 속성은 {TYPE_LABELS[expected]} 유형이어야 합니다")
        return value

    title = _plain(prop("이름")["title"]).strip()  # type: ignore[index]
    if not title:
        raise RowError("이름이 비어 있습니다")
    concept_id = _plain(prop("개념 ID")["rich_text"]).strip()  # type: ignore[index]
    if not CONCEPT_ID_PATTERN.match(concept_id):
        raise RowError("개념 ID가 없거나 형식이 틀렸습니다 (예: NET-101)")

    category = ((prop("카테고리") or {}).get("select") or {}).get("name")
    difficulty = (prop("난이도") or {}).get("number")
    if difficulty is not None:
        if difficulty != int(difficulty) or not 1 <= difficulty <= 5:
            raise RowError("난이도는 1~5 정수여야 합니다")
        difficulty = int(difficulty)
    labs = _names(prop("실습"))
    for lab in labs:
        if not LAB_ID_PATTERN.match(lab):
            raise RowError(f"실습 id 형식이 틀렸습니다: {lab} (예: LAB-002)")

    return _Row(
        page_id=row["id"],
        title=title,
        concept_id=concept_id,
        category=category,
        keywords=_names(prop("키워드")),
        difficulty=difficulty,
        labs=labs,
        prerequisite_pages=_relation(prop("선수 개념"), "선수 개념", warnings),
        related_pages=_relation(prop("연관 개념"), "연관 개념", warnings),
        warnings=tuple(warnings),
    )


def _plain(rich_text: list[dict[str, Any]]) -> str:
    return "".join(part.get("plain_text", "") for part in rich_text)


def _names(value: dict[str, Any] | None) -> tuple[str, ...]:
    names = (option.get("name", "").strip() for option in (value or {}).get("multi_select", []))
    return tuple(dict.fromkeys(n for n in names if n))


def _relation(value: dict[str, Any] | None, label: str, warnings: list[str]) -> tuple[str, ...]:
    if not value:
        return ()
    if value.get("has_more"):
        warnings.append(f"{label} 연결이 너무 많아 Notion이 앞부분만 돌려줬습니다")
    return tuple(item["id"] for item in value.get("relation", []))


def _concept_ids(pages: tuple[str, ...], ids_by_page: dict[str, str], label: str, warnings: list[str]) -> tuple[str, ...]:
    ids: list[str] = []
    missing = 0
    for page_id in pages:
        concept_id = ids_by_page.get(page_id)
        if concept_id is None:
            missing += 1
        else:
            ids.append(concept_id)
    if missing:
        warnings.append(f"{label}으로 연결한 행 {missing}개는 개념 ID를 읽지 못해 뺐습니다")  # label은 "…개념"
    return tuple(dict.fromkeys(ids))


def _title_of(row: dict[str, Any]) -> str:
    value = row.get("properties", {}).get("이름") or {}
    return _plain(value.get("title", [])).strip() if value.get("type") == "title" else ""


def _labelled(title: str, message: str) -> str:
    return f"{title}: {message}" if title else message
