from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.models import AnswerEvaluation, AnswerSubmission, Concept, Question
from backend.services.concept_history import lab_ids
from tests.fakes import FakeLabRuntime

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "concepts"


@pytest.fixture
def client(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}", SAMPLES, lab_runtime=FakeLabRuntime())
    with TestClient(app) as c:
        c.post("/sync/markdown")
        yield c


def test_list_has_card_count_and_next_due(client):
    concepts = {c["id"]: c for c in client.get("/concepts").json()}
    assert {cid: c["card_count"] for cid, c in concepts.items()} == {"NET-001": 3, "NET-005": 3, "NET-010": 3}
    assert concepts["NET-010"]["next_due_at"].endswith("+09:00")
    assert client.get("/concepts/NET-010").json()["card_count"] == 3


def test_history_cards_reviews_and_original_scores(client):
    cards = client.get("/concepts/NET-010/history").json()["cards"]
    assert [(c["reviews"], c["last_rating"], c["last_score"]) for c in cards] == [(0, None, None)] * 3
    first = cards[0]["card_id"]

    client.post("/reviews", json={"card_id": first, "rating": 1})
    client.post("/reviews", json={"card_id": first, "rating": 3})
    add_evaluation(client, first, "original", 55, minutes=1)
    add_evaluation(client, first, "original", 80, minutes=2)  # 최근 것이 보인다
    add_evaluation(client, first, "variant", 30, minutes=3)   # 변형 질문은 세지 않는다

    card = client.get("/concepts/NET-010/history").json()["cards"][0]
    assert (card["reviews"], card["last_rating"], card["last_score"]) == (2, 3, 80)
    assert card["last_reviewed_at"].endswith("+09:00") and card["last_scored_at"].endswith("+09:00")
    assert card["due_at"] > cards[0]["due_at"]


def test_history_labs_and_runs(client):
    labs = client.get("/concepts/NET-005/history").json()["labs"]
    assert labs == [{"scenario_id": "LAB-001", "title": "대역의 첫 주소와 마지막 주소로 통신하기", "runs": []}]

    run_id = client.post("/labs/LAB-001/runs", json={"level": "hard"}).json()["run_id"]
    client.post(f"/lab-runs/{run_id}/finish")
    runs = client.get("/concepts/NET-005/history").json()["labs"][0]["runs"]
    assert [(r["run_id"], r["status"], r["level"], r["attempts_to_pass"]) for r in runs] == [(run_id, "abandoned", "hard", None)]
    assert client.get("/concepts/NET-001/history").json()["labs"] == []


def test_history_of_unknown_concept_is_404(client):
    assert client.get("/concepts/NET-404/history").status_code == 404


def test_lab_ids_join_concept_labs_and_scenario_concepts():
    scenarios = [scenario("LAB-001", ["NET-005"]), scenario("LAB-002", ["NET-010", "NET-111"])]
    assert lab_ids("NET-111", [], scenarios) == ["LAB-002"]                      # 시나리오가 가리킴
    assert lab_ids("NET-105", ["LAB-001"], scenarios) == ["LAB-001"]             # 개념 원본(Notion "실습")이 가리킴
    assert lab_ids("NET-010", ["LAB-002", "LAB-009"], scenarios) == ["LAB-002", "LAB-009"]  # 없는 시나리오도 남긴다


def scenario(scenario_id: str, concepts: list[str]) -> SimpleNamespace:
    return SimpleNamespace(id=scenario_id, concepts=tuple(concepts))  # lab_ids는 id·concepts만 본다


def add_evaluation(client, card_id: int, kind: str, score: int, minutes: int) -> None:
    at = datetime(2026, 11, 26, tzinfo=UTC) + timedelta(minutes=minutes)
    with client.app.state.session_factory() as session:
        q = Question(card_id=card_id, concept_id="NET-010", base_question="q", question="q", kind=kind)
        session.add(q)
        session.flush()
        sub = AnswerSubmission(question_id=q.id, answer="a", submitted_at=at)
        session.add(sub)
        session.flush()
        session.add(AnswerEvaluation(submission_id=sub.id, score=score, feedback_json={}, model="fake", prompt_version="1"))
        session.commit()


def test_source_of_markdown_concept_is_the_file(client):
    res = client.get("/concepts/NET-010/source").json()
    assert (res["source_type"], res["path"], res["url"]) == ("markdown", "network/static-routing.md", None)
    assert res["text"] == (SAMPLES / "network" / "static-routing.md").read_text(encoding="utf-8")
    assert "## 질문" in res["text"]  # 본문과 달리 frontmatter·질문까지 그대로


def test_source_outside_the_concepts_folder_or_missing_is_404(client):
    with client.app.state.session_factory() as session:
        concept = session.get(Concept, "NET-001")
        concept.source_ref = "../../pyproject.toml"
        session.commit()
    res = client.get("/concepts/NET-001/source")
    assert res.status_code == 404 and "동기화하세요" in res.json()["detail"]
    assert client.get("/concepts/NET-404/source").status_code == 404


def test_source_of_notion_concept_links_to_the_page(client):
    with client.app.state.session_factory() as session:
        concept = session.get(Concept, "NET-005")
        concept.source_type, concept.source_ref = "notion", "fe8d0d99-b2e0-82cf-9cfa-0185ee1aface"
        session.commit()
    res = client.get("/concepts/NET-005/source").json()
    assert res["url"] == "https://www.notion.so/fe8d0d99b2e082cf9cfa0185ee1aface"
    assert res["path"] is None and res["text"] == client.get("/concepts/NET-005").json()["content"]
