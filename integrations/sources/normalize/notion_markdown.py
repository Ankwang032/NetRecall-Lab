"""Notion-flavored Markdown(Notion API `markdown_version=v2`)을 일반 Markdown으로 바꾼다.

Notion은 콜아웃·토글 같은 블록을 XML 비슷한 태그로 내보낸다. 개념 본문은 일반 Markdown이어야
화면과 AI 프롬프트에서 똑같이 읽히므로 여기서 바꾼다. 일반 .md에 써도 해가 없다.
코드 블록과 인라인 코드 안은 건드리지 않는다.

블록
- <callout>, <quote> → 인용문(`> `)
- <toggle> → 목록 항목(`- 제목`) + 두 칸 들여쓴 내용. Notion의 Markdown 내보내기와 같은 모양이라,
  질문 섹션에서 "맨 앞 목록 항목 = 질문, 들여쓴 내용 = 답"으로 읽을 수 있다
- <toggle heading="h2"> → `## 제목` + 내용
- <columns>, <column>, <synced-block> → 태그만 지우고 내용은 남긴다
- <page>, <database>, <table-of-contents/>, <unknown/> → 지운다. unknown은 개수를 돌려준다
- <p />, <empty-block/> → 빈 줄
인라인
- <b> → **, <i> → *, <s> → ~~, <code> → `, <u>·<span> → 글자만, <mention> → 이름, <date/> → 날짜
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator

FENCE = re.compile(r"^(`{3,}|~{3,})")

CONTAINERS = ("callout", "quote", "toggle", "columns", "column", "synced-block-reference", "synced-block")
# 태그 이름 뒤는 공백이나 >. \b를 쓰면 <synced-block-reference>를 synced-block으로 읽는다
OPEN = re.compile(rf"^<({'|'.join(CONTAINERS)})(?=[\s>])([^>]*)>(.*)$")
CLOSE = re.compile(rf"^</({'|'.join(CONTAINERS)})>$")
HEADING_ATTR = re.compile(r'\bheading="h([1-4])"')
SKIPPED = re.compile(r"^<(page|database)\b[^>]*?(/?)>(.*)$")
REMOVED = re.compile(r"^<(table-of-contents|unknown)\b[^>]*/>$")
EMPTY = re.compile(r"^<(p|empty-block)\s*/>$")

# (?<!\\): Notion은 글자로 쓴 태그를 \<b>처럼 이스케이프한다
CODE_TAG = re.compile(r"(?<!\\)<code>(.*?)</code>")
CODE_SPAN = re.compile(r"(`+)(.+?)\1")
STYLE_TAGS = tuple(
    (re.compile(rf"(?<!\\)<{tag}>(.*?)</{tag}>"), mark) for tag, mark in (("b", "**"), ("i", "*"), ("s", "~~"))
)
PLAIN_TAGS = re.compile(r"(?<!\\)<(u|span)\b[^>]*>(.*?)</\1>")
MENTION = re.compile(r"(?<!\\)<mention\b[^>]*>(.*?)</mention>")
MENTION_EMPTY = re.compile(r"(?<!\\)<mention\b[^>]*/>")
DATE = re.compile(r"(?<!\\)<date\b([^>]*)/>")
ATTR = re.compile(r'(\w[\w-]*)="([^"]*)"')


@dataclass
class _Frame:
    tag: str
    prefix: str           # 안쪽 줄 앞에 붙일 문자열
    title: str | None     # 첫 줄을 제목으로 쓸 때의 모양: "- " 또는 "## ", 아니면 None


def iter_lines(text: str) -> Iterator[tuple[str, bool]]:
    """(줄, 코드 블록 안인지). 여는·닫는 펜스 줄도 코드 블록으로 본다."""
    fence: str | None = None
    for line in text.split("\n"):
        stripped = line.strip()
        if fence:
            if stripped and set(stripped) == {fence[0]} and len(stripped) >= len(fence):
                fence = None
            yield line, True
            continue
        match = FENCE.match(stripped)
        if match:
            fence = match.group(1)
        yield line, bool(match)


def notion_to_markdown(text: str) -> tuple[str, int]:
    """(일반 Markdown, 지운 <unknown> 블록 수)."""
    out: list[str] = []
    stack: list[_Frame] = []
    skip_until: str | None = None
    unknown = 0

    def emit(line: str) -> None:
        line = line.rstrip()
        if not line.strip(" >") and out and out[-1] == line:  # 빈 줄은 하나만
            return
        out.append(line)

    def prefix(frames: list[_Frame]) -> str:
        return "".join(f.prefix for f in frames)

    for line, in_code in iter_lines(text):
        if in_code:
            if stack and stack[-1].title:  # 제목 없이 코드가 먼저 나온 토글
                stack[-1].title = None
            emit(prefix(stack) + line)
            continue
        stripped = line.strip()

        if skip_until:
            if stripped.endswith(f"</{skip_until}>"):
                skip_until = None
            continue
        if match := SKIPPED.match(stripped):
            tag, self_closing, rest = match.groups()
            if not self_closing and not rest.endswith(f"</{tag}>"):
                skip_until = tag
            continue
        if REMOVED.match(stripped):
            unknown += stripped.startswith("<unknown")
            continue
        if EMPTY.match(stripped):
            emit(prefix(stack))
            continue

        if match := OPEN.match(stripped):
            tag, attrs, rest = match.groups()
            frame = _open_frame(tag, attrs)
            if stack and stack[-1].title:
                stack[-1].title = None
            closing = f"</{tag}>"
            if rest.endswith(closing):  # 한 줄짜리 블록
                stack.append(frame)
                _emit_content(rest[: -len(closing)], stack, emit, prefix)
                stack.pop()
                emit(prefix(stack))
                continue
            stack.append(frame)
            if rest.strip():
                _emit_content(rest, stack, emit, prefix)
            continue
        if match := CLOSE.match(stripped):
            tag = match.group(1)
            if any(f.tag == tag for f in stack):
                while out and out[-1] and not out[-1].strip(" >"):  # 블록 안 끝의 빈 줄
                    out.pop()
                while stack and stack.pop().tag != tag:
                    pass
                emit(prefix(stack))  # 블록이 끝나면 빈 줄. 다음 문단이 목록·인용문에 붙지 않게 한다
            continue

        if not stripped:
            emit(prefix(stack))
            continue
        _emit_content(line, stack, emit, prefix)

    while out and not out[-1].strip(" >"):
        out.pop()
    while out and not out[0].strip(" >"):
        out.pop(0)
    return "\n".join(out), unknown


def _open_frame(tag: str, attrs: str) -> _Frame:
    if tag in ("callout", "quote"):
        return _Frame(tag, "> ", None)
    if tag == "toggle":
        heading = HEADING_ATTR.search(attrs)
        if heading:
            return _Frame(tag, "", "#" * int(heading.group(1)) + " ")
        return _Frame(tag, "  ", "- ")
    return _Frame(tag, "", None)


def _emit_content(line: str, stack: list[_Frame], emit, prefix) -> None:
    top = stack[-1] if stack else None
    if top and top.title:
        emit(prefix(stack[:-1]) + top.title + inline(line.strip()))
        top.title = None
        return
    emit(prefix(stack) + inline(line))


def inline(line: str) -> str:
    """인라인 태그를 Markdown 표기로. 인라인 코드 안은 그대로 둔다."""
    line = CODE_TAG.sub(lambda m: _code_span(m.group(1)), line)
    parts: list[str] = []
    last = 0
    for match in CODE_SPAN.finditer(line):
        parts.append(_inline_tags(line[last:match.start()]))
        parts.append(match.group(0))
        last = match.end()
    parts.append(_inline_tags(line[last:]))
    return "".join(parts)


def _inline_tags(text: str) -> str:
    previous = None
    while previous != text:  # 태그가 겹쳐 있으면 바깥부터 한 겹씩 벗긴다
        previous = text
        text = PLAIN_TAGS.sub(r"\2", text)
        text = MENTION.sub(r"\1", text)
        text = MENTION_EMPTY.sub("", text)
        text = DATE.sub(_date, text)
        for pattern, mark in STYLE_TAGS:
            text = pattern.sub(lambda m, mark=mark: _wrap(m.group(1), mark), text)
    return text


def _wrap(text: str, mark: str) -> str:
    # Markdown 강조는 안쪽 끝에 공백이 있으면 깨지므로 공백을 바깥으로 뺀다
    core = text.strip()
    if not core:
        return text
    lead = text[: len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()):]
    return f"{lead}{mark}{core}{mark}{trail}"


def _code_span(text: str) -> str:
    return f"`` {text} ``" if "`" in text else f"`{text}`"


def _date(match: re.Match) -> str:
    attrs = dict(ATTR.findall(match.group(1)))
    start, end = attrs.get("start", ""), attrs.get("end")
    return f"{start}~{end}" if end else start
