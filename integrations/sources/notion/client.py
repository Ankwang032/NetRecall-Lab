"""Notion REST API 클라이언트. 읽기만 한다. Notion-Version 2026-03-11.

쓰는 엔드포인트
- GET /v1/blocks/{id}/children: 하위 페이지 목록 (child_page 블록, 휴지통에 있는 것은 뺀다)
- GET /v1/pages/{id}: 페이지 제목
- GET /v1/pages/{id}/markdown?markdown_version=v2: 페이지 내용 (Notion-flavored Markdown).
  다음 API 버전에서 기본 형식이 v2로 바뀐다고 예고되어 있어 v2를 고정한다.

재시도 (Notion 요청 한도 문서 기준)
- 429·529: Retry-After 초만큼(최대 60초) 기다렸다가 다시 보낸다. 차단(public_api_request_blocked)이면 보내지 않는다.
- 500·502·503·504와 연결 오류: GET만 잠깐 기다렸다가 다시 보낸다.
오류는 모두 NotionError로 바꾸고, 화면에 그대로 보여 줄 수 있는 짧은 문구를 담는다.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx

NOTION_VERSION = "2026-03-11"
BASE_URL = "https://api.notion.com/v1"
TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 2
MAX_RETRY_AFTER = 60
RETRY_STATUSES = {429, 529}
GET_RETRY_STATUSES = {500, 502, 503, 504}

HEX_ID = re.compile(
    r"(?<![0-9a-fA-F])([0-9a-fA-F]{8})-?([0-9a-fA-F]{4})-?([0-9a-fA-F]{4})-?([0-9a-fA-F]{4})-?([0-9a-fA-F]{12})"
    r"(?![0-9a-fA-F])"
)


class NotionError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


@dataclass(frozen=True)
class ChildPage:
    page_id: str
    title: str


@dataclass(frozen=True)
class PageMarkdown:
    page_id: str
    markdown: str
    truncated: bool
    unknown_block_ids: tuple[str, ...]


def page_id_from(value: str) -> str:
    """페이지 주소나 id(대시 있음·없음)에서 대시 있는 id를 꺼낸다. 주소의 ?v=(보기 id) 같은 쿼리는 보지 않는다."""
    text = value.strip()
    if "://" in text:
        text = urlsplit(text).path
    matches = HEX_ID.findall(text)
    if not matches:
        raise ValueError("Notion 페이지 주소나 id가 아닙니다")
    return "-".join(matches[-1]).lower()


class NotionClient:
    def __init__(
        self, token: str, *, transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = httpx.Client(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION},
            timeout=TIMEOUT_SECONDS,
            transport=transport,
        )
        self._sleep = sleep

    def child_pages(self, page_id: str) -> list[ChildPage]:
        """페이지 바로 아래의 하위 페이지. 블록 순서(페이지에 보이는 순서)대로."""
        pages: list[ChildPage] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            data = self._request("GET", f"/blocks/{page_id_from(page_id)}/children", params=params)
            for block in data.get("results", []):
                if block.get("type") == "child_page" and not block.get("in_trash"):
                    pages.append(ChildPage(block["id"], block.get("child_page", {}).get("title", "")))
            cursor = data.get("next_cursor")
            if not data.get("has_more") or not cursor:
                return pages

    def page_title(self, page_id: str) -> str:
        data = self._request("GET", f"/pages/{page_id_from(page_id)}")
        for prop in data.get("properties", {}).values():
            if prop.get("type") == "title":
                return "".join(part.get("plain_text", "") for part in prop.get("title", []))
        return ""

    def page_markdown(self, page_id: str) -> PageMarkdown:
        page_id = page_id_from(page_id)
        data = self._request("GET", f"/pages/{page_id}/markdown", params={"markdown_version": "v2"})
        return PageMarkdown(
            page_id=data.get("id", page_id),
            markdown=data.get("markdown", ""),
            truncated=bool(data.get("truncated")),
            unknown_block_ids=tuple(data.get("unknown_block_ids", [])),
        )

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        for attempt in range(MAX_RETRIES + 1):
            last = attempt == MAX_RETRIES
            try:
                response = self._http.request(method, path, **kwargs)
            except httpx.HTTPError as exc:
                if method == "GET" and not last:
                    self._sleep(2 ** attempt)
                    continue
                raise NotionError("Notion에 연결하지 못했습니다. 네트워크를 확인하고 다시 시도하세요.") from exc

            if response.is_success:
                try:
                    return response.json()
                except ValueError as exc:
                    raise NotionError("Notion 응답을 읽지 못했습니다.", response.status_code) from exc
            wait = None if last else _retry_wait(method, response, attempt)
            if wait is None:
                raise _error(response)
            self._sleep(wait)
        raise AssertionError("unreachable")


def notion_from_env() -> NotionClient | None:
    """NOTION_TOKEN이 없으면 None. Notion 없이도 앱의 나머지 기능은 동작한다."""
    token = os.environ.get("NOTION_TOKEN")
    return NotionClient(token) if token else None


def _body(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _retry_wait(method: str, response: httpx.Response, attempt: int) -> float | None:
    status = response.status_code
    if status in RETRY_STATUSES:
        reason = (_body(response).get("additional_data") or {}).get("rate_limit_reason")
        if reason == "public_api_request_blocked":
            return None
        try:
            seconds = int(response.headers.get("Retry-After", "1"))
        except ValueError:
            seconds = 1
        return float(min(max(seconds, 0), MAX_RETRY_AFTER))
    if status in GET_RETRY_STATUSES and method == "GET":
        return float(2 ** attempt)
    return None


def _error(response: httpx.Response) -> NotionError:
    body = _body(response)
    status, code = response.status_code, body.get("code")
    if status == 401:
        message = "Notion 토큰이 올바르지 않습니다 (NOTION_TOKEN)."
    elif status == 403:
        message = "Notion 통합에 이 페이지를 읽을 권한이 없습니다."
    elif status == 404:
        message = "Notion 페이지를 찾지 못했습니다. 페이지의 연결(Connections)에 통합을 추가했는지 확인하세요."
    elif status in RETRY_STATUSES:
        message = "Notion 요청 한도를 넘었습니다. 잠시 뒤에 다시 시도하세요."
    elif status >= 500:
        message = f"Notion 서버가 응답하지 않습니다 ({status}). 잠시 뒤에 다시 시도하세요."
    else:
        message = f"Notion 요청이 실패했습니다 ({status} {code or ''}): {body.get('message', '')}".strip()
    return NotionError(message, status, code)
