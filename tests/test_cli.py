import pytest

from backend import cli
from integrations.labs.base import ExecResult
from tests.fakes import FakeLabRuntime
from tests.labs.lab_fixtures import ADDR, FIRST, LAST, addr_json, solve_lab_001, write_fixed_scenarios


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    runtime = FakeLabRuntime()
    monkeypatch.setattr(cli, "containerlab_from_env", lambda: runtime)
    monkeypatch.setattr(cli, "DEFAULT_SCENARIOS_DIR", write_fixed_scenarios(tmp_path / "labs"))
    monkeypatch.setenv("NETRECALL_DATABASE_URL", f"sqlite:///{tmp_path / 'cli.db'}")
    return runtime


def test_lab_cycle(runtime, capsys):
    assert cli.main(["lab", "list"]) == 0
    assert "LAB-001  대역의 첫 주소와 마지막 주소로 통신하기  (개념 NET-005, 60분)" in capsys.readouterr().out

    assert cli.main(["lab", "start", "LAB-001"]) == 0
    out = capsys.readouterr().out
    assert "실행 1 · LAB-001" in out and "net = 10.37.84.64/27" in out
    assert "docker exec -it clab-nr-1-pc1 sh" in out
    assert FIRST not in out and LAST not in out
    assert "  1. pc1 eth1에 대역의 첫 번째 사용 가능 주소가 있다" in out
    assert "남은 시간 60분" in out and "검증 0번" in out
    assert "검증    python -m backend.cli lab verify" in out and "끝내기  python -m backend.cli lab finish" in out

    for node in ("pc1", "pc2"):
        runtime.responses[(node, ADDR)] = ExecResult(0, addr_json({"eth1": []}), "")
    assert cli.main(["lab", "verify"]) == 1
    out = capsys.readouterr().out
    assert "검증 결과: 실패" in out and "  1. X pc1 eth1에 대역의 첫 번째 사용 가능 주소가 있다" in out
    assert "  5. O 검사가 가리키는 주소가" in out
    assert "5개 중 4개 실패 · 남은 시간 60분" in out and "고친 뒤 다시 검증: python -m backend.cli lab verify" in out
    assert FIRST not in out and "[pc1:eth1 목표 주소]" in out

    solve_lab_001(runtime)
    assert cli.main(["lab", "verify", "1"]) == 0
    out = capsys.readouterr().out
    assert "검증 결과: 통과 (실행 1, passed)" in out and "모든 검사를 통과했습니다" in out
    assert "끝내기: python -m backend.cli lab finish" in out

    assert cli.main(["lab", "status"]) == 0
    out = capsys.readouterr().out
    assert "검증 2번" in out and "남은 시간" in out

    assert cli.main(["lab", "finish"]) == 0
    out = capsys.readouterr().out
    assert "실행 1을 끝냈습니다 (passed)" in out and "실습 환경을 지웠습니다" in out
    assert runtime.list_runs() == []


def test_errors_exit_2(runtime, capsys):
    assert cli.main(["lab", "verify"]) == 2
    assert "진행 중인 실습이 없습니다" in capsys.readouterr().err
    assert cli.main(["lab", "start", "LAB-404"]) == 2
    assert cli.main(["lab", "start", "LAB-001"]) == 0
    assert cli.main(["lab", "start", "LAB-001"]) == 2
    assert "진행 중인 실습이 있습니다 (실행 1)" in capsys.readouterr().err


def test_env_file(runtime, tmp_path, monkeypatch, capsys):
    env = tmp_path / "test.env"
    env.write_text(f"NETRECALL_DATABASE_URL=sqlite:///{tmp_path / 'from-env.db'}\n")
    monkeypatch.delenv("NETRECALL_DATABASE_URL")
    assert cli.main(["--env-file", str(env), "lab", "list"]) == 0
    assert (tmp_path / "from-env.db").exists()
    assert cli.main(["--env-file", str(env), "lab", "start", "LAB-001"]) == 0
    assert f"python -m backend.cli --env-file {env} lab verify" in capsys.readouterr().out  # 안내 명령도 같은 파일을 쓴다
