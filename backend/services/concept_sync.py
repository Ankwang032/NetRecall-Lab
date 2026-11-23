"""개념 동기화 계획 수립.

소스에서 읽은 결과와 DB의 현재 상태를 비교해 무엇을 바꿀지 '계획'만 만든다.
실제 DB 반영은 저장소 계층이 이 계획을 받아 한 트랜잭션으로 처리한다.
계획과 실행을 나누면 DB 없이 테스트할 수 있고, 반영 전에 미리보기도 가능하다.

규칙
- 개념의 식별자는 concept_id다. 파일 경로(source_ref)가 바뀌어도 같은 개념이다.
- 내용 해시가 같으면 갱신하지 않는다. 경로만 바뀌면 relocated로 처리한다.
- 원본에서 사라진 개념은 삭제하지 않고 archive한다. 복습 이력을 보존하기 위해서다.
- 읽기에 실패한 파일에 있던 개념은 archive하지 않는다. 오타 하나로 이력이 사라지면 안 된다.
- 다른 소스(Notion 등)가 이미 쓰고 있는 id는 덮어쓰지 않고 충돌로 보고한다.
  그 개념이 다른 소스에서 보관된 상태면 넘겨받는다(taken_over). 노트를 다른 소스로 옮겨도 복습 이력이 이어진다.
- 질문이 MIN_QUESTIONS개보다 적은 개념은 오류로 보고한다. 소스와 무관한 규칙이라 여기서 검사한다.
  이미 저장된 개념이면 읽기 오류처럼 기존 상태를 유지한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from integrations.sources.base import FetchResult, RawConcept, SourceError

# 질문 1개가 복습 카드 1장이 된다 (develop-memo D5)
MIN_QUESTIONS = 3


@dataclass(frozen=True)
class ExistingConcept:
    concept_id: str
    source_type: str
    source_ref: str
    content_hash: str
    archived: bool = False


@dataclass
class SyncPlan:
    source_type: str
    created: list[RawConcept] = field(default_factory=list)
    updated: list[RawConcept] = field(default_factory=list)
    relocated: list[RawConcept] = field(default_factory=list)
    restored: list[RawConcept] = field(default_factory=list)
    taken_over: list[RawConcept] = field(default_factory=list)  # 다른 소스에서 보관된 개념을 넘겨받음
    archived: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    kept_due_to_error: list[str] = field(default_factory=list)
    errors: list[SourceError] = field(default_factory=list)
    warnings: list[SourceError] = field(default_factory=list)  # 반영은 하되 알릴 것 (소스가 보고)
    dangling_refs: list[tuple[str, str]] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.created or self.updated or self.relocated
                    or self.restored or self.taken_over or self.archived)

    def summary(self) -> dict[str, int]:
        return {
            "created": len(self.created),
            "updated": len(self.updated),
            "relocated": len(self.relocated),
            "restored": len(self.restored),
            "taken_over": len(self.taken_over),
            "archived": len(self.archived),
            "unchanged": len(self.unchanged),
            "kept_due_to_error": len(self.kept_due_to_error),
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "dangling_refs": len(self.dangling_refs),
        }


def plan_sync(
    source_type: str,
    fetched: FetchResult,
    existing: list[ExistingConcept],
) -> SyncPlan:
    plan = SyncPlan(source_type=source_type, errors=list(fetched.errors), warnings=list(fetched.warnings))
    by_id = {e.concept_id: e for e in existing}
    failed_refs = {err.source_ref for err in fetched.errors}
    invalid_ids: set[str] = set()
    incoming_ids: set[str] = set()

    for concept in fetched.concepts:
        current = by_id.get(concept.concept_id)

        if len(concept.questions) < MIN_QUESTIONS:
            plan.errors.append(SourceError(
                concept.source_ref,
                f"질문이 {MIN_QUESTIONS}개 이상 필요합니다 (현재 {len(concept.questions)}개)",
            ))
            invalid_ids.add(concept.concept_id)
            continue

        if current and current.source_type != source_type and not current.archived:
            plan.errors.append(SourceError(
                concept.source_ref,
                f"id '{concept.concept_id}'는 이미 {current.source_type} 소스에서 사용 중입니다",
            ))
            continue

        incoming_ids.add(concept.concept_id)

        if current is None:
            plan.created.append(concept)
        elif current.source_type != source_type:
            plan.taken_over.append(concept)
        elif current.archived:
            plan.restored.append(concept)
        elif current.content_hash != concept.content_hash:
            plan.updated.append(concept)
        elif current.source_ref != concept.source_ref:
            plan.relocated.append(concept)
        else:
            plan.unchanged.append(concept.concept_id)

    for e in existing:
        if e.source_type != source_type or e.archived or e.concept_id in incoming_ids:
            continue
        if e.source_ref in failed_refs or e.concept_id in invalid_ids:
            plan.kept_due_to_error.append(e.concept_id)
        else:
            plan.archived.append(e.concept_id)

    # 선수·연관 개념이 실제로 존재하는지 확인 (경고만, 반영은 막지 않음)
    known_ids = (
        {e.concept_id for e in existing if not e.archived and e.concept_id not in plan.archived}
        | incoming_ids
    )
    for concept in fetched.concepts:
        if concept.concept_id not in incoming_ids:
            continue
        for ref in concept.prerequisites + concept.related:
            if ref not in known_ids:
                plan.dangling_refs.append((concept.concept_id, ref))

    return plan
