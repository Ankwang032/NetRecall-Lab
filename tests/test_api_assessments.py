from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services import ai_prompts as prompts
from integrations.llm import LLMError
from tests.fakes import FakeLLM

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "concepts"

VARIANT = prompts.VariantQuestion(question="변형 질문")
DIFFICULTY = prompts.DifficultyAssessment(reason="비슷하다", relative_difficulty=0)
EVALUATION = prompts.AnswerEvaluation(
    score=75, accuracy=80, completeness=70, logic=75, technical_validity=80, application=65,
    strengths=["핵심을 짚음"], missing_points=["왕복 경로 누락"], technical_errors=[],
    recommended_lab="LAB-002",
)


def client_with(tmp_path, *responses):
    llm = FakeLLM(*responses)
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}", SAMPLES, llm=llm)
    client = TestClient(app)
    client.post("/sync/markdown")
    return client


def static_routing_card(client):
    return next(c["card_id"] for c in client.get("/reviews/due").json() if c["concept_id"] == "NET-010")


def test_full_learning_cycle(tmp_path):
    client = client_with(tmp_path, VARIANT, DIFFICULTY, EVALUATION)
    card_id = static_routing_card(client)

    res = client.post(f"/cards/{card_id}/questions")
    assert res.status_code == 201
    q = res.json()
    assert (q["card_id"], q["concept_id"], q["question"]) == (card_id, "NET-010", "변형 질문")
    assert (q["relative_difficulty"], q["difficulty_reason"]) == (0, "비슷하다")
    assert q["created_at"].endswith("+09:00")

    res = client.post(f"/questions/{q['question_id']}/answers", json={"answer": "다음 홉을 지정한다"})
    assert res.status_code == 201
    ev = res.json()
    assert (ev["score"], ev["application"], ev["recommended_lab"]) == (75, 65, "LAB-002")
    assert ev["missing_points"] == ["왕복 경로 누락"]
    assert ev["model"] == "fake-model" and ev["submitted_at"].endswith("+09:00")

    # 피드백을 본 뒤 등급은 사용자가 고른다
    assert client.post("/reviews", json={"card_id": card_id, "rating": 2}).status_code == 200


def test_original_then_variant_cycle(tmp_path):
    client = client_with(tmp_path, EVALUATION, VARIANT, DIFFICULTY, EVALUATION)
    card_id = static_routing_card(client)

    res = client.post(f"/cards/{card_id}/questions/original")
    assert res.status_code == 201
    original = res.json()
    assert original["kind"] == "original" and original["question"] == original["base_question"]
    assert (original["relative_difficulty"], original["difficulty_reason"]) == (None, None)
    res = client.post(f"/questions/{original['question_id']}/answers", json={"answer": "1차 답안"})
    assert res.status_code == 201

    # 필요하면 2차로 변형 질문을 받는다
    variant = client.post(f"/cards/{card_id}/questions").json()
    assert (variant["kind"], variant["question"]) == ("variant", "변형 질문")
    res = client.post(f"/questions/{variant['question_id']}/answers", json={"answer": "2차 답안"})
    assert res.status_code == 201
    assert client.post("/reviews", json={"card_id": card_id, "rating": 3}).status_code == 200


def test_original_question_works_without_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = TestClient(create_app(f"sqlite:///{tmp_path / 'api.db'}", SAMPLES))
    client.post("/sync/markdown")
    card_id = client.get("/reviews/due").json()[0]["card_id"]
    assert client.post(f"/cards/{card_id}/questions/original").status_code == 201
    assert client.post("/cards/999/questions/original").status_code == 404


def test_ai_endpoints_are_503_without_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = TestClient(create_app(f"sqlite:///{tmp_path / 'api.db'}", SAMPLES))
    client.post("/sync/markdown")
    card_id = client.get("/reviews/due").json()[0]["card_id"]
    assert client.post(f"/cards/{card_id}/questions").status_code == 503
    assert client.post("/questions/1/answers", json={"answer": "답"}).status_code == 503
    assert client.get("/reviews/due").status_code == 200  # 나머지 기능은 동작한다


def test_llm_failure_is_502(tmp_path):
    client = client_with(tmp_path, LLMError("할당량 초과"))
    res = client.post(f"/cards/{static_routing_card(client)}/questions")
    assert res.status_code == 502 and "할당량 초과" in res.json()["detail"]


def test_answer_llm_failure_is_502(tmp_path):
    client = client_with(tmp_path, VARIANT, DIFFICULTY, LLMError("시간 초과"))
    q = client.post(f"/cards/{static_routing_card(client)}/questions").json()
    assert client.post(f"/questions/{q['question_id']}/answers", json={"answer": "답"}).status_code == 502


def test_unknown_card_and_question_are_404(tmp_path):
    client = client_with(tmp_path)
    assert client.post("/cards/999/questions").status_code == 404
    assert client.post("/questions/999/answers", json={"answer": "답"}).status_code == 404


@pytest.mark.parametrize("answer", ["", "가" * 10_001])
def test_answer_length_is_validated(tmp_path, answer):
    client = client_with(tmp_path)
    assert client.post("/questions/1/answers", json={"answer": answer}).status_code == 422
