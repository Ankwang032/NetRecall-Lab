from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "concepts"


@pytest.fixture
def client(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}", SAMPLES)
    with TestClient(app) as c:
        yield c


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_sync_then_list_and_detail(client):
    assert client.get("/concepts").json() == []

    res = client.post("/sync/markdown").json()
    assert res["summary"]["created"] == 3
    assert res["errors"] == [] and res["dangling_refs"] == []

    concepts = client.get("/concepts").json()
    assert [c["id"] for c in concepts] == ["NET-001", "NET-005", "NET-010"]
    static = concepts[2]
    assert static["prerequisites"] == ["NET-005"]
    assert static["related"] == ["NET-001"]
    assert static["labs"] == ["LAB-002"]
    assert "content" not in static

    detail = client.get("/concepts/NET-010").json()
    assert detail["title"] == "Static Routing"
    assert len(detail["questions"]) == 3
    assert "## 질문" not in detail["content"]

    assert client.post("/sync/markdown").json()["summary"]["unchanged"] == 3


def test_dry_run_does_not_store(client):
    res = client.post("/sync/markdown", params={"dry_run": True}).json()
    assert res["dry_run"] is True and res["summary"]["created"] == 3
    assert client.get("/concepts").json() == []


def test_unknown_concept_is_404(client):
    assert client.get("/concepts/NET-404").status_code == 404


def test_archived_concepts_hidden_by_default(tmp_path):
    root = tmp_path / "concepts"
    root.mkdir()
    note = root / "a.md"
    note.write_text("---\nid: NET-001\nquestions: [Q1, Q2, Q3]\n---\n본문\n", encoding="utf-8")
    with TestClient(create_app(f"sqlite:///{tmp_path / 'a.db'}", root)) as client:
        client.post("/sync/markdown")
        note.unlink()
        assert client.post("/sync/markdown").json()["summary"]["archived"] == 1
        assert client.get("/concepts").json() == []
        archived = client.get("/concepts", params={"include_archived": True}).json()
        assert [c["archived"] for c in archived] == [True]


def test_missing_concepts_dir_is_500(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'm.db'}", tmp_path / "missing")
    with TestClient(app) as client:
        assert client.post("/sync/markdown").status_code == 500


def test_review_flow(client):
    assert client.get("/reviews/due").json() == []
    client.post("/sync/markdown")

    due = client.get("/reviews/due").json()
    assert len(due) == 9  # 샘플 개념 3개 × 질문 3개
    first = due[0]
    assert set(first) == {"card_id", "concept_id", "concept_title", "question", "due_at"}
    assert first["due_at"].endswith("+09:00")

    res = client.post("/reviews", json={"card_id": first["card_id"], "rating": 3})
    assert res.status_code == 200
    body = res.json()
    assert body["rating"] == 3
    assert body["reviewed_at"].endswith("+09:00") and body["next_due_at"].endswith("+09:00")
    assert datetime.fromisoformat(body["next_due_at"]) > datetime.fromisoformat(body["reviewed_at"])

    remaining = client.get("/reviews/due").json()
    assert first["card_id"] not in [c["card_id"] for c in remaining]
    assert len(remaining) == 8


@pytest.mark.parametrize("rating", [0, 5])
def test_review_rejects_invalid_rating(client, rating):
    client.post("/sync/markdown")
    card_id = client.get("/reviews/due").json()[0]["card_id"]
    assert client.post("/reviews", json={"card_id": card_id, "rating": rating}).status_code == 422


def test_review_unknown_card_is_404(client):
    assert client.post("/reviews", json={"card_id": 999, "rating": 3}).status_code == 404


def test_review_archived_concept_is_409(tmp_path):
    root = tmp_path / "concepts"
    root.mkdir()
    note = root / "a.md"
    note.write_text("---\nid: NET-001\nquestions: [Q1, Q2, Q3]\n---\n본문\n", encoding="utf-8")
    with TestClient(create_app(f"sqlite:///{tmp_path / 'a.db'}", root)) as client:
        client.post("/sync/markdown")
        card_id = client.get("/reviews/due").json()[0]["card_id"]
        note.unlink()
        client.post("/sync/markdown")
        assert client.get("/reviews/due").json() == []
        assert client.post("/reviews", json={"card_id": card_id, "rating": 3}).status_code == 409


def test_serves_built_ui_at_root(tmp_path):
    ui = tmp_path / "dist"
    ui.mkdir()
    (ui / "index.html").write_text("<title>NetRecall Lab</title>", encoding="utf-8")
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}", SAMPLES, frontend_dir=ui)
    with TestClient(app) as c:
        assert "NetRecall Lab" in c.get("/").text
        assert c.get("/health").json() == {"status": "ok"}  # API가 먼저 매칭된다
        assert c.get("/reviews/due").json() == []


def test_address_bar_gets_ui_on_api_paths(tmp_path):
    ui = tmp_path / "dist"
    (ui / "assets").mkdir(parents=True)
    (ui / "index.html").write_text("<title>NetRecall Lab</title>", encoding="utf-8")
    (ui / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}", SAMPLES, frontend_dir=ui)
    page = {"accept": "text/html,application/xhtml+xml,*/*;q=0.8"}  # 브라우저 주소창
    with TestClient(app) as c:
        res = c.get("/labs", headers=page)
        assert "NetRecall Lab" in res.text  # 화면 경로 /labs = API GET /labs
        assert (res.headers["vary"], res.headers["cache-control"]) == ("Accept", "no-cache")  # fetch가 캐시를 쓰지 않게
        assert "scenarios" in c.get("/labs").json()                  # 화면의 fetch (Accept: */*)
        assert c.get("/assets/app.js", headers=page).text == "console.log(1)"
        assert "swagger" in c.get("/docs", headers=page).text.lower()
        assert c.post("/reviews", headers=page, json={}).status_code == 422  # GET만 바꾼다


def test_root_is_404_without_built_ui(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}", SAMPLES, frontend_dir=tmp_path / "없음")
    with TestClient(app) as c:
        assert c.get("/").status_code == 404
