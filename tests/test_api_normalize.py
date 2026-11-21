import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services.concept_extract import ConceptExtraction
from integrations.llm import LLMError
from tests.fakes import FakeLLM

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "concepts"
NOTE = "# OSPF\n\nOSPF 본문\n\n## 질문\n\n- Q1. 하나\n- Q2. 둘\n- Q3. 셋\n"
STANDARD = "---\nid: NET-020\ntitle: OSPF\nquestions: [Q1, Q2, Q3]\n---\nOSPF 본문\n"
EXTRACTION = ConceptExtraction(
    category="Routing", keywords=["OSPF"], difficulty=3, prerequisites=["NET-010"], related=[], extra_questions=[],
)


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def make(*responses, llm=True):
        root = tmp_path / "concepts"
        shutil.copytree(SAMPLES, root, dirs_exist_ok=True)
        app = create_app(f"sqlite:///{tmp_path / 'api.db'}", root, llm=FakeLLM(*responses) if llm else None)
        client = TestClient(app)
        client.post("/sync/markdown")
        return client
    return make


def test_plan(make_client):
    client = make_client()
    res = client.post("/concepts/normalize/plan", json={"files": [
        {"name": "ospf.md", "content": NOTE}, {"name": "std.md", "content": STANDARD},
    ]})
    assert res.status_code == 200
    assert res.json()["files"] == [
        # 함께 올린 표준 파일의 NET-020도 쓰인 번호다
        {"name": "ospf.md", "status": "convert", "concept_id": "NET-021", "title": "OSPF", "warnings": [], "error": None},
        {"name": "std.md", "status": "standard", "concept_id": "NET-020", "title": "OSPF", "warnings": [], "error": None},
    ]


def test_plan_rejects_bad_prefix(make_client):
    res = make_client().post("/concepts/normalize/plan", json={"files": [{"name": "a.md", "content": "x"}], "prefix": "net"})
    assert res.status_code == 422


def test_convert_then_save(make_client):
    client = make_client(EXTRACTION)
    res = client.post("/concepts/normalize/convert", json={
        "file": {"name": "ospf.md", "content": NOTE}, "concept_id": "NET-011",
        "batch": [{"concept_id": "NET-011", "title": "OSPF"}],
    })
    assert res.status_code == 200
    body = res.json()
    assert (body["name"], body["concept_id"], body["title"], body["warnings"]) == ("ospf.md", "NET-011", "OSPF", [])
    assert body["content"].startswith("---\nid: NET-011\ntitle: OSPF\ncategory: Routing\n")

    saved = client.post("/concepts/files", json={
        "folder": "network", "files": [{"name": "ospf.md", "content": body["content"]}],
    }).json()
    assert saved["saved"] is True
    assert saved["files"][0]["question_count"] == 3
    assert client.get("/concepts/NET-011").json()["prerequisites"] == ["NET-010"]


def test_convert_failures(make_client):
    request = {"file": {"name": "ospf.md", "content": NOTE}, "concept_id": "NET-011"}
    assert make_client(LLMError("과부하")).post("/concepts/normalize/convert", json=request).status_code == 502
    assert make_client(llm=False).post("/concepts/normalize/convert", json=request).status_code == 503
    bad_id = request | {"concept_id": "NET-1"}
    assert make_client().post("/concepts/normalize/convert", json=bad_id).status_code == 422
