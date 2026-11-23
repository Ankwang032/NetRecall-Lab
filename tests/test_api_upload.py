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


def test_missing_concepts_folder_is_reported_with_path(tmp_path):
    """개념 폴더가 없으면 폴더를 쓰는 API가 모두 같은 문구로 알린다 (화면에 '요청 실패 (500)'만 나오지 않게)."""
    missing = tmp_path / "없는-폴더"
    client = TestClient(create_app(f"sqlite:///{tmp_path / 'api.db'}", missing))
    file = {"name": "ospf.md", "content": OSPF}
    responses = [
        client.get("/concepts/folders"),
        client.post("/concepts/files", params={"dry_run": True}, json={"folder": "", "files": [file]}),
        client.post("/concepts/normalize/plan", json={"files": [file]}),
        client.post("/sync/markdown"),
    ]
    for res in responses:
        assert res.status_code == 500
        assert res.json()["detail"] == f"개념 폴더가 없습니다: {missing}"


def test_concepts_folder_from_env_expands_home(tmp_path, monkeypatch):
    """.env 파일은 ~를 풀지 않으므로 앱이 홈 폴더로 바꾼다."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("NETRECALL_CONCEPTS_DIR", "~/notes")
    shutil.copytree(SAMPLES, tmp_path / "notes")
    client = TestClient(create_app(f"sqlite:///{tmp_path / 'api.db'}"))
    assert client.post("/sync/markdown").json()["summary"]["created"] == 3
