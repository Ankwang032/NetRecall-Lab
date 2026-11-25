"""실습 시나리오 파일 읽기·검증과 실행마다의 렌더링.

형식 명세: docs/lab-scenario-format.md

- 시나리오 파일에는 정답 설정도 명령도 없다. 여기서 만드는 것은 토폴로지, 배포 때 넣을 주소(preset),
  주소를 채운 검사 목록뿐이다. 명령은 검사 종류마다 코드에 고정한다.
- 검사가 가리키는 인터페이스의 주소는 preset이나 address 검사에서 정한다. 이 표가 주소 유일성 검사의
  "있어야 할 곳"이 된다.
- 주소 대역은 실행마다 무작위로 고른다. 형식 오류는 읽을 때 모두 잡는다. 프리픽스 범위 안의 어떤 길이가
  골라져도 주소가 대역을 넘거나 서로 겹치지 않는지 미리 확인한다.
"""
from __future__ import annotations

import hashlib
import ipaddress
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from integrations.labs.base import MAX_NODES, NODE_KINDS, Endpoint, RenderedTopology, TopologyLink, TopologyNode
from integrations.sources.markdown.adapter import CONCEPT_ID_PATTERN, LAB_ID_PATTERN

SCENARIO_FILE = "scenario.yaml"
NODE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9]{0,14}$")
PARAMETER_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,19}$")
CHECK_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
ENDPOINT_PATTERN = re.compile(r"^([a-z][a-z0-9]*):(eth[1-9][0-9]?)$")  # eth0은 관리망 자리라 쓰지 않는다
HOST_PATTERN = re.compile(r"^([a-z][a-z0-9_]*)\.host\((-?[0-9]+)\)$")
PLACEHOLDER_PATTERN = re.compile(r"\{([^{}]*)\}")

TYPES = ("build",)  # 장애 해결(troubleshoot)은 Phase 6
TIME_LIMIT_DEFAULT, TIME_LIMIT_MAX = 60, 120
MAX_PREFIX = 30  # /31·/32는 "첫 번째·마지막 사용 가능 주소"가 없다
PRIVATE_POOLS = tuple(ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
ROUTE_PROTOCOLS = ("kernel", "connected", "local", "static", "ospf", "bgp", "rip", "isis")
ROUTER_DEFAULT_PROTOCOLS = ("static", "kernel")  # vtysh로 넣으면 static, ip route add로 넣으면 kernel
CHECK_KINDS = ("ping", "route", "address")
MAX_HINTS = 3  # 검사마다 힌트는 1~3단계: 개념 질문 → 확인할 곳 → 할 일
CHOOSE_ATTEMPTS = 100

SCENARIO_KEYS = {
    "id", "title", "type", "concepts", "time_limit_minutes",
    "parameters", "nodes", "links", "preset", "goal", "checks",
}
REQUIRED_KEYS = ("id", "title", "type", "concepts", "nodes", "links", "goal", "checks")


class ScenarioError(ValueError):
    pass


# ---- 읽은 시나리오 ----

@dataclass(frozen=True)
class Parameter:
    name: str
    pool: ipaddress.IPv4Network
    prefix_min: int
    prefix_max: int


@dataclass(frozen=True)
class HostAddress:
    """`<대역>.host(n)`. n이 양수면 앞에서 n번째, 음수면 뒤에서 |n|번째 사용 가능 주소 (-1 = 마지막)."""
    parameter: str
    index: int

    def __str__(self) -> str:
        return f"{self.parameter}.host({self.index})"


@dataclass(frozen=True)
class Check:
    id: str
    description: str
    kind: str                       # ping | route | address
    node: str                       # ping: 보내는 노드, route: 조회할 노드, address: 주소가 있어야 할 노드
    target: Endpoint | None         # ping·route: 목적지 인터페이스
    interface: str | None           # address: 인터페이스
    address: HostAddress | None     # address: 있어야 할 주소
    protocols: tuple[str, ...] | None  # route: 허용하는 프로토콜 (Linux 노드는 None)
    hints: tuple[str, ...] = ()     # 단계별 힌트. {대역}·{대역.prefix}·{노드:인터페이스}(preset 주소)를 쓸 수 있다


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    type: str
    concepts: tuple[str, ...]
    time_limit_minutes: int
    parameters: tuple[Parameter, ...]
    nodes: tuple[TopologyNode, ...]
    links: tuple[TopologyLink, ...]
    preset_addresses: tuple[tuple[Endpoint, HostAddress], ...]
    goal: str
    checks: tuple[Check, ...]
    source_hash: str  # 파일 내용의 sha256. 실행 기록에 남겨 파일이 바뀌어도 그때 실행을 재현한다


# ---- 실행마다 렌더링한 결과 ----

@dataclass(frozen=True)
class RenderedCheck:
    id: str
    description: str
    kind: str
    node: str
    target: str                      # ping·route: 목적지 주소, address: 주소/프리픽스
    interface: str | None = None     # address만
    protocols: tuple[str, ...] | None = None  # route만
    hints: tuple[str, ...] = ()      # 값을 채운 힌트 (힌트가 생기기 전 실행 기록에는 없다)


@dataclass(frozen=True)
class RenderedLab:
    scenario_id: str
    scenario_hash: str
    run_name: str
    networks: dict[str, str]                         # 대역 이름 → 고른 대역 (주소표)
    topology: RenderedTopology
    preset_addresses: tuple[tuple[Endpoint, str], ...]  # 배포 때 넣을 주소/프리픽스
    expected_addresses: dict[str, Endpoint]          # 검사가 가리키는 주소 → 있어야 할 곳 (주소 유일성)
    goal: str
    checks: tuple[RenderedCheck, ...]
    time_limit_minutes: int


# ---- 읽기 ----

def load_scenario(directory: str | Path) -> Scenario:
    """`<directory>/scenario.yaml`을 읽는다. 폴더 이름이 시나리오 id와 같아야 한다."""
    directory = Path(directory)
    raw = (directory / SCENARIO_FILE).read_bytes()
    scenario = parse_scenario(raw)
    if directory.name != scenario.id:
        raise ScenarioError(f"폴더 이름({directory.name})이 시나리오 id({scenario.id})와 다릅니다")
    return scenario


def parse_scenario(raw: bytes) -> Scenario:
    try:
        data = yaml.safe_load(raw.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise ScenarioError(f"YAML을 읽지 못했습니다: {exc}") from None
    meta = _mapping(data, "시나리오")
    _keys(meta, SCENARIO_KEYS, "시나리오")
    for key in REQUIRED_KEYS:
        if key not in meta:
            raise ScenarioError(f"'{key}'가 없습니다")

    scenario_id = meta["id"]
    if not isinstance(scenario_id, str) or not LAB_ID_PATTERN.match(scenario_id):
        raise ScenarioError("id 형식이 틀렸습니다 (예: LAB-001)")
    title = _text(meta["title"], "title")
    if meta["type"] not in TYPES:
        raise ScenarioError(f"type은 {', '.join(TYPES)} 중 하나여야 합니다")
    concepts = _concepts(meta["concepts"])
    time_limit = meta.get("time_limit_minutes", TIME_LIMIT_DEFAULT)
    if not _is_int(time_limit) or not 1 <= time_limit <= TIME_LIMIT_MAX:
        raise ScenarioError(f"time_limit_minutes는 1~{TIME_LIMIT_MAX} 정수여야 합니다")

    parameters = _parameters(meta.get("parameters", {}))
    by_name = {p.name: p for p in parameters}
    nodes = _nodes(meta["nodes"])
    kinds = {n.name: n.kind for n in nodes}
    links = _links(meta["links"], kinds)
    interfaces = {e for link in links for e in (link.a, link.b)}

    def host_address(value: Any, where: str) -> HostAddress:
        m = HOST_PATTERN.match(value) if isinstance(value, str) else None
        if not m:
            raise ScenarioError(f"{where}: 주소는 '<대역>.host(n)' 형식이어야 합니다 (예: lan1.host(1))")
        ref = HostAddress(m.group(1), int(m.group(2)))
        parameter = by_name.get(ref.parameter)
        if parameter is None:
            raise ScenarioError(f"{where}: parameters에 없는 대역입니다: {ref.parameter}")
        usable = 2 ** (32 - parameter.prefix_max) - 2  # 가장 작은 대역 기준
        if ref.index == 0 or abs(ref.index) > usable:
            raise ScenarioError(
                f"{where}: {ref}는 /{parameter.prefix_max} 대역의 사용 가능 주소({usable}개)를 벗어납니다"
            )
        return ref

    def interface(value: Any, where: str) -> Endpoint:
        endpoint = _endpoint(value, where)
        if endpoint not in interfaces:
            raise ScenarioError(f"{where}: links에 없는 인터페이스입니다: {endpoint}")
        return endpoint

    preset = _mapping(meta.get("preset", {}), "preset")
    _keys(preset, {"addresses"}, "preset")
    preset_addresses = tuple(
        (interface(k, "preset.addresses"), host_address(v, f"preset.addresses.{k}"))
        for k, v in _mapping(preset.get("addresses", {}), "preset.addresses").items()
    )

    checks = _checks(meta["checks"], kinds, host_address, interface)

    # 인터페이스마다 주소 하나. preset과 address 검사가 같은 인터페이스에 다른 주소를 정하면 오류다.
    addresses: dict[Endpoint, HostAddress] = {}
    for where, endpoint, ref in [("preset", e, r) for e, r in preset_addresses] + [
        (f"검사 {c.id}", Endpoint(c.node, c.interface), c.address) for c in checks if c.kind == "address"
    ]:
        if addresses.setdefault(endpoint, ref) != ref:
            raise ScenarioError(f"{where}: {endpoint}의 주소가 {addresses[endpoint]}와 {ref}로 다릅니다")
    for c in checks:
        if c.target is not None and c.target not in addresses:
            raise ScenarioError(f"검사 {c.id}: {c.target}의 주소가 preset이나 address 검사에 없습니다")
    _check_distinct(addresses, by_name)

    goal = _text(meta["goal"], "goal").strip()
    for name in PLACEHOLDER_PATTERN.findall(goal):
        if name not in by_name:
            raise ScenarioError(f"goal: parameters에 없는 대역입니다: {{{name}}}")
    given = {e for e, _ in preset_addresses}
    for c in checks:
        for hint in c.hints:
            for name in PLACEHOLDER_PATTERN.findall(hint):
                _hint_value(name, by_name, given, f"검사 {c.id}의 힌트")

    return Scenario(
        id=scenario_id, title=title.strip(), type=meta["type"], concepts=concepts,
        time_limit_minutes=time_limit, parameters=parameters, nodes=nodes, links=links,
        preset_addresses=preset_addresses, goal=goal, checks=checks,
        source_hash=hashlib.sha256(raw).hexdigest(),
    )


def _parameters(value: Any) -> tuple[Parameter, ...]:
    result = []
    for name, spec in _mapping(value, "parameters").items():
        where = f"parameters.{name}"
        if not isinstance(name, str) or not PARAMETER_NAME_PATTERN.match(name):
            raise ScenarioError(f"{where}: 대역 이름은 소문자로 시작하는 영문·숫자·_여야 합니다")
        spec = _mapping(spec, where)
        _keys(spec, {"pool", "prefix"}, where)
        try:
            pool = ipaddress.IPv4Network(spec.get("pool"))
        except (ValueError, TypeError):
            raise ScenarioError(f"{where}: pool은 IPv4 대역이어야 합니다 (예: 10.0.0.0/8)") from None
        if not any(pool.subnet_of(p) for p in PRIVATE_POOLS):
            raise ScenarioError(f"{where}: pool은 사설 대역(10/8, 172.16/12, 192.168/16) 안이어야 합니다")
        prefix = spec.get("prefix")
        if isinstance(prefix, dict):
            _keys(prefix, {"min", "max"}, f"{where}.prefix")
            low, high = prefix.get("min"), prefix.get("max")
        else:
            low = high = prefix
        if not (_is_int(low) and _is_int(high) and pool.prefixlen <= low <= high <= MAX_PREFIX):
            raise ScenarioError(
                f"{where}: prefix는 /{pool.prefixlen}~/{MAX_PREFIX} 정수이거나 {{min, max}}여야 합니다"
            )
        result.append(Parameter(name, pool, low, high))
    return tuple(result)


def _nodes(value: Any) -> tuple[TopologyNode, ...]:
    nodes = []
    for name, spec in _mapping(value, "nodes").items():
        if not isinstance(name, str) or not NODE_NAME_PATTERN.match(name):
            raise ScenarioError(f"nodes: 노드 이름은 소문자로 시작하는 영문·숫자 15자 이하여야 합니다: {name}")
        spec = _mapping(spec, f"nodes.{name}")
        _keys(spec, {"kind"}, f"nodes.{name}")  # 이미지·마운트 같은 것은 시나리오에서 정하지 않는다
        if spec.get("kind") not in NODE_KINDS:
            raise ScenarioError(f"nodes.{name}: kind는 {', '.join(NODE_KINDS)} 중 하나여야 합니다")
        nodes.append(TopologyNode(name, spec["kind"]))
    if not 1 <= len(nodes) <= MAX_NODES:
        raise ScenarioError(f"노드는 1~{MAX_NODES}개여야 합니다")
    return tuple(nodes)


def _links(value: Any, kinds: dict[str, str]) -> tuple[TopologyLink, ...]:
    if not isinstance(value, list):
        raise ScenarioError("links는 목록이어야 합니다")
    used: set[Endpoint] = set()
    links = []
    for item in value:
        if not isinstance(item, list) or len(item) != 2:
            raise ScenarioError("links의 항목은 [노드:인터페이스, 노드:인터페이스]여야 합니다")
        a, b = (_endpoint(e, "links") for e in item)
        for e in (a, b):
            if e.node not in kinds:
                raise ScenarioError(f"links: nodes에 없는 노드입니다: {e.node}")
            if e in used:
                raise ScenarioError(f"links: {e}를 두 번 썼습니다")
            used.add(e)
        if a.node == b.node:
            raise ScenarioError(f"links: 같은 노드끼리 연결할 수 없습니다: {a}, {b}")
        links.append(TopologyLink(a, b))
    return tuple(links)


def _checks(value: Any, kinds: dict[str, str], host_address, interface) -> tuple[Check, ...]:
    if not isinstance(value, list) or not value:
        raise ScenarioError("checks는 비어 있지 않은 목록이어야 합니다")
    checks: list[Check] = []
    for item in value:
        item = _mapping(item, "checks의 항목")
        check_id = item.get("id")
        if not isinstance(check_id, str) or not CHECK_ID_PATTERN.match(check_id):
            raise ScenarioError(f"검사 id는 소문자·숫자·-여야 합니다: {check_id}")
        if any(c.id == check_id for c in checks):
            raise ScenarioError(f"검사 id가 겹칩니다: {check_id}")
        where = f"검사 {check_id}"
        present = [k for k in CHECK_KINDS if k in item]
        if len(present) != 1:
            raise ScenarioError(f"{where}: {', '.join(CHECK_KINDS)} 중 하나만 써야 합니다")
        kind = present[0]
        _keys(item, {"id", "description", kind, "hints"}, where)
        description = _text(item.get("description"), f"{where}의 description").strip()
        hints = _hints(item.get("hints", []), where)
        spec = _mapping(item[kind], f"{where}.{kind}")

        def node(key: str) -> str:
            name = spec.get(key)
            if name not in kinds:
                raise ScenarioError(f"{where}: {key}가 nodes에 없는 노드입니다: {name}")
            return name

        if kind == "ping":
            _keys(spec, {"from", "to"}, where)
            check = Check(check_id, description, kind, node("from"), interface(spec.get("to"), where),
                          None, None, None, hints)
        elif kind == "route":
            _keys(spec, {"node", "to", "protocol"}, where)
            at = node("node")
            protocols = spec.get("protocol")
            if kinds[at] == "host":
                if protocols is not None:  # ip route get은 프로토콜을 돌려주지 않는다
                    raise ScenarioError(f"{where}: Linux 노드(host)의 경로 검사에는 protocol을 쓸 수 없습니다")
            elif protocols is None:
                protocols = ROUTER_DEFAULT_PROTOCOLS
            else:
                if not isinstance(protocols, list) or not protocols or any(p not in ROUTE_PROTOCOLS for p in protocols):
                    raise ScenarioError(f"{where}: protocol은 {', '.join(ROUTE_PROTOCOLS)} 중에서 고른 목록이어야 합니다")
                protocols = tuple(dict.fromkeys(protocols))
            check = Check(check_id, description, kind, at, interface(spec.get("to"), where), None, None, protocols,
                          hints)
        else:
            _keys(spec, {"interface", "address"}, where)
            endpoint = interface(spec.get("interface"), where)
            check = Check(check_id, description, kind, endpoint.node, None, endpoint.interface,
                          host_address(spec.get("address"), where), None, hints)
        checks.append(check)
    return tuple(checks)


def _check_distinct(addresses: dict[Endpoint, HostAddress], parameters: dict[str, Parameter]) -> None:
    """프리픽스 범위 안의 어떤 길이가 골라져도 서로 다른 인터페이스의 주소가 겹치지 않아야 한다."""
    by_parameter: dict[str, list[tuple[Endpoint, HostAddress]]] = {}
    for endpoint, ref in addresses.items():
        by_parameter.setdefault(ref.parameter, []).append((endpoint, ref))
    for name, refs in by_parameter.items():
        parameter = parameters[name]
        for prefix in range(parameter.prefix_min, parameter.prefix_max + 1):
            seen: dict[int, Endpoint] = {}
            for endpoint, ref in refs:
                offset = _offset(ref.index, prefix)
                if offset in seen:
                    raise ScenarioError(f"/{prefix}일 때 {seen[offset]}와 {endpoint}의 주소가 같습니다")
                seen[offset] = endpoint


# ---- 렌더링 ----

def render(scenario: Scenario, run_id: int, rng: random.Random | None = None) -> RenderedLab:
    """실행 하나의 대역을 고르고 주소를 채운다. 고른 결과는 실행 기록에 그대로 남긴다."""
    rng = rng or random.SystemRandom()
    networks = _choose_networks(scenario.parameters, rng)

    def address(ref: HostAddress) -> ipaddress.IPv4Address:
        net = networks[ref.parameter]
        return net.network_address + _offset(ref.index, net.prefixlen)

    def with_prefix(ref: HostAddress) -> str:
        return f"{address(ref)}/{networks[ref.parameter].prefixlen}"

    by_endpoint: dict[Endpoint, HostAddress] = dict(scenario.preset_addresses)
    by_endpoint.update({Endpoint(c.node, c.interface): c.address for c in scenario.checks if c.kind == "address"})

    preset = dict(scenario.preset_addresses)

    def hint_text(text: str) -> str:
        def value(m: re.Match) -> str:
            name = m.group(1)
            if name in networks:
                return str(networks[name])
            if name.endswith(".prefix"):
                return str(networks[name.removesuffix(".prefix")].prefixlen)
            return str(address(preset[_endpoint(name, "힌트")]))
        return PLACEHOLDER_PATTERN.sub(value, text)

    checks: list[RenderedCheck] = []
    expected: dict[str, Endpoint] = {}
    for c in scenario.checks:
        hints = tuple(hint_text(h) for h in c.hints)
        if c.kind == "address":
            endpoint = Endpoint(c.node, c.interface)
            checks.append(RenderedCheck(c.id, c.description, c.kind, c.node, with_prefix(c.address), c.interface,
                                        hints=hints))
        else:
            endpoint = c.target
            checks.append(RenderedCheck(c.id, c.description, c.kind, c.node, str(address(by_endpoint[endpoint])),
                                        protocols=c.protocols, hints=hints))
        expected[str(address(by_endpoint[endpoint]))] = endpoint

    goal = PLACEHOLDER_PATTERN.sub(lambda m: str(networks[m.group(1)]), scenario.goal)
    return RenderedLab(
        scenario_id=scenario.id,
        scenario_hash=scenario.source_hash,
        run_name=f"nr-{run_id}",
        networks={name: str(net) for name, net in networks.items()},
        topology=RenderedTopology(scenario.nodes, scenario.links),
        preset_addresses=tuple((e, with_prefix(r)) for e, r in scenario.preset_addresses),
        expected_addresses=expected,
        goal=goal,
        checks=tuple(checks),
        time_limit_minutes=scenario.time_limit_minutes,
    )


def _choose_networks(parameters: tuple[Parameter, ...], rng: random.Random) -> dict[str, ipaddress.IPv4Network]:
    chosen: dict[str, ipaddress.IPv4Network] = {}
    for p in parameters:
        for _ in range(CHOOSE_ATTEMPTS):
            prefix = rng.randint(p.prefix_min, p.prefix_max)
            index = rng.randrange(2 ** (prefix - p.pool.prefixlen))
            net = ipaddress.IPv4Network((int(p.pool.network_address) + index * 2 ** (32 - prefix), prefix))
            if not any(net.overlaps(other) for other in chosen.values()):
                chosen[p.name] = net
                break
        else:
            raise ScenarioError(f"대역 '{p.name}'을 다른 대역과 겹치지 않게 고르지 못했습니다. pool을 넓히세요")
    return chosen


def _offset(index: int, prefix: int) -> int:
    """대역의 네트워크 주소에서 몇 번째 주소인지. -1은 브로드캐스트 바로 앞(마지막 사용 가능 주소)."""
    return index if index > 0 else 2 ** (32 - prefix) - 1 + index


# ---- 작은 도우미 ----

def _mapping(value: Any, where: str) -> dict:
    if not isinstance(value, dict):
        raise ScenarioError(f"{where}는 매핑이어야 합니다")
    return value


def _keys(value: dict, allowed: set[str], where: str) -> None:
    unknown = set(map(str, value)) - allowed
    if unknown:  # 오타 난 키가 조용히 무시되지 않게 한다
        raise ScenarioError(f"{where}: 알 수 없는 키: {', '.join(sorted(unknown))}")


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScenarioError(f"{where}가 비어 있습니다")
    return value


def _hints(value: Any, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > MAX_HINTS:
        raise ScenarioError(f"{where}: hints는 글 {MAX_HINTS}개 이하의 목록이어야 합니다")
    for h in value:
        if not isinstance(h, str):  # YAML은 따옴표 없는 `- {lan1} ...`을 글이 아니라 사전으로 읽는다
            raise ScenarioError(f"{where}: 힌트는 글이어야 합니다. {{로 시작하는 힌트는 따옴표로 감싸세요")
    return tuple(_text(h, f"{where}의 힌트").strip() for h in value)


def _hint_value(name: str, parameters: dict[str, Parameter], given: set[Endpoint], where: str) -> None:
    """힌트에는 학습자가 이미 받은 값만 쓴다: 대역, 대역의 프리픽스 길이, preset으로 넣은 인터페이스 주소.

    address 검사가 정하는 목표 주소(LAB-001의 첫·마지막 주소처럼 학습자가 계산할 값)는 쓸 수 없다.
    """
    if name in parameters or (name.endswith(".prefix") and name.removesuffix(".prefix") in parameters):
        return
    m = ENDPOINT_PATTERN.match(name)
    if m is None:
        raise ScenarioError(f"{where}: 모르는 자리표시입니다: {{{name}}} ({{대역}}, {{대역.prefix}}, {{노드:인터페이스}}만)")
    if Endpoint(m.group(1), m.group(2)) not in given:
        raise ScenarioError(f"{where}: {{{name}}}는 preset으로 넣은 주소가 아니라 쓸 수 없습니다 (정답이 새지 않게)")


def _concepts(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ScenarioError("concepts는 비어 있지 않은 개념 id 목록이어야 합니다")
    for concept_id in value:
        if not isinstance(concept_id, str) or not CONCEPT_ID_PATTERN.match(concept_id):
            raise ScenarioError(f"개념 id 형식이 틀렸습니다: {concept_id} (예: NET-005)")
    return tuple(dict.fromkeys(value))


def _endpoint(value: Any, where: str) -> Endpoint:
    m = ENDPOINT_PATTERN.match(value) if isinstance(value, str) else None
    if not m:
        raise ScenarioError(f"{where}: 인터페이스는 '노드:ethN' 형식이어야 합니다 (eth1부터): {value}")
    return Endpoint(m.group(1), m.group(2))


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
