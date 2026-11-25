"""실습 테스트 공통 도우미. 대역을 10.37.84.64/27로 고정한 LAB-001로 녹화한 출력(fixtures/)을 그대로 쓴다."""
import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.services.lab_checks import STATE_COMMANDS, ping_argv
from integrations.labs.base import ExecResult
from integrations.labs.containerlab.topology import IMAGES
from tests.fakes import FakeLabRuntime

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"
ADDR = tuple(STATE_COMMANDS["host"]["addresses"])
FIRST, LAST = "10.37.84.65", "10.37.84.94"


def require_lab_tools() -> None:
    """실제 배포 테스트(`pytest -m lab`)는 명시해서 돌리므로 준비가 안 됐으면 건너뛰지 않고 실패한다."""
    for tool in ("containerlab", "docker"):
        if shutil.which(tool) is None:
            pytest.fail(f"{tool}이 없습니다")
    for image in IMAGES.values():
        if subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode != 0:
            pytest.fail(f"이미지가 없습니다: {image}")


def live_run_id() -> int:
    return random.randint(900_000, 999_999)  # 앱의 실행 id와 겹치지 않게 큰 수를 쓴다


def labelled(run_name: str) -> int:
    """그 실습 이름이 붙은 컨테이너 수 (정리됐는지 확인)."""
    out = subprocess.run(["docker", "ps", "-aq", "--filter", f"label=containerlab={run_name}"],
                         capture_output=True, text=True).stdout
    return len(out.split())


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def addr_json(interfaces: dict[str, list[str]]) -> str:
    """`ip -j addr show`와 같은 모양(검사가 읽는 키만)."""
    return json.dumps([
        {"ifname": name, "addr_info": [
            {"family": "inet", "local": a.split("/")[0], "prefixlen": int(a.split("/")[1])} for a in addrs
        ]} for name, addrs in interfaces.items()
    ])


def fixed_lab_001_text() -> str:
    text = (ROOT / "lab_scenarios" / "LAB-001" / "scenario.yaml").read_text()
    return text.replace("{pool: 10.0.0.0/8, prefix: {min: 24, max: 30}}", "{pool: 10.37.84.64/27, prefix: 27}")


def write_fixed_scenarios(root: Path) -> Path:
    (root / "LAB-001").mkdir(parents=True)
    (root / "LAB-001" / "scenario.yaml").write_text(fixed_lab_001_text())
    return root


def solve_lab_001(runtime: FakeLabRuntime) -> None:
    """가짜 런타임이 정답 상태를 돌려주게 한다."""
    runtime.responses.update({
        ("pc1", ADDR): ExecResult(0, addr_json({"eth1": [f"{FIRST}/27"]}), ""),
        ("pc2", ADDR): ExecResult(0, addr_json({"eth1": [f"{LAST}/27"]}), ""),
        ("pc1", tuple(ping_argv(LAST))): ExecResult(0, fixture("l1_ping_ok.out"), ""),
        ("pc2", tuple(ping_argv(FIRST))): ExecResult(0, fixture("l1_ping_ok.out"), ""),
    })
