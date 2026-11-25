"""시나리오별 기준 풀이·오답 (설계서 §D-5 "검증기 테스트").

`tests/labs/solutions/<시나리오 id>/cases.yaml`을 읽는다. 형식은 docs/lab-scenario-format.md "기준 풀이와 오답".
- 형식 검사는 기본 `pytest`에서 Docker 없이 돈다.
- 실제 검사는 `pytest -m lab`: 배포 → preset → 풀이 명령 → 검증 → 정리. 기준 풀이는 모든 검사를 통과하고,
  오답은 `fails`에 적은 검사만 실패해야 한다.
"""
import ipaddress
import random
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from backend.services.lab_checks import UNIQUE_CHECK_ID, verify
from backend.services.lab_preset import apply_preset
from backend.services.lab_scenario import _offset, load_scenario, render
from integrations.labs.containerlab.runtime import ContainerlabRuntime
from tests.labs.lab_fixtures import ROOT, labelled, live_run_id, require_lab_tools

SOLUTIONS = Path(__file__).parent / "solutions"
SCENARIOS = ROOT / "lab_scenarios"
CASE_KEYS = {"id", "description", "steps", "fails"}
TOKEN = re.compile(r"\{([^{}]*)\}")
VALUE = re.compile(r"^([a-z][a-z0-9_]*)\.(?:host\((-?[0-9]+)\)|(prefix|netmask|network))$")


@dataclass(frozen=True)
class Case:
    scenario_id: str
    kind: str                      # solution | wrong
    id: str
    description: str
    steps: dict[str, list[str]]    # 노드 → 차례로 실행할 명령
    fails: frozenset[str]          # 오답이 실패해야 하는 검사 id (기준 풀이는 비어 있다)


def load_cases(path: Path) -> list[Case]:
    raw = yaml.safe_load(path.read_text())
    assert set(raw) <= {"solutions", "wrong"}, f"{path}: 모르는 키 {set(raw) - {'solutions', 'wrong'}}"
    cases = []
    for key, kind in (("solutions", "solution"), ("wrong", "wrong")):
        for item in raw.get(key) or []:
            assert set(item) <= CASE_KEYS, f"{path} {item.get('id')}: 모르는 키 {set(item) - CASE_KEYS}"
            steps = {node: list(commands) for node, commands in item["steps"].items()}
            cases.append(Case(path.parent.name, kind, item["id"], item["description"], steps,
                              frozenset(item.get("fails") or ())))
    return cases


def fill(command: str, networks: dict[str, str]) -> list[str]:
    """`{대역.host(n)}`·`{대역.prefix}`·`{대역.netmask}`·`{대역.network}`을 이번 실행의 값으로 바꿔 인자 목록으로."""
    def value(m: re.Match) -> str:
        v = VALUE.match(m.group(1))
        if v is None or v.group(1) not in networks:
            raise ValueError(f"모르는 식입니다: {m.group(0)}")
        net = ipaddress.ip_network(networks[v.group(1)])
        if v.group(2) is not None:
            address = net.network_address + _offset(int(v.group(2)), net.prefixlen)
            if not net.network_address < address < net.broadcast_address:
                raise ValueError(f"{m.group(0)}이 {net}의 사용 가능 주소가 아닙니다")
            return str(address)
        return {"prefix": str(net.prefixlen), "netmask": str(net.netmask),
                "network": str(net.network_address)}[v.group(3)]
    return shlex.split(TOKEN.sub(value, command))


ALL_CASES = [c for path in sorted(SOLUTIONS.glob("*/cases.yaml")) for c in load_cases(path)]


def case_id(case: Case) -> str:
    return f"{case.scenario_id}-{case.kind}-{case.id}"


# ---- 형식 (기본 pytest) ----

def test_every_scenario_has_solutions_and_wrong_answers():
    scenarios = sorted(d.name for d in SCENARIOS.iterdir() if (d / "scenario.yaml").exists())
    assert sorted({c.scenario_id for c in ALL_CASES}) == scenarios
    for scenario_id in scenarios:
        kinds = [c.kind for c in ALL_CASES if c.scenario_id == scenario_id]
        assert "solution" in kinds and "wrong" in kinds, scenario_id
        ids = [c.id for c in ALL_CASES if c.scenario_id == scenario_id]
        assert len(ids) == len(set(ids)), f"{scenario_id}: 겹치는 id"


@pytest.mark.parametrize("case", ALL_CASES, ids=case_id)
def test_case_is_well_formed(case):
    scenario = load_scenario(SCENARIOS / case.scenario_id)
    assert case.steps and set(case.steps) <= {n.name for n in scenario.nodes}
    if case.kind == "solution":
        assert not case.fails
    else:
        assert case.fails and case.fails <= {c.id for c in scenario.checks} | {UNIQUE_CHECK_ID}
    lab = render(scenario, 1, random.Random(0))
    for commands in case.steps.values():
        assert commands
        for command in commands:
            fill(command, lab.networks)


def test_fill():
    networks = {"net": "10.37.84.64/27"}
    assert fill("ip addr add {net.host(1)}/{net.prefix} dev eth1", networks) == \
        ["ip", "addr", "add", "10.37.84.65/27", "dev", "eth1"]
    assert fill("ifconfig eth1 {net.host(-1)} netmask {net.netmask}", networks) == \
        ["ifconfig", "eth1", "10.37.84.94", "netmask", "255.255.255.224"]
    assert fill("{net.network}", networks) == ["10.37.84.64"]
    for bad in ("{lan.prefix}", "{net.broadcast}", "{net.host(x)}"):
        with pytest.raises(ValueError, match="모르는 식"):
            fill(bad, networks)
    for outside in ("{net.host(0)}", "{net.host(31)}", "{net.host(-31)}"):  # /27의 사용 가능 주소는 host(1)~host(30)
        with pytest.raises(ValueError, match="사용 가능 주소가 아닙니다"):
            fill(outside, networks)
    assert fill("{net.host(30)} {net.host(-30)}", networks) == ["10.37.84.94", "10.37.84.65"]


# ---- 실제 Containerlab (pytest -m lab) ----

@pytest.mark.lab
@pytest.mark.parametrize("case", ALL_CASES, ids=case_id)
def test_case_on_containerlab(case, tmp_path):
    require_lab_tools()
    runtime = ContainerlabRuntime(tmp_path)
    lab = render(load_scenario(SCENARIOS / case.scenario_id), live_run_id())
    runtime.deploy(lab.run_name, lab.topology)
    try:
        apply_preset(runtime, lab)
        for node, commands in case.steps.items():
            for command in commands:
                argv = fill(command, lab.networks)
                r = runtime.exec(lab.run_name, node, argv)
                assert r.exit_code == 0, f"{node}: {shlex.join(argv)} → {(r.stderr or r.stdout).strip()}"
        result = verify(runtime, lab)
    finally:
        runtime.destroy(lab.run_name)
    detail = f"대역 {lab.networks} | " + " | ".join(
        f"{'O' if r.passed else 'X'} {r.id}: {r.message}" for r in result.results)
    assert {r.id for r in result.results if not r.passed} == case.fails, detail
    assert result.passed == (case.kind == "solution")
    assert labelled(lab.run_name) == 0
