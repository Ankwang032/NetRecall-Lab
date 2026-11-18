import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "concepts"
OSPF = "---\nid: NET-020\ntitle: OSPF\nquestions: [Q1, Q2, Q3]\n---\nOSPF 본문\n"


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "concepts"
    shutil.copytree(SAMPLES, root)
    client = TestClient(create_app(f"sqlite:///{tmp_path / 'api.db'}", root))
    client.post("/sync/markdown")
    return client, root


def test_folders(setup):
    client, _ = setup
    assert client.get("/concepts/folders").json() == ["", "network"]


def test_dry_run_checks_without_saving(setup):
    client, root = setup
    res = client.post("/concepts/files", params={"dry_run": True},
                      json={"folder": "network", "files": [{"name": "ospf.md", "content": OSPF}]}).json()
    assert res["saved"] is False and res["sync"] is None
    assert res["files"] == [{"name": "ospf.md", "path": "network/ospf.md", "concept_id": "NET-020",
                             "title": "OSPF", "question_count": 3, "errors": []}]
    assert not (root / "network" / "ospf.md").exists()


def test_save_then_cards_are_due(setup):
    client, root = setup
    res = client.post("/concepts/files", json={"folder": "network", "files": [{"name": "ospf.md", "content": OSPF}]}).json()
    assert res["saved"] is True and res["sync"]["summary"]["created"] == 1
    assert (root / "network" / "ospf.md").exists()
    due = [c for c in client.get("/reviews/due").json() if c["concept_id"] == "NET-020"]
    assert len(due) == 3


def test_invalid_file_is_not_saved(setup):
    client, root = setup
    res = client.post("/concepts/files", json={"files": [{"name": "bad.md", "content": "본문만"}]}).json()
    assert res["saved"] is False and res["files"][0]["errors"]
    assert not (root / "bad.md").exists()


@pytest.mark.parametrize("folder", ["없는폴더", "../outside", "/etc"])
def test_unknown_folder_is_422(setup, folder):
    client, _ = setup
    res = client.post("/concepts/files", json={"folder": folder, "files": [{"name": "a.md", "content": OSPF}]})
    assert res.status_code == 422


def test_concept_detail_route_still_works(setup):
    client, _ = setup
    assert client.get("/concepts/NET-010").json()["title"] == "Static Routing"
