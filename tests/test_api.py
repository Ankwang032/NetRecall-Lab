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
    assert len(detail["questions"]) == 2
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
    note.write_text("---\nid: NET-001\n---\n본문\n", encoding="utf-8")
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
