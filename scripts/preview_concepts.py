"""Markdown 개념 폴더를 DB 반영 없이 검사한다.

사용법: python scripts/preview_concepts.py [폴더]   (기본: samples/concepts)
읽기 오류가 하나라도 있으면 종료 코드 1. 없는 선수·연관 개념 참조는 경고만 한다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backend.services.concept_sync import plan_sync
from integrations.sources.markdown import MarkdownConceptSource

DEFAULT_ROOT = Path(__file__).resolve().parent.parent / "samples" / "concepts"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Markdown 개념 폴더 미리보기")
    parser.add_argument("root", nargs="?", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args(argv)

    try:
        source = MarkdownConceptSource(args.root)
    except NotADirectoryError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1

    plan = plan_sync(source.source_type, source.fetch_all(), existing=[])

    print(f"개념 {len(plan.created)}개 ({source.root})")
    for c in plan.created:
        print(f"  {c.concept_id}  {c.title}  [{c.source_ref}]  질문 {len(c.questions)}개")

    for concept_id, ref in plan.dangling_refs:
        print(f"경고: {concept_id}가 없는 개념 {ref}를 참조합니다")

    for err in plan.errors:
        print(f"오류: {err.source_ref}: {err.message}", file=sys.stderr)

    return 1 if plan.errors else 0


if __name__ == "__main__":
    sys.exit(main())
