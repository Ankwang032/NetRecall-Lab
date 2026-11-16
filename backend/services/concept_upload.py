"""Markdown 개념 파일 올리기: 저장 전 검사 → 개념 폴더에 저장 → 동기화.

검사를 통과하지 못한 파일이 하나라도 있으면 아무것도 저장하지 않는다. 형식이 틀린 파일이
개념 폴더에 남으면 동기화할 때마다 오류로 보고되기 때문이다.
질문 개수, 다른 소스와의 id 충돌은 동기화 계획(plan_sync)을 그대로 돌려 같은 규칙으로 검사한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from backend.services.concept_store import load_existing, sync_source
from backend.services.concept_sync import SyncPlan, plan_sync
from integrations.sources.markdown import MarkdownConceptSource
from integrations.sources.markdown.adapter import IGNORED_DIR_NAMES, MarkdownParseError, parse_concept

MAX_FILE_BYTES = 512_000  # MarkdownConceptSource 기본 상한과 같다


@dataclass(frozen=True)
class NewFile:
    name: str
    content: str


@dataclass
class FileCheck:
    name: str
    path: str  # 개념 폴더 기준 상대 경로
    concept_id: str | None = None
    title: str | None = None
    question_count: int = 0
    errors: list[str] = field(default_factory=list)


def list_folders(root: Path) -> list[str]:
    """파일을 저장할 수 있는 폴더. 개념 폴더 기준 상대 경로이고, 개념 폴더 자체는 ""."""
    folders = [""]
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if path.is_dir() and not path.is_symlink() and not _skipped(rel.parts):
            folders.append(rel.as_posix())
    return folders


def check_files(session: Session, root: Path, folder: str, files: list[NewFile]) -> list[FileCheck]:
    """저장하지 않고 검사만 한다. 폴더가 목록에 없으면 ValueError."""
    if folder not in list_folders(root):
        raise ValueError(f"개념 폴더 안의 폴더가 아닙니다: {folder}")

    fetched = MarkdownConceptSource(root).fetch_all()
    seen_ids = {c.concept_id: c.source_ref for c in fetched.concepts}
    taken_paths: set[str] = set()
    parsed: dict[str, FileCheck] = {}
    checks: list[FileCheck] = []

    for f in files:
        path = f"{folder}/{f.name}" if folder else f.name
        check = FileCheck(name=f.name, path=path)
        checks.append(check)

        if error := _name_error(f.name):
            check.errors.append(error)
            continue
        if path in taken_paths or (root / path).exists():
            check.errors.append("같은 이름의 파일이 이미 있습니다")
            continue
        taken_paths.add(path)
        if len(f.content.encode("utf-8")) > MAX_FILE_BYTES:
            check.errors.append(f"파일이 너무 큽니다 (최대 {MAX_FILE_BYTES} bytes)")
            continue

        text = f.content.removeprefix("﻿").replace("\r\n", "\n")  # 어댑터와 같은 정규화
        try:
            concept = parse_concept(text, source_ref=path, fallback_title=Path(f.name).stem)
        except MarkdownParseError as exc:
            check.errors.append(str(exc))
            continue
        check.concept_id, check.title = concept.concept_id, concept.title
        check.question_count = len(concept.questions)

        if concept.concept_id in seen_ids:
            check.errors.append(f"id '{concept.concept_id}'가 {seen_ids[concept.concept_id]}와 중복됩니다")
            continue
        seen_ids[concept.concept_id] = path
        fetched.concepts.append(concept)
        parsed[path] = check

    plan = plan_sync(MarkdownConceptSource.source_type, fetched, load_existing(session))
    session.rollback()  # load_existing이 연 읽기 트랜잭션을 끝낸다
    for err in plan.errors:
        if err.source_ref in parsed:
            parsed[err.source_ref].errors.append(err.message)
    return checks


def save_files(
    session: Session, root: Path, folder: str, files: list[NewFile],
) -> tuple[list[FileCheck], SyncPlan | None]:
    """모두 통과하면 저장하고 동기화한다. 하나라도 실패하면 저장하지 않고 계획 없이(None) 돌려준다."""
    checks = check_files(session, root, folder, files)
    if any(c.errors for c in checks):
        return checks, None
    for f, check in zip(files, checks):
        with (root / check.path).open("x", encoding="utf-8", newline="") as out:  # 덮어쓰지 않는다
            out.write(f.content)
    return checks, sync_source(session, MarkdownConceptSource(root))


def _name_error(name: str) -> str | None:
    if any(ch in name for ch in "/\\\0") or name in ("", ".", ".."):
        return "파일 이름에 경로를 넣을 수 없습니다"
    if not name.endswith(".md"):
        return ".md 파일만 올릴 수 있습니다"
    if _skipped([name]) or name.upper() == "README.MD":
        return "동기화에서 건너뛰는 이름입니다 (README.md, . 이나 _로 시작하는 이름)"
    if len(name) > 200:
        return "파일 이름이 너무 깁니다"
    return None


def _skipped(parts) -> bool:
    # MarkdownConceptSource.list_items와 같은 건너뛰기 규칙
    return any(p in IGNORED_DIR_NAMES or p.startswith(("_", ".")) for p in parts)
