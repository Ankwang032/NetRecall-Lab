"""POST /sync/notion: Notion 데이터베이스 동기화. 가짜 Notion(httpx MockTransport)으로 확인한다."""
import shutil
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.main import create_app
from backend.models import Concept, ReviewCard
from integrations.sources.notion import NotionClient
from tests.sources.test_notion_source import BODY, row

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "concepts"
DATABASE = "41fd0d99-b2e0-81ce-b08c-ff964280e202"
SOURCE = "41fd0d99-b2e0-811b-bda4-000b8cceb9d2"
P1 = "aaaa0d99-b2e0-8000-8000-000000000001"
P2 = "aaaa0d99-b2e0-8000-8000-000000000002"


class FakeNotion:
    def __init__(self):
        self.rows = [row(P1, "정적 라우팅", "NET-111", 난이도=3, 선수_개념=[P2]), row(P2, "라우팅 테이블", "NET-108")]
        self.down = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/v1")
        if self.down:
            return httpx.Response(404, json={"code": "object_not_found", "message": "x"})
        if path == f"/databases/{DATABASE}":
            return httpx.Response(200, json={"data_sources": [{"id": SOURCE, "name": "개념"}]})
        if path == f"/data_sources/{SOURCE}/query":
            return httpx.Response(200, json={"results": self.rows, "has_more": False})
        page_id = path.split("/")[2]
        return httpx.Response(200, json={"id": page_id, "markdown": BODY, "truncated": False})


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.delenv("NETRECALL_NOTION_DATABASE", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    root = tmp_path / "concepts"
    shutil.copytree(SAMPLES, root)
    fake = FakeNotion()

    def make(database=f"https://app.notion.com/p/{DATABASE.replace('-', '')}?v=1"):
        client = NotionClient("t", transport=httpx.MockTransport(fake.handler), sleep=lambda s: None)
        app = create_app(f"sqlite:///{tmp_path / 'api.db'}", root, notion=client, notion_database=database)
        return TestClient(app), app.state.session_factory
    return make, fake, root


def test_sync_creates_then_unchanged_then_archives(setup):
    make, fake, _ = setup
    api, sessions = make()
    res = api.post("/sync/notion")
    assert res.status_code == 200
    body = res.json()
    assert body["summary"]["created"] == 2 and body["errors"] == [] and body["warnings"] == []

    with sessions() as s:
        c = s.get(Concept, "NET-111")
        assert (c.source_type, c.source_ref, c.difficulty) == ("notion", P1, 3)
        assert len(s.scalars(select(ReviewCard).where(ReviewCard.concept_id == "NET-111")).all()) == 3

    assert api.post("/sync/notion").json()["summary"]["unchanged"] == 2

    fake.rows = fake.rows[:1]  # 행을 휴지통으로 보내면 query에서 빠진다
    body = api.post("/sync/notion").json()
    assert body["summary"]["archived"] == 1
    with sessions() as s:
        assert s.get(Concept, "NET-108").archived


def test_notion_failure_is_502_and_changes_nothing(setup):
    make, fake, _ = setup
    api, sessions = make()
    api.post("/sync/notion")
    fake.down = True
    res = api.post("/sync/notion")
    assert res.status_code == 502 and "찾지 못했습니다" in res.json()["detail"]
    with sessions() as s:
        assert not any(c.archived for c in s.scalars(select(Concept)))  # 연결 실패로 개념이 보관되지 않는다


def test_missing_or_bad_database_setting_is_503(setup):
    make, _, _ = setup
    res = make(database=None)[0].post("/sync/notion")
    assert res.status_code == 503 and "NETRECALL_NOTION_DATABASE" in res.json()["detail"]
    res = make(database="개념")[0].post("/sync/notion")
    assert res.status_code == 503 and "주소나 id가 아닙니다" in res.json()["detail"]


def test_note_moved_from_markdown_keeps_cards(setup):
    """.md를 지워 보관된 개념을 같은 id의 Notion 행이 넘겨받는다. 활성인 id는 충돌이다."""
    make, fake, root = setup
    api, sessions = make()
    api.post("/sync/markdown")
    with sessions() as s:
        before = {c.question for c in s.scalars(select(ReviewCard).where(ReviewCard.concept_id == "NET-010"))}

    fake.rows = [row(P1, "Static Routing", "NET-010"), row(P2, "OSI", "NET-001")]
    (root / "network" / "static-routing.md").unlink()
    assert api.post("/sync/markdown").json()["summary"]["archived"] == 1

    body = api.post("/sync/notion").json()
    assert body["summary"]["taken_over"] == 1
    assert [e["source_ref"] for e in body["errors"]] == [P2]  # NET-001은 아직 Markdown에서 쓰는 중
    assert "markdown 소스에서 사용 중" in body["errors"][0]["message"]
    with sessions() as s:
        c = s.get(Concept, "NET-010")
        assert (c.source_type, c.source_ref, c.archived) == ("notion", P1, False)
        cards = s.scalars(select(ReviewCard).where(ReviewCard.concept_id == "NET-010")).all()
        assert before <= {c.question for c in cards}  # 옛 카드 행과 이력은 남는다 (질문이 달라 비활성)
