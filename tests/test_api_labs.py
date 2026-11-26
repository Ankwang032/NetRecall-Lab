from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from backend.api import labs as labs_api
from backend.main import create_app
from backend.models.concept import utcnow
from integrations.labs.base import ExecResult, LabRuntimeError
from tests.fakes import FakeLabRuntime
from tests.labs.lab_fixtures import ADDR, FIRST, LAST, addr_json, solve_lab_001, write_fixed_scenarios


@pytest.fixture
def runtime():
    return FakeLabRuntime()


@pytest.fixture
def client(tmp_path, runtime):
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}", tmp_path / "concepts", lab_runtime=runtime,
                     scenarios_dir=write_fixed_scenarios(tmp_path / "labs"))
    return TestClient(app)


def test_list_labs(client):
    body = client.get("/labs").json()
    assert body["scenarios"] == [{
        "id": "LAB-001", "title": "대역의 첫 주소와 마지막 주소로 통신하기", "type": "build",
        "concepts": ["NET-005"], "time_limit_minutes": 60, "last_run": None,
    }]
    assert body["errors"] == []


def test_list_labs_shows_last_run(client, runtime):
    client.post("/labs/LAB-001/runs")
    client.post("/lab-runs/1/finish")
    client.post("/labs/LAB-001/runs", json={"level": "easy"})
    client.post("/lab-runs/2/hints")
    solve_lab_001(runtime)
    client.post("/lab-runs/2/attempts")
    last = client.get("/labs").json()["scenarios"][0]["last_run"]
    assert {k: last[k] for k in ("run_id", "status", "level", "attempts", "attempts_to_pass", "hints_used",
                                 "finished_at")} == \
        {"run_id": 2, "status": "passed", "level": "easy", "attempts": 1, "attempts_to_pass": 1, "hints_used": 1,
         "finished_at": None}
    assert last["passed_at"].endswith("+09:00")


def test_list_labs_checks_time_limit(client, runtime, monkeypatch):
    client.post("/labs/LAB-001/runs")
    later = utcnow() + timedelta(minutes=61)
    monkeypatch.setattr(labs_api, "utcnow", lambda: later)
    assert client.get("/labs").json()["scenarios"][0]["last_run"]["status"] == "expired"
    assert runtime.list_runs() == []


def test_repo_scenarios_are_served_by_default(tmp_path):
    client = TestClient(create_app(f"sqlite:///{tmp_path / 'api.db'}", tmp_path, lab_runtime=FakeLabRuntime()))
    assert [s["id"] for s in client.get("/labs").json()["scenarios"]] == ["LAB-001", "LAB-002"]


def test_full_run(client, runtime):
    res = client.post("/labs/LAB-001/runs")
    assert res.status_code == 201
    run = res.json()
    assert (run["run_id"], run["status"], run["networks"]) == (1, "active", {"net": "10.37.84.64/27"})
    assert "10.37.84.64/27" in run["goal"]
    assert run["nodes"] == [
        {"name": "pc1", "kind": "host", "connect": "docker exec -it clab-nr-1-pc1 sh"},
        {"name": "pc2", "kind": "host", "connect": "docker exec -it clab-nr-1-pc2 sh"},
    ]
    assert run["addresses"] == []
    assert run["links"] == [{"a": "pc1:eth1", "b": "pc2:eth1"}]
    assert (run["hints"], run["last_attempt"]) == ({}, None)
    assert [c["id"] for c in run["checks"]] == ["pc1-address", "pc2-address", "pc1-to-pc2", "pc2-to-pc1"]
    assert FIRST not in str(run) and LAST not in str(run)  # 정답 주소를 내보내지 않는다
    assert run["started_at"].endswith("+09:00") and run["attempts"] == 0
    assert client.get("/lab-runs/current").json()["run_id"] == 1

    for node in ("pc1", "pc2"):  # 아직 아무것도 설정하지 않음
        runtime.responses[(node, ADDR)] = ExecResult(0, addr_json({"lo": ["127.0.0.1/8"], "eth1": []}), "")
    res = client.post("/lab-runs/1/attempts")
    assert res.status_code == 201
    attempt = res.json()
    assert (attempt["passed"], attempt["run_status"]) == (False, "active")
    by_id = {r["check_id"]: r for r in attempt["results"]}
    assert by_id["pc1-address"]["message"] == "eth1에 [pc1:eth1 목표 주소]/27가 없습니다"
    assert by_id["pc1-to-pc2"]["message"] == "[pc2:eth1 목표 주소]에서 응답이 없습니다"
    assert by_id["auto:unique-addresses"]["kind"] == "unique"
    assert FIRST not in str(attempt) and LAST not in str(attempt)

    solve_lab_001(runtime)
    attempt = client.post("/lab-runs/1/attempts").json()
    assert (attempt["passed"], attempt["run_status"]) == (True, "passed")
    run = client.get("/lab-runs/1").json()
    assert run["attempts"] == 2 and run["passed_at"] == attempt["attempted_at"]
    assert run["last_attempt"] == attempt  # 화면을 새로 열어도 마지막 검증 결과를 보여 준다

    res = client.post("/lab-runs/1/finish")
    assert res.status_code == 200
    assert (res.json()["status"], runtime.list_runs()) == ("passed", [])
    assert res.json()["finished_at"] is not None
    assert client.get("/lab-runs/current").json() is None
    assert client.post("/lab-runs/1/attempts").status_code == 409


def test_errors(client, runtime):
    assert client.post("/labs/LAB-404/runs").status_code == 404
    assert client.post("/labs/LAB-001/runs", json={"evaluation_id": 7}).status_code == 404
    assert client.get("/lab-runs/5").status_code == 404
    assert client.post("/lab-runs/5/attempts").status_code == 404
    assert client.post("/lab-runs/5/finish").status_code == 404

    assert client.post("/labs/LAB-001/runs").status_code == 201
    res = client.post("/labs/LAB-001/runs")
    assert res.status_code == 409 and "실행 1" in res.json()["detail"]


def test_deploy_failure_is_502(client, runtime):
    def broken(run_name, topology):
        raise LabRuntimeError("containerlab을 실행하지 못했습니다")

    runtime.deploy = broken
    res = client.post("/labs/LAB-001/runs")
    assert res.status_code == 502 and "containerlab을 실행하지 못했습니다" in res.json()["detail"]
    assert client.get("/lab-runs/1").json()["status"] == "deploy_failed"


def test_time_limit_is_checked_on_requests(client, runtime, monkeypatch):
    client.post("/labs/LAB-001/runs")
    later = utcnow() + timedelta(minutes=61)
    monkeypatch.setattr(labs_api, "utcnow", lambda: later)
    assert client.get("/lab-runs/current").json() is None
    assert client.get("/lab-runs/1").json()["status"] == "expired"
    assert runtime.list_runs() == []
    res = client.post("/lab-runs/1/attempts")
    assert res.status_code == 409 and "시간 제한" in res.json()["detail"]


def test_startup_cleans_up_finished_runs(tmp_path):
    runtime = FakeLabRuntime()
    url = f"sqlite:///{tmp_path / 'api.db'}"
    scenarios = write_fixed_scenarios(tmp_path / "labs")
    first = TestClient(create_app(url, tmp_path, lab_runtime=runtime, scenarios_dir=scenarios))
    first.post("/labs/LAB-001/runs")
    runtime.deployed["nr-500"] = None  # 다른 DB가 만든 실습

    # 앱이 멈춘 사이 실습 환경이 사라졌다
    runtime.deployed.pop("nr-1")
    with TestClient(create_app(url, tmp_path, lab_runtime=runtime, scenarios_dir=scenarios)) as client:
        run = client.get("/lab-runs/1").json()
    assert (run["status"], run["error"]) == ("abandoned", "실습 환경이 사라졌습니다")
    assert runtime.list_runs() == ["nr-500"]


def test_startup_survives_missing_docker(tmp_path):
    runtime = FakeLabRuntime()

    def broken():
        raise LabRuntimeError("docker를 실행하지 못했습니다")

    runtime.list_runs = broken
    with TestClient(create_app(f"sqlite:///{tmp_path / 'api.db'}", tmp_path, lab_runtime=runtime)) as client:
        assert client.get("/health").status_code == 200


def test_hints(client, runtime):
    run = client.post("/labs/LAB-001/runs").json()
    assert (run["level"], run["hint_limit"], run["hints_used"]) == ("normal", 2, 0)

    first = client.post("/lab-runs/1/hints")  # 본문 없이: 검증 전이면 첫 검사
    assert first.status_code == 200
    assert {k: first.json()[k] for k in ("check_id", "number", "new", "limit", "total")} == \
        {"check_id": "pc1-address", "number": 1, "new": True, "limit": 2, "total": 3}
    assert len(first.json()["hints"]) == 1
    second = client.post("/lab-runs/1/hints", json={"check_id": "pc1-address"}).json()
    third = client.post("/lab-runs/1/hints", json={"check_id": "pc1-address"}).json()
    assert (len(second["hints"]), second["new"], len(third["hints"]), third["new"]) == (2, True, 2, False)
    assert FIRST not in str(third)
    run = client.get("/lab-runs/1").json()
    assert run["hints_used"] == 2
    assert run["hints"] == {"pc1-address": third["hints"]}  # 새 단계를 열지 않고 본 힌트만
    assert client.get("/lab-runs/1").json()["hints_used"] == 2

    assert client.post("/lab-runs/1/hints", json={"check_id": "nope"}).status_code == 404
    assert client.post("/lab-runs/9/hints").status_code == 404
    client.post("/lab-runs/1/finish")
    assert client.post("/lab-runs/1/hints").status_code == 409


def test_hard_level_hides_checks_and_results_until_finished(client, runtime):
    run = client.post("/labs/LAB-001/runs", json={"level": "hard"}).json()
    assert (run["level"], run["hint_limit"], run["checks"]) == ("hard", 0, [])
    res = client.post("/lab-runs/1/hints")
    assert res.status_code == 409 and "어려움 난이도에서는 힌트가 없습니다" in res.json()["detail"]

    for node in ("pc1", "pc2"):
        runtime.responses[(node, ADDR)] = ExecResult(0, addr_json({"eth1": []}), "")
    attempt = client.post("/lab-runs/1/attempts").json()
    assert (attempt["passed"], attempt["passed_count"], attempt["total_count"], attempt["results"]) == (False, 1, 5, [])
    assert client.get("/lab-runs/1").json()["last_attempt"]["results"] == []

    finished = client.post("/lab-runs/1/finish").json()
    assert [c["id"] for c in finished["checks"]] == ["pc1-address", "pc2-address", "pc1-to-pc2", "pc2-to-pc1"]
    assert len(finished["last_attempt"]["results"]) == 5  # 끝나면 마지막 검증의 검사별 결과도 보여 준다


def test_level_must_be_known(client):
    assert client.post("/labs/LAB-001/runs", json={"level": "expert"}).status_code == 422
