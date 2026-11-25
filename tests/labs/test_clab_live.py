"""실제 Containerlab 통합 테스트. `pytest -m lab`으로만 돈다.

필요한 것: containerlab(clab_admins 그룹), docker 그룹, 이미지 두 개
(`docker build -t netrecall/lab-host:1 integrations/labs/images/host`, `docker pull quay.io/frrouting/frr:10.7.1`).
명시해서 돌리는 테스트라 준비가 안 됐으면 건너뛰지 않고 실패한다.
"""
from pathlib import Path

import pytest

from backend.services.lab_checks import verify
from backend.services.lab_preset import apply_preset
from backend.services.lab_scenario import load_scenario, parse_scenario, render
from integrations.labs.base import LabRuntimeError
from integrations.labs.containerlab import runtime as rt
from integrations.labs.containerlab.runtime import ContainerlabRuntime
from integrations.labs.containerlab.topology import IMAGES
from tests.labs.lab_fixtures import labelled, require_lab_tools
from tests.labs.lab_fixtures import live_run_id as run_id

pytestmark = pytest.mark.lab
ROOT = Path(__file__).resolve().parents[2]

ROUTER_SCENARIO = b"""
id: LAB-900
title: router
type: build
concepts: [NET-010]
parameters:
  lan: {pool: 10.0.0.0/8, prefix: 24}
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
    description: R1 -> PC1 ping
    ping: {from: r1, to: pc1:eth1}
  - id: r1-route
    description: R1 connected route
    route: {node: r1, to: pc1:eth1, protocol: [connected]}
  - id: pc1-route
    description: PC1 route
    route: {node: pc1, to: r1:eth1}
"""


@pytest.fixture(scope="module", autouse=True)
def ready():
    require_lab_tools()


@pytest.fixture
def runtime(tmp_path):
    return ContainerlabRuntime(tmp_path)


def test_lab_001_deploy_verify_destroy(runtime, monkeypatch):
    lab = render(load_scenario(ROOT / "lab_scenarios" / "LAB-001"), run_id())
    runtime.deploy(lab.run_name, lab.topology)
    try:
        assert lab.run_name in runtime.list_runs()
        before = verify(runtime, lab)
        assert not before.passed and [r.passed for r in before.results][:4] == [False] * 4

        first, last = lab.checks[0].target, lab.checks[1].target
        for node, address in (("pc1", first), ("pc2", last)):
            assert runtime.exec(lab.run_name, node, ["ip", "addr", "add", address, "dev", "eth1"]).exit_code == 0
        after = verify(runtime, lab)
        assert after.passed, [(r.id, r.message) for r in after.results]

        with pytest.raises(LabRuntimeError, match="No such container"):
            runtime.exec(lab.run_name, "pc9", ["true"])
        monkeypatch.setattr(rt, "EXEC_TIMEOUT", 1)
        with pytest.raises(LabRuntimeError, match="1초 안에 끝나지 않았습니다"):
            runtime.exec(lab.run_name, "pc1", ["sleep", "5"])
    finally:
        runtime.destroy(lab.run_name)
    assert lab.run_name not in runtime.list_runs()
    assert labelled(lab.run_name) == 0
    runtime.destroy(lab.run_name)  # 두 번 불러도 된다


def test_router_is_ready_and_preset_is_applied(runtime):
    lab = render(parse_scenario(ROUTER_SCENARIO), run_id())
    runtime.deploy(lab.run_name, lab.topology)
    try:
        version = runtime.exec(lab.run_name, "r1", ["vtysh", "-c", "show version"])
        assert version.exit_code == 0 and "Can't open configuration file" not in version.stdout + version.stderr

        apply_preset(runtime, lab)
        r1_address = dict((str(e), a) for e, a in lab.preset_addresses)["r1:eth1"]
        running = runtime.exec(lab.run_name, "r1", ["vtysh", "-c", "show running-config"]).stdout
        assert f"ip address {r1_address}" in running  # 학습자가 보는 설정에 preset이 나온다

        result = verify(runtime, lab)
        assert result.passed, [(r.id, r.message) for r in result.results]
        assert "running_config" in result.state["r1"]
    finally:
        runtime.destroy(lab.run_name)
    assert labelled(lab.run_name) == 0


def test_failed_deploy_leaves_nothing(runtime, monkeypatch):
    monkeypatch.setitem(IMAGES, "host", "netrecall/lab-host:does-not-exist")
    lab = render(load_scenario(ROOT / "lab_scenarios" / "LAB-001"), run_id())
    with pytest.raises(LabRuntimeError, match="배포에 실패했습니다"):
        runtime.deploy(lab.run_name, lab.topology)
    assert labelled(lab.run_name) == 0
    assert not (runtime.work_dir / f"{lab.run_name}.clab.yml").exists()
