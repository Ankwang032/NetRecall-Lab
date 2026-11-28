from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from tests.fakes import FakeLabRuntime

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "concepts"


@pytest.fixture
def client(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}", SAMPLES, lab_runtime=FakeLabRuntime())
    with TestClient(app) as c:
        c.post("/sync/markdown")
        yield c


def test_summary_of_new_samples(client):
    s = client.get("/dashboard/summary").json()
    assert s["today"] == {"due": 9, "overdue": 0, "reviewed": 0, "concepts": 3, "cards": 9, "streak_days": 0}
    assert len(s["reviews_by_day"]) == 28 and len(s["due_by_day"]) == 7 and len(s["errors_by_week"]) == 4
    assert len(s["reviews_by_day"][-1]["date"]) == 10  # KST 날짜 "YYYY-MM-DD"
    assert s["due_by_day"][0]["cards"] == 9
    assert s["stages"] == {"new": 9, "learning": 0, "review": 0, "mature": 0}
    assert sum(c["stages"]["new"] for c in s["categories"]) == 9
    assert s["weak_concepts"] == []
    assert s["rules"]["recent_days"] == 30
    assert [(lab["scenario_id"], lab["runs"], lab["last_run"]) for lab in s["labs"]] == [("LAB-001", 0, None), ("LAB-002", 0, None)]


def test_summary_follows_reviews_and_lab_runs(client):
    card = client.get("/reviews/due").json()[0]
    client.post("/reviews", json={"card_id": card["card_id"], "rating": 1})
    run_id = client.post("/labs/LAB-001/runs", json={"level": "normal"}).json()["run_id"]
    client.post(f"/lab-runs/{run_id}/finish")

    s = client.get("/dashboard/summary").json()
    assert (s["today"]["reviewed"], s["today"]["due"], s["today"]["streak_days"]) == (1, 8, 1)
    assert s["reviews_by_day"][-1] == {**s["reviews_by_day"][-1], "again": 1, "hard": 0}
    assert s["errors_by_week"][-1]["reviews"] == 1 and s["errors_by_week"][-1]["wrong"] == 1
    assert s["stages"]["learning"] == 1
    category = next(c for c in s["categories"] if c["reviews"] == 1)
    assert category["wrong"] == 1
    lab = s["labs"][0]
    assert (lab["runs"], lab["last_run"]["status"], lab["last_run"]["started_at"][-6:]) == (1, "abandoned", "+09:00")
