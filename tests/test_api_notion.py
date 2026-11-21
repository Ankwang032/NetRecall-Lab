import shutil
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services.concept_extract import ConceptExtraction
from backend.services.notion_import import file_name_for
from integrations.sources.notion import NotionClient
from tests.fakes import FakeLLM

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "concepts"
PARENT = "415d0d99-b2e0-815c-9d80-f6da2bb44bb3"
STATIC = "fe8d0d99-b2e0-82cf-9cfa-0185ee1aface"
LPM = "9f1d0d99-b2e0-8295-8d12-81c9c39947a3"
COPY = "41fd0d99-b2e0-81de-958d-c019e23c1ec9"
MISSING = "02ad0d99-b2e0-82bc-a8fd-8175aabd93da"

STATIC_MD = """<callout icon="💡" color="yellow_bg">
<b>한 줄 요약</b>: 정적 라우팅은 경로를 직접 넣는 방식이에요.
</callout>

## 1. 정적 경로의 구성

| 형태 | 예시 |
| --- | --- |
| 다음 홉 | <code>ip route 192.168.3.0/24 10.0.12.2</code> |

## 13. 이해 확인 질문

<toggle>
Q1. 정적 경로의 기본 관리 거리는?

<b>1</b>이에요.
</toggle>

<toggle>
Q2. 정적 라우팅의 가장 큰 단점은?

자동으로 대응하지 못해요.
</toggle>

<toggle>
Q3. r2에는 왜 정적 경로가 두 개 필요할까?

양쪽 LAN을 모르기 때문이에요.
</toggle>
"""

TITLES = {PARENT: "네트워크", STATIC: "정적 라우팅", LPM: "Longest Prefix Match", COPY: "정적 라우팅"}
MARKDOWN = {STATIC: (STATIC_MD, False), LPM: ("본문", True), COPY: ("복사본 본문", False)}


def notion_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path.removeprefix("/v1")
    if path == f"/blocks/{PARENT}/children":
        return httpx.Response(200, json={"results": [
            {"object": "block", "id": STATIC, "type": "child_page", "in_trash": False, "child_page": {"title": "정적 라우팅"}},
            {"object": "block", "id": LPM, "type": "child_page", "in_trash": False,
             "child_page": {"title": "Longest Prefix Match"}},
        ], "has_more": False, "next_cursor": None})
    page_id = path.split("/")[2]
    if page_id not in TITLES:
        return httpx.Response(404, json={"object": "error", "status": 404, "code": "object_not_found", "message": "x"})
    if path.endswith("/markdown"):
        markdown, truncated = MARKDOWN[page_id]
        return httpx.Response(200, json={"id": page_id, "markdown": markdown, "truncated": truncated})
    return httpx.Response(200, json={"properties": {"title": {"type": "title", "title": [{"plain_text": TITLES[page_id]}]}}})


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def make(*responses, notion=True):
        root = tmp_path / "concepts"
        shutil.copytree(SAMPLES, root, dirs_exist_ok=True)
        client = NotionClient("t", transport=httpx.MockTransport(notion_handler), sleep=lambda s: None)
        app = create_app(f"sqlite:///{tmp_path / 'api.db'}", root, llm=FakeLLM(*responses),
                         notion=client if notion else None)
        api = TestClient(app)
        api.post("/sync/markdown")
        return api
    return make


def test_list_pages(make_client):
    res = make_client().get("/notion/pages", params={"parent": f"https://app.notion.com/p/{PARENT.replace('-', '')}?pvs=204"})
    assert res.status_code == 200
    assert res.json() == {
        "parent": {"page_id": PARENT, "title": "네트워크"},
        "pages": [{"page_id": STATIC, "title": "정적 라우팅"}, {"page_id": LPM, "title": "Longest Prefix Match"}],
    }


def test_list_pages_errors(make_client):
    client = make_client()
    assert client.get("/notion/pages", params={"parent": "not-a-page"}).status_code == 422
    res = client.get("/notion/pages", params={"parent": MISSING})
    assert res.status_code == 502 and "연결(Connections)" in res.json()["detail"]
    assert make_client(notion=False).get("/notion/pages", params={"parent": PARENT}).status_code == 503


def test_fetch_files(make_client):
    res = make_client().post("/notion/files", json={"page_ids": [STATIC, LPM, COPY, MISSING]})
    files = res.json()["files"]
    assert [(f["page_id"], f["title"], f["name"], f["error"]) for f in files] == [
        (STATIC, "정적 라우팅", "정적-라우팅.md", None),
        (LPM, "Longest Prefix Match", "Longest-Prefix-Match.md", None),
        (COPY, "정적 라우팅", "정적-라우팅-2.md", None),  # 같은 제목
        (MISSING, "", "", files[3]["error"]),
    ]
    assert files[0]["content"] == f"# 정적 라우팅\n\n{STATIC_MD}"
    assert files[1]["warnings"] == ["Notion이 페이지를 끝까지 돌려주지 못했습니다 (블록이 너무 많음). 뒷부분이 빠졌을 수 있습니다"]
    assert files[3]["content"] is None and "찾지 못했습니다" in files[3]["error"]


def test_notion_page_to_saved_concept(make_client):
    extraction = ConceptExtraction(
        category="Routing", keywords=["Static Route"], difficulty=2, prerequisites=["NET-005"], related=[],
        extra_questions=[],
    )
    client = make_client(extraction)
    (file,) = client.post("/notion/files", json={"page_ids": [STATIC]}).json()["files"]

    (plan,) = client.post("/concepts/normalize/plan", json={"files": [{"name": file["name"], "content": file["content"]}]}).json()["files"]
    assert (plan["status"], plan["concept_id"], plan["title"]) == ("convert", "NET-011", "정적 라우팅")

    converted = client.post("/concepts/normalize/convert", json={
        "file": {"name": file["name"], "content": file["content"]}, "concept_id": plan["concept_id"],
    }).json()
    saved = client.post("/concepts/files", json={
        "folder": "network", "files": [{"name": converted["name"], "content": converted["content"]}],
    }).json()
    assert saved["saved"] is True

    concept = client.get("/concepts/NET-011").json()
    assert concept["title"] == "정적 라우팅"
    assert concept["source_ref"] == "network/정적-라우팅.md"
    assert concept["questions"] == ["정적 경로의 기본 관리 거리는?", "정적 라우팅의 가장 큰 단점은?", "r2에는 왜 정적 경로가 두 개 필요할까?"]
    assert concept["prerequisites"] == ["NET-005"]
    assert "<" not in concept["content"].replace("<br", "")  # Notion 태그가 남지 않는다
    assert "`ip route 192.168.3.0/24 10.0.12.2`" in concept["content"]
    assert "자동으로 대응하지 못해요" not in concept["content"]  # 토글 안의 답은 버린다


@pytest.mark.parametrize("title, expected", [
    ("정적 라우팅", "정적-라우팅.md"),
    ("네트워크 계층 구조 (OSI / TCP-IP)", "네트워크-계층-구조-OSI-TCP-IP.md"),
    ("TCP와 UDP, 포트", "TCP와-UDP-포트.md"),
    ("관리 거리(AD)와 메트릭", "관리-거리-AD-와-메트릭.md"),
    ("_draft.", "draft.md"),  # 동기화에서 건너뛰는 _ 로 시작하지 않게
    ("README", "README-2.md"),
    ("??", "notion-415d0d99.md"),
    ("가" * 100, "가" * 80 + ".md"),
])
def test_file_name_for(title, expected):
    assert file_name_for(title, PARENT, set()) == expected
