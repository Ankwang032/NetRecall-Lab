import json

import httpx
import pytest

from integrations.sources.notion import NotionClient, NotionError, notion_from_env, page_id_from

PAGE = "415d0d99-b2e0-815c-9d80-f6da2bb44bb3"


def respond(status=200, body=None, headers=None):
    return httpx.Response(status, json=body if body is not None else {}, headers=headers)


class Fake:
    """요청을 기록하고 준비된 응답을 차례로 돌려주는 가짜 Notion."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def client(self) -> NotionClient:
        return NotionClient("secret-token", transport=httpx.MockTransport(self.handler), sleep=self.sleeps.append)


def block(type_, id_, trashed=False, **payload):
    return {"object": "block", "id": id_, "type": type_, "in_trash": trashed, type_: payload}


def test_headers_and_child_pages_with_pagination():
    fake = Fake(
        respond(body={"results": [
            block("child_page", "p1", title="네트워크 계층 구조"),
            block("paragraph", "b1", rich_text=[]),
            block("child_database", "d1", title="개념"),
            block("child_page", "p2", title="지운 페이지", trashed=True),
        ], "has_more": True, "next_cursor": "cursor-2"}),
        respond(body={"results": [block("child_page", "p3", title="IPv4 주소")], "has_more": False, "next_cursor": None}),
    )
    pages = fake.client().child_pages(f"https://app.notion.com/p/{PAGE.replace('-', '')}?pvs=204")

    assert [(p.page_id, p.title) for p in pages] == [("p1", "네트워크 계층 구조"), ("p3", "IPv4 주소")]
    first, second = fake.requests
    assert first.headers["Authorization"] == "Bearer secret-token"
    assert first.headers["Notion-Version"] == "2026-03-11"
    assert first.url.path == f"/v1/blocks/{PAGE}/children"
    assert first.url.params["page_size"] == "100" and "start_cursor" not in first.url.params
    assert second.url.params["start_cursor"] == "cursor-2"


def test_page_title():
    fake = Fake(respond(body={"properties": {
        "title": {"id": "title", "type": "title", "title": [{"plain_text": "정적 "}, {"plain_text": "라우팅"}]},
    }}))
    assert fake.client().page_title(PAGE) == "정적 라우팅"
    assert fake.requests[0].url.path == f"/v1/pages/{PAGE}"


def test_page_title_of_database_row_uses_its_title_property():
    fake = Fake(respond(body={"properties": {
        "개념 ID": {"type": "rich_text", "rich_text": [{"plain_text": "NET-111"}]},
        "이름": {"type": "title", "title": [{"plain_text": "정적 라우팅"}]},
    }}))
    assert fake.client().page_title(PAGE) == "정적 라우팅"


def test_page_markdown():
    fake = Fake(respond(body={
        "object": "page_markdown", "id": PAGE, "markdown": "## 본문", "truncated": True,
        "unknown_block_ids": ["u1", "u2"],
    }))
    page = fake.client().page_markdown(PAGE)
    assert (page.page_id, page.markdown, page.truncated, page.unknown_block_ids) == (PAGE, "## 본문", True, ("u1", "u2"))
    request = fake.requests[0]
    assert request.url.path == f"/v1/pages/{PAGE}/markdown"
    assert request.url.params["markdown_version"] == "v2"


# ---- 재시도와 오류 ----

def test_rate_limit_waits_retry_after_capped_at_60_seconds():
    fake = Fake(
        respond(429, {"code": "rate_limited"}, {"Retry-After": "3"}),
        respond(429, {"code": "rate_limited"}, {"Retry-After": "120"}),
        respond(body={"properties": {}}),
    )
    assert fake.client().page_title(PAGE) == ""
    assert fake.sleeps == [3.0, 60.0]


def test_blocked_request_is_not_retried():
    fake = Fake(respond(429, {"code": "rate_limited", "additional_data": {"rate_limit_reason": "public_api_request_blocked"}}))
    with pytest.raises(NotionError) as info:
        fake.client().page_title(PAGE)
    assert info.value.status == 429 and fake.sleeps == []


def test_server_errors_on_get_are_retried_then_reported():
    fake = Fake(respond(503), respond(502), respond(504, {"code": "gateway_timeout"}))
    with pytest.raises(NotionError, match=r"Notion 서버가 응답하지 않습니다 \(504\)") as info:
        fake.client().page_markdown(PAGE)
    assert (info.value.status, info.value.code) == (504, "gateway_timeout")
    assert fake.sleeps == [1.0, 2.0]


def test_connection_errors_are_retried_then_reported():
    fake = Fake(httpx.ConnectError("down"), respond(body={"properties": {}}))
    assert fake.client().page_title(PAGE) == ""
    fake = Fake(*[httpx.ConnectTimeout("slow")] * 3)
    with pytest.raises(NotionError, match="연결하지 못했습니다"):
        fake.client().page_title(PAGE)


@pytest.mark.parametrize("status, code, message", [
    (401, "unauthorized", "토큰이 올바르지 않습니다"),
    (403, "restricted_resource", "권한이 없습니다"),
    (404, "object_not_found", r"연결\(Connections\)에 통합을 추가했는지"),
    (400, "validation_error", r"\(400 validation_error\): 잘못된 요청"),
])
def test_client_errors_are_not_retried(status, code, message):
    fake = Fake(respond(status, {"object": "error", "status": status, "code": code, "message": "잘못된 요청"}))
    with pytest.raises(NotionError, match=message) as info:
        fake.client().page_title(PAGE)
    assert (info.value.status, info.value.code) == (status, code)
    assert len(fake.requests) == 1


def test_unreadable_response():
    fake = Fake(httpx.Response(200, content=b"<html>"))
    with pytest.raises(NotionError, match="응답을 읽지 못했습니다"):
        fake.client().page_title(PAGE)


# ---- id·환경 변수 ----

@pytest.mark.parametrize("value", [
    PAGE,
    PAGE.replace("-", ""),
    PAGE.upper(),
    f"https://app.notion.com/p/{PAGE.replace('-', '')}?pvs=204",
    f"https://www.notion.so/myspace/Static-Routing-{PAGE.replace('-', '')}?v=0123456789abcdef0123456789abcdef",
    f"  https://www.notion.so/{PAGE.replace('-', '')}#heading  ",
])
def test_page_id_from(value):
    assert page_id_from(value) == PAGE


@pytest.mark.parametrize("value", ["", "https://www.notion.so/", "415d0d99", f"{PAGE.replace('-', '')}ab"])
def test_page_id_from_rejects(value):
    with pytest.raises(ValueError):
        page_id_from(value)


def test_notion_from_env(monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    assert notion_from_env() is None
    monkeypatch.setenv("NOTION_TOKEN", "t")
    client = notion_from_env()
    assert isinstance(client, NotionClient)
    client.close()


DATABASE = "41fd0d99-b2e0-81ce-b08c-ff964280e202"
SOURCE = "41fd0d99-b2e0-811b-bda4-000b8cceb9d2"


def page_row(id_, trashed=False):
    return {"object": "page", "id": id_, "in_trash": trashed, "properties": {}}


def test_database_rows_queries_the_data_source_in_created_order():
    fake = Fake(
        respond(body={"object": "database", "data_sources": [{"id": SOURCE, "name": "개념"}]}),
        respond(body={"results": [page_row("r1"), page_row("r2", trashed=True)], "has_more": True, "next_cursor": "c2"}),
        respond(body={"results": [page_row("r3"), {"object": "data_source", "id": "x"}], "has_more": False}),
    )
    rows = fake.client().database_rows(f"https://app.notion.com/p/{DATABASE.replace('-', '')}?v=abc")

    assert [r["id"] for r in rows] == ["r1", "r3"]  # 휴지통 행과 페이지가 아닌 결과는 뺀다
    get, first, second = fake.requests
    assert (get.method, get.url.path) == ("GET", f"/v1/databases/{DATABASE}")
    assert (first.method, first.url.path) == ("POST", f"/v1/data_sources/{SOURCE}/query")
    body = json.loads(first.content)
    assert body == {"page_size": 100, "sorts": [{"timestamp": "created_time", "direction": "ascending"}]}
    assert json.loads(second.content)["start_cursor"] == "c2"


def test_database_with_several_data_sources_is_rejected():
    fake = Fake(respond(body={"data_sources": [{"id": "a"}, {"id": "b"}]}))
    with pytest.raises(NotionError, match="여러 개"):
        fake.client().database_rows(DATABASE)


def test_query_is_read_only_so_server_errors_are_retried():
    fake = Fake(
        respond(body={"data_sources": [{"id": SOURCE}]}),
        respond(502),
        respond(body={"results": [page_row("r1")], "has_more": False}),
    )
    assert [r["id"] for r in fake.client().database_rows(DATABASE)] == ["r1"]
    assert fake.sleeps == [1.0]
