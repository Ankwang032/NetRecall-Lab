"""검증: 노드 상태 수집과 검사.

검사 의미: docs/lab-scenario-format.md "checks: 검사"

- 실행할 명령은 여기에 고정한다. 시나리오 파일과 학습자 입력은 명령이 되지 않고, 렌더링할 때 만든
  주소만 인자로 들어간다. 셸을 거치지 않는다.
- 검사는 최종 상태만 본다. 목표를 만족하면 어떤 방법으로 설정했든 통과다.
- 검사 전에 모든 노드의 상태를 수집해 시도 기록에 남긴다. address 검사와 주소 유일성 검사는 이 상태로 판단한다.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from integrations.labs.base import Endpoint, LabRuntime, LabRuntimeError

from .lab_scenario import RenderedCheck, RenderedLab

PING_COUNT = 3
UNIQUE_CHECK_ID = "auto:unique-addresses"  # 시나리오 검사 id 형식(소문자·숫자·-)과 겹치지 않는다
UNIQUE_DESCRIPTION = "검사가 가리키는 주소가 의도한 인터페이스에만 있다"
UNIQUE_HINTS = (  # 모든 실습에 붙는 검사라 힌트도 코드에 둔다. 특정 주소를 말하지 않는다
    "같은 주소가 두 곳에 있으면 ping이 엉뚱한 곳(보내는 노드 자신 등)에서 응답해 통과한 것처럼 보일 수 있습니다.",
    "결과 문구에 나온 노드에서 `ip addr`로 lo를 포함한 모든 인터페이스의 주소를 보세요.",
    "의도하지 않은 곳에 남은 주소를 `ip addr del <주소/프리픽스> dev <인터페이스>`로 지우세요.",
)
PING_STATS = re.compile(r"(\d+) packets transmitted, (\d+) (?:packets )?received")  # iputils·busybox

# 노드 종류별 상태 수집 명령. 라우터의 학습자가 ip addr로 넣은 주소는 running-config에 나오지 않아 주소도 따로 모은다.
STATE_COMMANDS: dict[str, dict[str, list[str]]] = {
    "host": {
        "addresses": ["ip", "-j", "addr", "show"],
        "routes": ["ip", "-j", "route", "show"],
    },
    "router": {
        "addresses": ["ip", "-j", "addr", "show"],
        "routes": ["vtysh", "-c", "show ip route json"],
        "running_config": ["vtysh", "-c", "show running-config"],
    },
}


def ping_argv(address: str) -> list[str]:
    # 응답 대기 한 번에 1초. iputils(host)와 busybox(router) 모두 받는 옵션만 쓴다
    return ["ping", "-n", "-c", str(PING_COUNT), "-W", "1", address]


def route_argv(kind: str, address: str) -> list[str]:
    if kind == "router":
        return ["vtysh", "-c", f"show ip route {address} json"]
    return ["ip", "-j", "route", "get", address]


@dataclass(frozen=True)
class CommandOutput:
    argv: tuple[str, ...]
    exit_code: int | None  # None: 실행하지 못함 (stderr에 이유)
    stdout: str
    stderr: str


@dataclass(frozen=True)
class CheckResult:
    id: str
    description: str
    kind: str        # ping | route | address | unique
    passed: bool
    message: str     # 통과·실패 이유 한 줄
    output: str      # 판단에 쓴 출력 (ping 결과, 경로, 인터페이스 주소)


@dataclass(frozen=True)
class Verification:
    passed: bool
    state: dict[str, dict[str, CommandOutput]]  # 노드 → 수집 항목 → 출력
    results: tuple[CheckResult, ...]


def collect_state(runtime: LabRuntime, lab: RenderedLab) -> dict[str, dict[str, CommandOutput]]:
    """검증 전, 그리고 포기·시간 초과로 정리하기 전에 부른다. 마지막 설정이 사라지지 않게 남긴다."""
    return {
        node.name: {name: _run(runtime, lab.run_name, node.name, argv)
                    for name, argv in STATE_COMMANDS[node.kind].items()}
        for node in lab.topology.nodes
    }


def verify(runtime: LabRuntime, lab: RenderedLab) -> Verification:
    state = collect_state(runtime, lab)
    addresses = {node: _ipv4_addresses(outputs["addresses"]) for node, outputs in state.items()}
    kinds = {n.name: n.kind for n in lab.topology.nodes}

    results: list[CheckResult] = []
    for check in lab.checks:
        if check.kind == "address":
            results.append(_address(check, addresses[check.node], state[check.node]["addresses"]))
        elif check.kind == "ping":
            results.append(_ping(check, _run(runtime, lab.run_name, check.node, ping_argv(check.target))))
        else:
            out = _run(runtime, lab.run_name, check.node, route_argv(kinds[check.node], check.target))
            results.append(_router_route(check, out) if kinds[check.node] == "router" else _host_route(check, out))
    results.append(_unique(lab.expected_addresses, addresses))
    return Verification(all(r.passed for r in results), state, tuple(results))


# ---- 검사별 판단 ----

def _ping(check: RenderedCheck, out: CommandOutput) -> CheckResult:
    if out.exit_code is None:
        return _result(check, False, f"명령을 실행하지 못했습니다: {out.stderr}", "")
    m = PING_STATS.search(out.stdout)
    received = int(m.group(2)) if m else 0
    text = "\n".join(s for s in (out.stdout.strip(), out.stderr.strip()) if s)
    if received:
        return _result(check, True, f"{check.target}에서 {PING_COUNT}번 중 {received}번 응답했습니다", text)
    return _result(check, False, f"{check.target}에서 응답이 없습니다", text)


def _router_route(check: RenderedCheck, out: CommandOutput) -> CheckResult:
    data = _json(out)
    if not isinstance(data, dict):
        return _result(check, False, _unreadable(out, "경로 조회 결과"), _text(out))
    # 실패하면 출력을 붙이지 않는다. 메시지가 같은 내용을 말하고, 경로 표 전체는 시도 기록의 수집 상태에 남는다
    output = json.dumps(data, ensure_ascii=False, indent=2)
    entries = [(prefix, e) for prefix, routes in data.items() if isinstance(routes, list) for e in routes]
    selected = [(prefix, e) for prefix, e in entries if e.get("selected")]
    if not selected:
        return _result(check, False, f"{check.target}로 가는 경로가 없습니다 (선택된 경로 없음)", "")
    prefix, route = selected[0]
    protocol = route.get("protocol")
    if not route.get("installed"):
        return _result(check, False, f"{prefix} 경로({protocol})가 커널에 설치되지 않았습니다", "")
    if protocol not in (check.protocols or ()):
        allowed = ", ".join(check.protocols or ())
        return _result(check, False, f"{prefix} 경로의 프로토콜이 {protocol}입니다 (허용: {allowed})", "")
    return _result(check, True, f"{prefix} 경로({protocol}, {_nexthops(route)})를 씁니다", output)


def _host_route(check: RenderedCheck, out: CommandOutput) -> CheckResult:
    if out.exit_code is None:
        return _result(check, False, f"명령을 실행하지 못했습니다: {out.stderr}", "")
    if out.exit_code != 0:
        return _result(check, False, f"{check.target}로 가는 경로가 없습니다", "")  # 출력은 RTNETLINK 오류 한 줄
    data = _json(out)
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        return _result(check, False, _unreadable(out, "경로 조회 결과"), _text(out))
    route = data[0]
    if route.get("type") == "local":
        return _result(check, False, f"{check.target}가 이 노드 자신의 주소입니다", "")
    via = f"{route['gateway']} 경유" if route.get("gateway") else "직접 연결"
    return _result(check, True, f"{route.get('dev')}로 {via}", _text(out))


def _address(check: RenderedCheck, addresses: dict[str, list[str]] | None, out: CommandOutput) -> CheckResult:
    if addresses is None:
        return _result(check, False, _unreadable(out, "주소"), _text(out))
    have = addresses.get(check.interface)
    if have is None:
        return _result(check, False, f"{check.interface} 인터페이스가 없습니다", "")
    output = f"{check.interface}: {', '.join(have) or '(IPv4 주소 없음)'}"
    if check.target in have:
        return _result(check, True, f"{check.interface}에 {check.target}가 있습니다", output)
    ip = check.target.split("/")[0]
    same_ip = [a for a in have if a.split("/")[0] == ip]
    if same_ip:  # 주소는 맞으니 프리픽스만 말한다. 출력은 메시지와 같은 내용이라 붙이지 않는다
        have_prefix, want_prefix = same_ip[0].split("/")[1], check.target.split("/")[1]
        return _result(check, False, f"{check.interface}의 {ip}는 프리픽스 길이가 /{have_prefix}입니다 "
                                     f"(대역은 /{want_prefix})", "")
    return _result(check, False, f"{check.interface}에 {check.target}가 없습니다", output)


def _unique(expected: dict[str, Endpoint], addresses: dict[str, dict[str, list[str]] | None]) -> CheckResult:
    """검사가 가리키는 주소가 의도한 인터페이스에만 있는지. 다른 곳에 있으면 ping이 엉뚱한 곳에서 성공할 수 있다."""
    description = UNIQUE_DESCRIPTION
    unreadable = sorted(node for node, a in addresses.items() if a is None)
    if unreadable:
        return CheckResult(UNIQUE_CHECK_ID, description, "unique", False,
                           f"주소를 읽지 못한 노드가 있어 확인하지 못했습니다: {', '.join(unreadable)}", "")
    where: dict[str, list[Endpoint]] = defaultdict(list)
    for node, interfaces in addresses.items():
        for interface, addrs in (interfaces or {}).items():
            for a in addrs:
                where[a.split("/")[0]].append(Endpoint(node, interface))
    problems = []
    for ip, intended in expected.items():
        others = sorted(e for e in where.get(ip, []) if e != intended)
        if others:
            problems.append(f"{ip}는 {intended}에만 있어야 하는데 {', '.join(map(str, others))}에도 있습니다")
    if problems:
        return CheckResult(UNIQUE_CHECK_ID, description, "unique", False, problems[0], "\n".join(problems))
    return CheckResult(UNIQUE_CHECK_ID, description, "unique", True, "다른 곳에 같은 주소가 없습니다", "")


# ---- 도우미 ----

def _run(runtime: LabRuntime, run_name: str, node: str, argv: list[str]) -> CommandOutput:
    try:
        r = runtime.exec(run_name, node, list(argv))
    except LabRuntimeError as exc:
        return CommandOutput(tuple(argv), None, "", str(exc))
    return CommandOutput(tuple(argv), r.exit_code, r.stdout, r.stderr)


def _ipv4_addresses(out: CommandOutput) -> dict[str, list[str]] | None:
    """`ip -j addr show` → 인터페이스 → ["주소/프리픽스"]. 읽지 못하면 None."""
    data = _json(out)
    if not isinstance(data, list):
        return None
    return {
        link["ifname"]: [f"{a['local']}/{a['prefixlen']}" for a in link.get("addr_info", []) if a.get("family") == "inet"]
        for link in data if isinstance(link, dict) and "ifname" in link
    }


def _json(out: CommandOutput) -> Any:
    if out.exit_code != 0:
        return None
    try:
        return json.loads(out.stdout)
    except ValueError:
        return None


def _nexthops(route: dict) -> str:
    hops = [h.get("ip") or h.get("interfaceName") or "?" for h in route.get("nexthops", []) if h.get("active")]
    return "next-hop " + ", ".join(hops) if hops else "next-hop 없음"


def _unreadable(out: CommandOutput, what: str) -> str:
    if out.exit_code is None:
        return f"명령을 실행하지 못했습니다: {out.stderr}"
    return f"{what}를 읽지 못했습니다"


def _text(out: CommandOutput) -> str:
    return "\n".join(s for s in (out.stdout.strip(), out.stderr.strip()) if s)


def _result(check: RenderedCheck, passed: bool, message: str, output: str) -> CheckResult:
    return CheckResult(check.id, check.description, check.kind, passed, message, output)
