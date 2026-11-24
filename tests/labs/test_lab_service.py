import random
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from backend.database import init_db, make_engine, make_session_factory
from backend.models import LabAttempt, LabResult, LabRun
from backend.services import lab_service as labs
from backend.services.lab_checks import UNIQUE_CHECK_ID
from backend.services.lab_preset import address_argv
from backend.services.lab_scenario import parse_scenario, render
from integrations.labs.base import Endpoint, ExecResult, LabRuntimeError
from tests.fakes import FakeLabRuntime
from tests.labs.lab_fixtures import FIRST, LAST, fixed_lab_001_text, solve_lab_001

NOW = datetime(2026, 11, 24, 5, 0, tzinfo=UTC)
PRESET_SCENARIO = b"""
id: LAB-900
title: preset
type: build
concepts: [NET-010]
time_limit_minutes: 30
parameters:
  lan: {pool: 10.1.1.0/24, prefix: 24}
nodes:
  pc1: {kind: host}
  r1:  {kind: router}
links:
  - [pc1:eth1, r1:eth1]
preset:
  addresses:
    pc1:eth1: lan.host(10)
    r1:eth1:  lan.host(1)
goal: ping
checks:
  - id: r1-to-pc1
    description: R1 -> PC1
    ping: {from: r1, to: pc1:eth1}
"""


@pytest.fixture
def session(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'lab.db'}")
    init_db(engine)
    with make_session_factory(engine)() as s:
        yield s
    engine.dispose()


@pytest.fixture
def scenario():
    return parse_scenario(fixed_lab_001_text().encode())


def start(session, runtime, scenario, now=NOW):
    return labs.start_run(session, runtime, scenario, now, rng=random.Random(0))


def test_start_deploys_and_records_the_run(session, scenario):
    runtime = FakeLabRuntime()
    run = start(session, runtime, scenario)
    assert (run.id, run.status, run.scenario_id, run.mode) == (1, "active", "LAB-001", "build")
    assert runtime.list_runs() == ["nr-1"]
    assert run.params_json == {"net": "10.37.84.64/27"}
    assert run.topology_json == {"nodes": [["pc1", "host"], ["pc2", "host"]], "links": [["pc1:eth1", "pc2:eth1"]],
                                 "preset_addresses": []}
    assert run.checks_json["expected_addresses"] == {FIRST: "pc1:eth1", LAST: "pc2:eth1"}
    assert run.containerlab_version == "fake 1.0" and run.image_digests_json["host"]["id"] == "sha256:host"
    assert run.scenario_hash == scenario.source_hash
    assert run.expires_at == NOW + timedelta(minutes=60)
    assert "10.37.84.64/27" in run.goal


def test_rendered_lab_survives_the_database(session, scenario, tmp_path):
    run = start(session, FakeLabRuntime(), scenario)
    expected = render(scenario, 1, random.Random(0))
    session.expire_all()  # DB에서 다시 읽는다 (시각은 시간대 없이 돌아온다)
    assert labs.rendered_lab(session.get(LabRun, run.id)) == expected


def test_only_one_run_at_a_time(session, scenario):
    runtime = FakeLabRuntime()
    start(session, runtime, scenario)
    with pytest.raises(labs.RunInProgress, match="실행 1"):
        start(session, runtime, scenario)


def test_failed_deploy_is_recorded_and_frees_the_slot(session, scenario):
    runtime = FakeLabRuntime()

    def broken(run_name, topology):
        raise LabRuntimeError("이미지를 받지 못했습니다")

    runtime.deploy = broken
    with pytest.raises(labs.DeployFailed, match="이미지를 받지 못했습니다") as info:
        start(session, runtime, scenario)
    run = info.value.run
    assert (run.status, run.error, run.destroyed_at) == ("deploy_failed", "이미지를 받지 못했습니다", NOW)
    assert labs.current_run(session) is None


def test_failed_preset_destroys_the_environment(session):
    runtime = FakeLabRuntime()  # 준비한 응답이 없어 preset 명령이 실패한다
    with pytest.raises(labs.DeployFailed, match="pc1:eth1에 10.1.1.10/24를 넣지 못했습니다"):
        start(session, runtime, parse_scenario(PRESET_SCENARIO))
    assert runtime.list_runs() == []


def test_preset_is_applied_after_deploy(session):
    runtime = FakeLabRuntime({
        ("pc1", tuple(address_argv("host", "eth1", "10.1.1.10/24"))): ExecResult(0, "", ""),
        ("r1", tuple(address_argv("router", "eth1", "10.1.1.1/24"))): ExecResult(0, "", ""),
    })
    run = start(session, runtime, parse_scenario(PRESET_SCENARIO))
    assert run.status == "active" and len(runtime.calls) == 2


def test_unknown_evaluation(session, scenario):
    with pytest.raises(labs.EvaluationNotFound):
        labs.start_run(session, FakeLabRuntime(), scenario, NOW, evaluation_id=99)


def test_verify_records_attempts_and_passes(session, scenario):
    runtime = FakeLabRuntime()
    run = start(session, runtime, scenario)

    first = labs.verify_run(session, runtime, run.id, NOW + timedelta(minutes=1))
    assert (first.kind, first.passed, run.status) == ("verify", False, "active")
    assert set(first.state_json) == {"pc1", "pc2"}
    assert first.state_json["pc1"]["addresses"]["argv"] == ["ip", "-j", "addr", "show"]

    solve_lab_001(runtime)
    second = labs.verify_run(session, runtime, run.id, NOW + timedelta(minutes=5))
    assert second.passed and run.status == "passed"
    results = labs.results_of(session, second.id)
    assert [r.check_id for r in results] == ["pc1-address", "pc2-address", "pc1-to-pc2", "pc2-to-pc1", UNIQUE_CHECK_ID]
    assert all(r.passed for r in results)

    # 통과한 뒤에도 끝내기 전까지 다시 검증할 수 있다
    assert labs.verify_run(session, runtime, run.id, NOW + timedelta(minutes=6)).passed


def test_finish_collects_final_state_and_destroys(session, scenario):
    runtime = FakeLabRuntime()
    run = start(session, runtime, scenario)
    labs.finish_run(session, runtime, run.id, NOW + timedelta(minutes=3))
    assert (run.status, run.destroyed_at, run.finished_at) == ("abandoned", NOW + timedelta(minutes=3), NOW + timedelta(minutes=3))
    assert runtime.list_runs() == []
    assert [(a.kind, a.passed) for a in labs.attempts_of(session, run.id)] == [("final", None)]
    labs.finish_run(session, runtime, run.id, NOW + timedelta(minutes=4))  # 두 번 불러도 된다
    assert len(labs.attempts_of(session, run.id)) == 1
    with pytest.raises(labs.RunNotActive, match="끝낸 실습"):
        labs.verify_run(session, runtime, run.id, NOW + timedelta(minutes=5))


def test_finishing_a_passed_run_keeps_passed(session, scenario):
    runtime = FakeLabRuntime()
    run = start(session, runtime, scenario)
    solve_lab_001(runtime)
    labs.verify_run(session, runtime, run.id, NOW)
    labs.finish_run(session, runtime, run.id, NOW + timedelta(minutes=1))
    assert run.status == "passed" and run.destroyed_at is not None


def test_time_limit_expires_runs(session, scenario):
    runtime = FakeLabRuntime()
    run = start(session, runtime, scenario)
    assert labs.expire_overdue(session, runtime, NOW + timedelta(minutes=59)) == []
    with pytest.raises(labs.RunNotActive, match="시간 제한"):
        labs.verify_run(session, runtime, run.id, NOW + timedelta(minutes=61))
    assert (run.status, runtime.list_runs()) == ("expired", [])
    assert [a.kind for a in labs.attempts_of(session, run.id)] == ["final"]
    # 정리한 뒤에는 새 실습을 시작할 수 있다
    assert start(session, runtime, scenario, NOW + timedelta(minutes=62)).id == 2


def test_passed_run_is_cleaned_at_time_limit_but_stays_passed(session, scenario):
    runtime = FakeLabRuntime()
    run = start(session, runtime, scenario)
    solve_lab_001(runtime)
    labs.verify_run(session, runtime, run.id, NOW)
    assert labs.expire_overdue(session, runtime, NOW + timedelta(hours=2)) == [run.id]
    assert run.status == "passed" and run.destroyed_at == NOW + timedelta(hours=2)


def test_destroy_failure_is_kept_for_the_next_cleanup(session, scenario):
    runtime = FakeLabRuntime()
    run = start(session, runtime, scenario)

    def broken(run_name):
        raise LabRuntimeError("docker가 응답하지 않습니다")

    runtime.destroy = broken
    labs.finish_run(session, runtime, run.id, NOW)
    assert run.status == "abandoned" and run.destroyed_at is None
    assert "정리하지 못했습니다" in run.error
    assert labs.current_run(session) is None  # 끝난 실행이라 새 실습을 막지 않는다


def add_run(session, status, destroyed_at=None) -> LabRun:
    run = LabRun(scenario_id="LAB-001", scenario_hash="h", mode="build", status=status, params_json={},
                 topology_json={"nodes": [], "links": [], "preset_addresses": []},
                 checks_json={"checks": [], "expected_addresses": {}}, goal="", image_digests_json={},
                 containerlab_version="", started_at=NOW, expires_at=NOW + timedelta(hours=1), destroyed_at=destroyed_at)
    session.add(run)
    session.commit()
    return run


def test_cleanup_orphans_on_startup(session):
    finished = add_run(session, "abandoned")       # 정리하지 못하고 끝난 실행: 환경이 남음
    crashed = add_run(session, "deploying")        # 배포 중에 앱이 멈춤: 환경이 남음
    vanished = add_run(session, "active")          # 진행 중인데 환경이 사라짐
    alive = add_run(session, "active")             # 진행 중, 환경 있음
    runtime = FakeLabRuntime()
    for name in (f"nr-{finished.id}", f"nr-{crashed.id}", f"nr-{alive.id}", "nr-999"):
        runtime.deployed[name] = None

    removed = labs.cleanup_orphans(session, runtime, NOW)
    assert removed == [f"nr-{finished.id}", f"nr-{crashed.id}"]
    assert runtime.list_runs() == [f"nr-{alive.id}", "nr-999"]  # 이 DB가 만들지 않은 실습은 그대로
    assert (crashed.status, crashed.error) == ("deploy_failed", "배포 중에 앱이 멈췄습니다")
    assert (vanished.status, vanished.error) == ("abandoned", "실습 환경이 사라졌습니다")
    assert vanished.destroyed_at == NOW and finished.destroyed_at == NOW
    assert alive.status == "active" and alive.destroyed_at is None


def test_hidden_addresses_and_redaction(scenario):
    lab = render(scenario, 1, random.Random(0))
    hidden = labs.hidden_addresses(lab)
    assert hidden == {FIRST: Endpoint("pc1", "eth1"), LAST: Endpoint("pc2", "eth1")}
    text = f"eth1에 {FIRST}/27가 없습니다\nPING {LAST} ({LAST}) 56(84)\n10.37.84.6 10.37.84.651 110.37.84.65"
    assert labs.redact(text, hidden) == (
        "eth1에 [pc1:eth1 목표 주소]/27가 없습니다\nPING [pc2:eth1 목표 주소] ([pc2:eth1 목표 주소]) 56(84)\n"
        "10.37.84.6 10.37.84.651 110.37.84.65"
    )
    # preset으로 준 주소는 학습자가 이미 안다
    assert labs.hidden_addresses(render(parse_scenario(PRESET_SCENARIO), 1, random.Random(0))) == {}


def test_load_scenarios_reports_broken_files(tmp_path):
    (tmp_path / "LAB-001").mkdir()
    (tmp_path / "LAB-001" / "scenario.yaml").write_text(fixed_lab_001_text())
    (tmp_path / "LAB-002").mkdir()
    (tmp_path / "LAB-002" / "scenario.yaml").write_text("id: LAB-002\n")
    (tmp_path / "notes").mkdir()  # scenario.yaml이 없는 폴더는 무시한다
    scenarios, errors = labs.load_scenarios(tmp_path)
    assert [s.id for s in scenarios] == ["LAB-001"]
    assert errors == [("LAB-002", "'title'가 없습니다")]
    with pytest.raises(labs.ScenarioNotFound):
        labs.find_scenario(tmp_path, "LAB-002")


def test_results_are_stored_per_check(session, scenario):
    runtime = FakeLabRuntime()
    run = start(session, runtime, scenario)
    attempt = labs.verify_run(session, runtime, run.id, NOW)
    stored = session.scalars(select(LabResult).where(LabResult.attempt_id == attempt.id)).all()
    assert len(stored) == 5 and not any(r.passed for r in stored[:4])
    assert session.scalar(select(LabAttempt.passed).where(LabAttempt.id == attempt.id)) is False
