"""Notion 페이지를 .md 파일 내용으로 가져온다. 저장하지 않는다.

가져온 내용은 `# 제목` + 페이지 Markdown(Notion-flavored)이다. 표준 형식으로 맞추기와 저장은 .md 파일 올리기와
같은 경로(concept_normalize → concept_upload)를 쓴다. Notion 표기는 정리 규칙(integrations/sources/normalize)이 바꾼다.
가져온 뒤에는 .md 파일이 원본이다. Notion에서 고친 내용은 다시 가져와야 반영된다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

from integrations.sources.notion import ChildPage, NotionClient, NotionError, page_id_from

UNSAFE_NAME = re.compile(r"[\s/\\:*?\"<>|#%&{}$!'@+`=\[\]();,~^]+")
MAX_STEM = 80


@dataclass
class NotionPages:
    parent: ChildPage
    pages: list[ChildPage]


@dataclass
class NotionFile:
    page_id: str
    title: str
    name: str
    content: str | None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


def list_pages(notion: NotionClient, parent: str) -> NotionPages:
    """페이지와 그 바로 아래 하위 페이지. 주소·id 형식이 틀리면 ValueError, Notion 오류는 NotionError."""
    parent_id = page_id_from(parent)
    return NotionPages(ChildPage(parent_id, notion.page_title(parent_id)), notion.child_pages(parent_id))


def fetch_files(notion: NotionClient, page_ids: Sequence[str]) -> list[NotionFile]:
    """페이지마다 .md 파일 내용. 한 페이지가 실패해도 나머지는 가져온다."""
    names: set[str] = set()
    files: list[NotionFile] = []
    for raw_id in page_ids:
        page_id = page_id_from(raw_id)
        try:
            title = notion.page_title(page_id).strip()
            page = notion.page_markdown(page_id)
        except NotionError as exc:
            files.append(NotionFile(page_id, "", "", None, error=str(exc)))
            continue
        warnings = []
        if page.truncated:
            warnings.append("Notion이 페이지를 끝까지 돌려주지 못했습니다 (블록이 너무 많음). 뒷부분이 빠졌을 수 있습니다")
        content = f"# {title}\n\n{page.markdown}" if title else page.markdown
        files.append(NotionFile(page_id, title, file_name_for(title, page_id, names), content, warnings))
    return files


def file_name_for(title: str, page_id: str, taken: set[str]) -> str:
    """제목으로 만든 .md 이름. 경로 문자와 공백은 -로 바꾼다. 같은 이름이 있으면 -2, -3을 붙인다."""
    stem = UNSAFE_NAME.sub("-", title).strip("-._")[:MAX_STEM].strip("-._")
    stem = stem or f"notion-{page_id.replace('-', '')[:8]}"
    name, n = f"{stem}.md", 2
    while name.lower() in taken or name.lower() == "readme.md":
        name, n = f"{stem}-{n}.md", n + 1
    taken.add(name.lower())
    return name
