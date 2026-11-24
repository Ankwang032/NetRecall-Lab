"""검사 의미 테스트. Docker 없이 가짜 런타임에 실제 출력을 녹화한 자료(fixtures/)를 넣어 돌린다.

녹화: 2026-11-24 Codespaces, Containerlab 0.83.0, netrecall/lab-host:1(iproute2 7.0.0, iputils 20250605),
FRRouting 10.7.1. LAB-001 모양은 10.37.84.64/27, LAB-002 모양은 lan1 10.1.1.0/24 · transit 172.16.0.0/30 ·
lan2 10.2.2.0/24 (pc는 .10, 라우터는 .1·.2).
"""
import random

import pytest

from backend.services.lab_checks import STATE_COMMANDS, UNIQUE_CHECK_ID, collect_state, ping_argv, route_argv, verify
from backend.services.lab_scenario import parse_scenario, render
from integrations.labs.base import ExecResult, LabRuntimeError
from tests.fakes import FakeLabRuntime
from tests.labs.lab_fixtures import ADDR, addr_json, fixed_lab_001_text, fixture

BUSYBOX_PING_OK = """PING 10.1.1.10 (10.1.1.10): 56 data bytes
64 bytes from 10.1.1.10: seq=0 ttl=64 time=0.100 ms

--- 10.1.1.10 ping statistics ---
3 packets transmitted, 1 packets received, 66% packet loss
"""
BUSYBOX_PING_LOSS = """PING 10.2.2.10 (10.2.2.10): 56 data bytes

--- 10.2.2.10 ping statistics ---
3 packets transmitted, 0 packets received, 100% packet loss
"""

LAB_002_LIKE = """
id: LAB-900
title: 라우터 두 대
type: build
concepts: [NET-010]
parameters:
  lan1:    {pool: 10.1.1.0/24, prefix: 24}
  lan2:    {pool: 10.2.2.0/24, prefix: 24}
  transit: {pool: 172.16.0.0/30, prefix: 30}
nodes:
  pc1: {kind: host}
  r1:  {kind: router}
  r2:  {kind: router}
  pc2: {kind: host}
links:
  - [pc1:eth1, r1:eth1]
  - [r1:eth2, r2:eth2]
  - [r2:eth1, pc2:eth1]
preset:
  addresses:
    pc1:eth1: lan1.host(10)
    r1:eth1:  lan1.host(1)
    r1:eth2:  transit.host(1)
    r2:eth2:  transit.host(2)
    r2:eth1:  lan2.host(1)
    pc2:eth1: lan2.host(10)
goal: PC1과 PC2가 서로 ping되게 하라.
checks:
  - id: r1-to-pc1
    description: R1 → PC1 ping
    ping: {from: r1, to: pc1:eth1}
  - id: r1-route
    description: R1이 LAN2로 갈 때 직접 넣은 경로를 쓴다
    route: {node: r1, to: pc2:eth1}
  - id: r2-route
    description: R2가 LAN1로 갈 때 직접 넣은 경로를 쓴다
    route: {node: r2, to: pc1:eth1}
  - id: pc1-route
    description: PC1에 PC2로 가는 경로가 있다
    route: {node: pc1, to: pc2:eth1}
"""


def ok(stdout: str) -> ExecResult:
    return ExecResult(0, stdout, "")


def lab_001():
    return render(parse_scenario(fixed_lab_001_text().encode()), 1, random.Random(0))


def lab_002():
    return render(parse_scenario(LAB_002_LIKE.encode()), 2, random.Random(0))


def lab_001_runtime(pc1_addr: str, pc2_addr: str, pc1_ping: ExecResult, pc2_ping: ExecResult) -> FakeLabRuntime:
    return FakeLabRuntime({
        ("pc1", ADDR): ok(pc1_addr),
        ("pc2", ADDR): ok(pc2_addr),
        ("pc1", tuple(ping_argv("10.37.84.94"))): pc1_ping,
        ("pc2", tuple(ping_argv("10.37.84.65"))): pc2_ping,
    })


def results(verification):
    return {r.id: r for r in verification.results}


PC1_OK = fixture("l1_addr_after.out")  # 실제: pc1 eth1 10.37.84.65/27
PC2_OK = addr_json({"lo": ["127.0.0.1/8"], "eth1": ["10.37.84.94/27"]})
PING_OK = ok(fixture("l1_ping_ok.out"))


def test_commands_are_fixed_and_take_only_the_address():
    assert ping_argv("10.0.0.1") == ["ping", "-n", "-c", "3", "-W", "1", "10.0.0.1"]
    assert route_argv("host", "10.0.0.1") == ["ip", "-j", "route", "get", "10.0.0.1"]
    assert route_argv("router", "10.0.0.1") == ["vtysh", "-c", "show ip route 10.0.0.1 json"]


def test_lab_001_reference_solution_passes():
    v = verify(lab_001_runtime(PC1_OK, PC2_OK, PING_OK, PING_OK), lab_001())
    assert v.passed, [(r.id, r.message) for r in v.results]
    r = results(v)
    assert list(r) == ["pc1-address", "pc2-address", "pc1-to-pc2", "pc2-to-pc1", UNIQUE_CHECK_ID]
    assert r["pc1-address"].message == "eth1에 10.37.84.65/27가 있습니다"
    assert r["pc1-address"].output == "eth1: 10.37.84.65/27"
    assert r["pc1-to-pc2"].message == "10.37.84.94에서 3번 중 3번 응답했습니다"


def test_nothing_configured_fails_everything():
    empty = addr_json({"lo": ["127.0.0.1/8"], "eth1": []})
    unreachable = ExecResult(2, "", fixture("l1_ping_noaddr.err"))  # ping: connect: Network unreachable
    v = verify(lab_001_runtime(empty, empty, unreachable, unreachable), lab_001())
    r = results(v)
    assert not v.passed
    assert r["pc1-address"].message == "eth1에 10.37.84.65/27가 없습니다"
    assert r["pc1-address"].output == "eth1: (IPv4 주소 없음)"
    assert not r["pc1-to-pc2"].passed and "Network unreachable" in r["pc1-to-pc2"].output
    assert r[UNIQUE_CHECK_ID].passed  # 주소가 아예 없는 것은 유일성 위반이 아니다


def test_wrong_prefix_fails_the_address_check_even_though_ping_works():
    v = verify(lab_001_runtime(PC1_OK, fixture("l1_addr_wrongprefix.out"), PING_OK, PING_OK), lab_001())
    r = results(v)
    assert not v.passed
    assert r["pc1-to-pc2"].passed and r["pc2-to-pc1"].passed
    assert r["pc2-address"].message == "eth1의 10.37.84.94/24는 프리픽스 길이가 다릅니다 (기대: 10.37.84.94/27)"


def test_target_address_on_the_wrong_node_fails_uniqueness():
    # pc1의 lo에 pc2 주소를 넣으면 pc1 → pc2 ping이 pc1 안에서 성공한다
    v = verify(lab_001_runtime(fixture("l1_addr_lo_cheat.out"), PC2_OK, PING_OK, PING_OK), lab_001())
    r = results(v)
    assert not v.passed
    assert [x.id for x in v.results if not x.passed] == [UNIQUE_CHECK_ID]
    assert r[UNIQUE_CHECK_ID].message == "10.37.84.94는 pc2:eth1에만 있어야 하는데 pc1:lo에도 있습니다"


@pytest.mark.parametrize("name", ["l1_ping_noreply.out", "l1_ping_arpfail_w.out", "l2_ping_badnh.out"])
def test_ping_without_reply_fails(name):
    v = verify(lab_001_runtime(PC1_OK, PC2_OK, ExecResult(1, fixture(name), ""), PING_OK), lab_001())
    assert results(v)["pc1-to-pc2"].message == "10.37.84.94에서 응답이 없습니다"


def test_one_reply_out_of_three_is_enough():
    one = ok(fixture("l1_ping_ok.out").replace("3 received", "1 received"))
    assert results(verify(lab_001_runtime(PC1_OK, PC2_OK, one, PING_OK), lab_001()))["pc1-to-pc2"].passed


def test_runtime_error_fails_checks_instead_of_raising():
    runtime = lab_001_runtime(PC1_OK, PC2_OK, PING_OK, PING_OK)
    runtime.responses[("pc2", ADDR)] = LabRuntimeError("컨테이너가 없습니다")
    runtime.responses[("pc1", tuple(ping_argv("10.37.84.94")))] = LabRuntimeError("시간 초과")
    r = results(verify(runtime, lab_001()))
    assert r["pc2-address"].message == "명령을 실행하지 못했습니다: 컨테이너가 없습니다"
    assert r["pc1-to-pc2"].message == "명령을 실행하지 못했습니다: 시간 초과"
    assert r[UNIQUE_CHECK_ID].message == "주소를 읽지 못한 노드가 있어 확인하지 못했습니다: pc2"


def test_state_is_collected_per_node_kind():
    runtime = FakeLabRuntime({("r1", tuple(STATE_COMMANDS["router"]["running_config"])): ok(fixture("l2_r1_running_static.out"))})
    state = collect_state(runtime, lab_002())
    assert set(state) == {"pc1", "r1", "r2", "pc2"}
    assert set(state["pc1"]) == {"addresses", "routes"}
    assert set(state["r1"]) == {"addresses", "routes", "running_config"}
    assert "ip route 10.2.2.0/24 172.16.0.2" in state["r1"]["running_config"].stdout
    assert state["pc1"]["routes"].argv == ("ip", "-j", "route", "show")
    assert state["pc1"]["addresses"].exit_code == 1  # 준비하지 않은 응답도 기록은 남는다


def lab_002_runtime(r1_route: str, r2_route: str, pc1_route: ExecResult) -> FakeLabRuntime:
    return FakeLabRuntime({
        ("pc1", ADDR): ok(addr_json({"eth1": ["10.1.1.10/24"]})),
        ("pc2", ADDR): ok(addr_json({"eth1": ["10.2.2.10/24"]})),
        ("r1", ADDR): ok(fixture("l2_r1_addr.out")),
        ("r2", ADDR): ok(addr_json({"eth1": ["10.2.2.1/24"], "eth2": ["172.16.0.2/30"]})),
        ("r1", tuple(ping_argv("10.1.1.10"))): ok(BUSYBOX_PING_OK),
        ("r1", tuple(route_argv("router", "10.2.2.10"))): ok(r1_route),
        ("r2", tuple(route_argv("router", "10.1.1.10"))): ok(r2_route),
        ("pc1", tuple(route_argv("host", "10.2.2.10"))): pc1_route,
    })


def test_lab_002_static_and_kernel_routes_pass():
    runtime = lab_002_runtime(fixture("l2_r1_route_static.out"), fixture("l2_r2_route_kernel.out"),
                              ok(fixture("l2_pc1_route_get_gw.out")))
    v = verify(runtime, lab_002())
    assert v.passed, [(r.id, r.message) for r in v.results]
    r = results(v)
    assert r["r1-to-pc1"].message == "10.1.1.10에서 3번 중 1번 응답했습니다"  # busybox ping 출력
    assert r["r1-route"].message == "10.2.2.0/24 경로(static, next-hop 172.16.0.2)를 씁니다"
    assert r["r2-route"].message == "10.1.1.0/24 경로(kernel, next-hop 172.16.0.1)를 씁니다"
    assert r["pc1-route"].message == "eth1로 10.1.1.1 경유"


def test_default_route_is_a_valid_solution():
    runtime = lab_002_runtime(fixture("l2_r1_route_default.out"), fixture("l2_r2_route_kernel.out"),
                              ok(fixture("l2_pc1_route_get_gw.out")))
    assert results(verify(runtime, lab_002()))["r1-route"].message == "0.0.0.0/0 경로(static, next-hop 172.16.0.2)를 씁니다"


@pytest.mark.parametrize("r1_route, message", [
    (fixture("l2_r1_route_none.out"), "10.2.2.10로 가는 경로가 없습니다 (선택된 경로 없음)"),
    (fixture("l2_r1_route_badnh_onlink_later.out"), "10.2.2.0/24 경로(static)가 커널에 설치되지 않았습니다"),
    (fixture("l2_r1_route_static.out").replace('"static"', '"ospf"'), "10.2.2.0/24 경로의 프로토콜이 ospf입니다 (허용: static, kernel)"),
    (fixture("l2_r1_route_connected.out"), "10.1.1.0/24 경로의 프로토콜이 connected입니다 (허용: static, kernel)"),
    ("% Unknown command", "경로 조회 결과를 읽지 못했습니다"),
])
def test_router_route_failures(r1_route, message):
    runtime = lab_002_runtime(r1_route, fixture("l2_r2_route_kernel.out"), ok(fixture("l2_pc1_route_get_gw.out")))
    r = results(verify(runtime, lab_002()))["r1-route"]
    assert not r.passed and r.message == message


@pytest.mark.parametrize("pc1_route, message", [
    (ExecResult(2, "", fixture("l1_route_get_none.err")), "10.2.2.10로 가는 경로가 없습니다"),
    (ok(fixture("l1_route_get_local.out")), "10.2.2.10가 이 노드 자신의 주소입니다"),
])
def test_host_route_failures(pc1_route, message):
    runtime = lab_002_runtime(fixture("l2_r1_route_static.out"), fixture("l2_r2_route_kernel.out"), pc1_route)
    r = results(verify(runtime, lab_002()))["pc1-route"]
    assert not r.passed and r.message == message


def test_busybox_ping_without_reply_fails():
    runtime = lab_002_runtime(fixture("l2_r1_route_static.out"), fixture("l2_r2_route_kernel.out"),
                              ok(fixture("l2_pc1_route_get_gw.out")))
    runtime.responses[("r1", tuple(ping_argv("10.1.1.10")))] = ExecResult(1, BUSYBOX_PING_LOSS, "")
    assert results(verify(runtime, lab_002()))["r1-to-pc1"].message == "10.1.1.10에서 응답이 없습니다"


def test_real_address_outputs_parse():
    from backend.services.lab_checks import CommandOutput, _ipv4_addresses
    parsed = _ipv4_addresses(CommandOutput((), 0, fixture("l1_addr_lo_cheat.out"), ""))
    assert parsed["lo"] == ["127.0.0.1/8", "10.37.84.94/32"] and parsed["eth1"] == ["10.37.84.65/27"]
    down = _ipv4_addresses(CommandOutput((), 0, fixture("l1_addr_down.out"), ""))
    assert down == {"eth1": ["10.37.84.94/24"]}  # 내려간 인터페이스도 주소는 그대로 보인다
    assert _ipv4_addresses(CommandOutput((), 0, fixture("l2_r1_addr.out"), ""))["eth2"] == ["172.16.0.1/30"]
