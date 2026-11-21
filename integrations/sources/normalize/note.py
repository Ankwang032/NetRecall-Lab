"""형식이 제각각인 노트(.md 파일, Notion 페이지)를 개념의 재료로 나눈다.

제목·본문·질문과, 노트에 이미 있던 frontmatter의 표준 키만 뽑는다. id·카테고리·키워드처럼
노트에 없는 값은 여기서 만들지 않는다. 가져오기에서는 AI가 채우고, Notion 동기화에서는
데이터베이스 속성에서 읽는다.

규칙
- 본문은 먼저 Notion 표기를 일반 Markdown으로 바꾼다 (notion_markdown.py).
- 제목: frontmatter `title` → 넘겨받은 제목(Notion 페이지 제목) → 본문 첫 `# 제목` → 파일 이름.
  앞에 붙은 이모지는 뗀다.
- 질문 섹션: 제목이 `질문` 또는 `이해 확인 질문`인 `##` 제목(앞 번호 허용, 예: `## 13. 이해 확인 질문`)부터
  다음 `#`·`##` 제목 전까지.
  - 맨 앞(들여쓰지 않은) 목록 항목(`-`, `*`, `+`, `1.`)과 `Q1.`로 시작하는 줄이 질문이다.
    Notion 토글은 목록 항목으로 바뀌므로 토글 제목이 질문이 되고, 들여쓴 토글 내용(답)은 버린다.
  - 앞의 `Q1.` 번호와 굵게(`**`)·취소선(`~~`) 표시는 뗀다. `###` 소제목과 다른 문장은 버린다.
  - 섹션 전체를 본문에서 지운다. frontmatter `questions`와 합치고 중복을 뺀다.
- 기존 frontmatter: 표준 키는 남긴다. Obsidian `tags`는 `keywords`가 없을 때 `keywords`로 쓴다.
  나머지 키는 버리고 경고한다. YAML을 읽지 못하면 frontmatter를 버리고 경고한다.
- 코드 블록 안은 제목·질문으로 보지 않는다 (bash 주석 `# ...` 등).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

import yaml

from ..markdown.adapter import ALLOWED_KEYS, FRONTMATTER_PATTERN
from .notion_markdown import iter_lines, notion_to_markdown

HEADING = re.compile(r"^#{1,2}[ \t]")
H1 = re.compile(r"^#[ \t]+(.+?)[ \t]*$")
QUESTION_HEADING = re.compile(r"^##[ \t]+(?:\d+[.)][ \t]*)?(?:질문|이해 확인 질문)[ \t]*$")
LIST_ITEM = re.compile(r"^(?:[-*+]|\d+[.)])[ \t]+(.+?)[ \t]*$")
Q_LINE = re.compile(r"^Q\d+[.):]?[ \t]+.+$")
Q_PREFIX = re.compile(r"^Q\d+[.):]?[ \t]+")
DIVIDER = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})$")
TITLE_SKIP = {"So", "Sk", "Mn", "Me", "Cf"}  # 이모지, 이모지 변형 선택자, 결합 문자


@dataclass(frozen=True)
class NoteParts:
    title: str
    body: str
    questions: tuple[str, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)  # title·questions를 뺀 표준 frontmatter 키
    warnings: tuple[str, ...] = ()


def split_note(text: str, *, fallback_title: str, title: str | None = None) -> NoteParts:
    warnings: list[str] = []
    text = text.removeprefix("﻿").replace("\r\n", "\n")
    meta, body = _frontmatter(text, warnings)

    body, unknown = notion_to_markdown(body)
    if unknown:
        warnings.append(f"Notion이 내보내지 못한 블록 {unknown}개를 뺐습니다")
    body, section_questions = _take_questions(body)

    questions = _meta_questions(meta.pop("questions", None), warnings) + section_questions
    meta_title = meta.pop("title", None)
    if meta_title is not None and not isinstance(meta_title, str):
        warnings.append("frontmatter title이 문자열이 아니어서 무시했습니다")
        meta_title = None
    chosen = next(
        (t for t in (meta_title, title, _first_h1(body), fallback_title) if t and _clean_title(t)),
        fallback_title,
    )
    return NoteParts(
        title=_clean_title(chosen),
        body=body,
        questions=tuple(dict.fromkeys(questions)),
        meta=meta,
        warnings=tuple(warnings),
    )


def _frontmatter(text: str, warnings: list[str]) -> tuple[dict[str, Any], str]:
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        return {}, text
    body = match.group(2) or ""
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        warnings.append("frontmatter YAML을 읽지 못해 뺐습니다")
        return {}, body
    if not isinstance(meta, dict):
        warnings.append("frontmatter가 key: value 형식이 아니어서 뺐습니다")
        return {}, body

    if "tags" in meta and "keywords" not in meta:
        tags = meta.pop("tags")
        tags = tags if isinstance(tags, list) else [tags]
        meta["keywords"] = [str(t).lstrip("#") for t in tags if t is not None]
    unknown = sorted(str(k) for k in meta if k not in ALLOWED_KEYS)
    if unknown:
        warnings.append(f"frontmatter의 알 수 없는 키를 뺐습니다: {', '.join(unknown)}")
    return {k: v for k, v in meta.items() if k in ALLOWED_KEYS}, body


def _meta_questions(value: Any, warnings: list[str]) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        warnings.append("frontmatter questions가 문자열 목록이 아니어서 무시했습니다")
        return []
    return [v.strip() for v in value if v.strip()]


def _take_questions(body: str) -> tuple[str, list[str]]:
    kept: list[str] = []
    questions: list[str] = []
    in_section = False
    for line, in_code in iter_lines(body):
        if not in_code and HEADING.match(line):
            in_section = bool(QUESTION_HEADING.match(line))
            if in_section:
                continue
        if not in_section:
            kept.append(line)
        elif not in_code and (question := _question(line)):
            questions.append(question)

    while kept and (not kept[-1].strip() or DIVIDER.match(kept[-1].strip())):
        kept.pop()  # 맨 끝 질문 섹션을 지우고 남은 구분선
    return "\n".join(kept).strip(), questions


def _question(line: str) -> str | None:
    match = LIST_ITEM.match(line)
    if match:
        text = match.group(1)
    elif Q_LINE.match(line):
        text = line
    else:
        return None
    text = text.replace("**", "").replace("~~", "").strip()
    return Q_PREFIX.sub("", text).strip() or None


def _first_h1(body: str) -> str | None:
    for line, in_code in iter_lines(body):
        if not in_code and (match := H1.match(line)):
            return match.group(1)
    return None


def _clean_title(title: str) -> str:
    title = title.strip()
    i = 0
    while i < len(title) and (title[i].isspace() or unicodedata.category(title[i]) in TITLE_SKIP):
        i += 1
    return title[i:].strip()
