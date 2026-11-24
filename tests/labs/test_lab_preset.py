import random

import pytest

from backend.services.lab_preset import address_argv, apply_preset
from backend.services.lab_scenario import parse_scenario, render
from integrations.labs.base import ExecResult, LabRuntimeError
from tests.fakes import FakeLabRuntime

SCENARIO = b"""
id: LAB-900
title: preset
type: build
concepts: [NET-010]
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


def lab():
    return render(parse_scenario(SCENARIO), 4, random.Random(0))


def test_preset_commands_are_fixed():
    assert address_argv("host", "eth1", "10.1.1.10/24") == ["ip", "addr", "add", "10.1.1.10/24", "dev", "eth1"]
    assert address_argv("router", "eth2", "10.1.1.1/24") == [
        "vtysh", "-c", "configure terminal", "-c", "interface eth2", "-c", "ip address 10.1.1.1/24",
    ]


def test_apply_preset_runs_one_command_per_address():
    runtime = FakeLabRuntime({
        ("pc1", tuple(address_argv("host", "eth1", "10.1.1.10/24"))): ExecResult(0, "", ""),
        ("r1", tuple(address_argv("router", "eth1", "10.1.1.1/24"))): ExecResult(0, "", ""),
    })
    apply_preset(runtime, lab())
    assert [(run, node) for run, node, _ in runtime.calls] == [("nr-4", "pc1"), ("nr-4", "r1")]


def test_apply_preset_failure_raises():
    runtime = FakeLabRuntime({
        ("pc1", tuple(address_argv("host", "eth1", "10.1.1.10/24"))): ExecResult(2, "", "RTNETLINK answers: File exists"),
    })
    with pytest.raises(LabRuntimeError, match="pc1:eth1에 10.1.1.10/24를 넣지 못했습니다: RTNETLINK answers: File exists"):
        apply_preset(runtime, lab())
