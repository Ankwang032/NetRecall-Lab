"""학습 자료 소스 공통 인터페이스.

모든 개념 소스(Notion, Markdown)는 이 모듈의 타입으로 결과를 돌려준다.
FSRS, AI, 실습 모듈은 RawConcept만 보고 소스 종류는 알지 못한다.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Iterable, Protocol, runtime_checkable


@dataclass(frozen=True)
class SourceItem:
    """소스 안의 개별 항목 위치. Markdown이면 상대 경로, Notion이면 page_id."""
    source_ref: str


@dataclass(frozen=True)
class RawConcept:
    """소스에서 읽어 정규화한 개념. DB 저장 직전 형태."""
    concept_id: str
    title: str
    content: str
    source_type: str
    source_ref: str
    category: str | None = None
    keywords: tuple[str, ...] = ()
    difficulty: int | None = None
    lab_ids: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    related: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()
    content_hash: str = field(default="", compare=False)

    def compute_hash(self) -> str:
        """학습 내용 기준 해시.

        위치(source_ref)와 소스 종류는 제외한다. 파일을 옮기거나 이름을 바꿔도
        내용이 같으면 '변경 없음'으로 본다.
        """
        payload = asdict(self)
        for key in ("content_hash", "source_ref", "source_type"):
            payload.pop(key)
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourceError:
    """한 항목의 읽기 실패. 동기화 전체를 멈추지 않고 모아서 보고한다."""
    source_ref: str
    message: str


@dataclass
class FetchResult:
    concepts: list[RawConcept] = field(default_factory=list)
    errors: list[SourceError] = field(default_factory=list)
    warnings: list[SourceError] = field(default_factory=list)  # 읽었지만 알릴 것 (빠진 블록, 끊긴 연결 등)


@runtime_checkable
class ConceptSource(Protocol):
    source_type: str

    def list_items(self) -> Iterable[SourceItem]: ...

    def fetch(self, item: SourceItem) -> RawConcept: ...

    def fetch_all(self) -> FetchResult: ...
