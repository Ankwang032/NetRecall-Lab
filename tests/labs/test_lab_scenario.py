import ipaddress
import random
from pathlib import Path

import pytest

from backend.services.lab_scenario import ScenarioError, load_scenario, parse_scenario, render
from integrations.labs.base import Endpoint

ROOT = Path(__file__).resolve().parents[2] / "lab_scenarios"

LAB_002_LIKE = """
id: LAB-900
title: 라우터 두 대
type: build
concepts: [NET-010]
parameters:
  lan1:    {pool: 10.0.0.0/8, prefix: 24}
  lan2:    {pool: 10.0.0.0/8, prefix: 24}
  transit: {pool: 172.16.0.0/12, prefix: 30}
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
goal: PC1({lan1})과 PC2({lan2})가 서로 ping되게 하라.
checks:
  - id: pc1-to-pc2
    description: PC1 → PC2 ping
    ping: {from: pc1, to: pc2:eth1}
  - id: r1-route
    description: R1이 LAN2로 가는 경로
    route: {node: r1, to: pc2:eth1}
  - id: r2-route-ospf-ok
    description: 프로토콜을 직접 정한 경로 검사
    route: {node: r2, to: pc1:eth1, protocol: [static, static, ospf]}
  - id: pc1-route
    description: PC1에 PC2로 가는 경로가 있다
    route: {node: pc1, to: pc2:eth1}
"""


def parse(text: str):
    return parse_scenario(text.encode())


def test_repo_scenarios_all_load():
    dirs = sorted(p for p in ROOT.iterdir() if p.is_dir())
    assert [d.name for d in dirs] == ["LAB-001"]
    for d in dirs:
        load_scenario(d)


def test_lab_001_renders_first_and_last_usable_address():
    scenario = load_scenario(ROOT / "LAB-001")
    lab = render(scenario, 7, random.Random(1))
    net = ipaddress.IPv4Network(lab.networks["net"])
    hosts = list(net.hosts())
    first, last = hosts[0], hosts[-1]

    assert lab.run_name == "nr-7"
    assert net.subnet_of(ipaddress.IPv4Network("10.0.0.0/8")) and 24 <= net.prefixlen <= 30
    assert str(net) in lab.goal and "{net}" not in lab.goal
    assert lab.preset_addresses == ()  # 주소 없이 배포한다
    by_id = {c.id: c for c in lab.checks}
    assert by_id["pc1-address"].target == f"{first}/{net.prefixlen}"
    assert by_id["pc1-address"].interface == "eth1"
    assert by_id["pc2-address"].target == f"{last}/{net.prefixlen}"
    assert (by_id["pc1-to-pc2"].node, by_id["pc1-to-pc2"].target) == ("pc1", str(last))
    assert (by_id["pc2-to-pc1"].node, by_id["pc2-to-pc1"].target) == ("pc2", str(first))
    assert lab.expected_addresses == {str(first): Endpoint("pc1", "eth1"), str(last): Endpoint("pc2", "eth1")}
    assert lab.scenario_hash == scenario.source_hash and len(scenario.source_hash) == 64


def test_lab_001_prefix_varies_across_runs():
    scenario = load_scenario(ROOT / "LAB-001")
    prefixes = {ipaddress.IPv4Network(render(scenario, 1, random.Random(i)).networks["net"]).prefixlen
                for i in range(200)}
    assert prefixes == set(range(24, 31))


def test_networks_do_not_overlap_and_presets_are_filled():
    scenario = parse(LAB_002_LIKE)
    for seed in range(50):
        lab = render(scenario, 1, random.Random(seed))
        nets = [ipaddress.IPv4Network(n) for n in lab.networks.values()]
        assert not any(a.overlaps(b) for i, a in enumerate(nets) for b in nets[i + 1:])
    preset = dict(lab.preset_addresses)
    lan1 = ipaddress.IPv4Network(lab.networks["lan1"])
    assert preset[Endpoint("pc1", "eth1")] == f"{lan1.network_address + 10}/24"
    transit = ipaddress.IPv4Network(lab.networks["transit"])
    assert preset[Endpoint("r2", "eth2")] == f"{transit.network_address + 2}/30"
    assert "{" not in lab.goal and lab.networks["lan2"] in lab.goal


def test_route_protocol_defaults():
    checks = {c.id: c for c in parse(LAB_002_LIKE).checks}
    assert checks["r1-route"].protocols == ("static", "kernel")  # 라우터 기본값
    assert checks["r2-route-ospf-ok"].protocols == ("static", "ospf")  # 중복 제거
    assert checks["pc1-route"].protocols is None  # Linux 노드는 프로토콜을 보지 않는다


def test_networks_that_cannot_fit_fail_at_render():
    text = LAB_002_LIKE.replace("lan2:    {pool: 10.0.0.0/8, prefix: 24}", "lan2:    {pool: 10.0.0.0/8, prefix: 8}")
    with pytest.raises(ScenarioError, match="겹치지 않게"):
        render(parse(text), 1, random.Random(0))


def test_folder_name_must_match_id(tmp_path):
    (tmp_path / "LAB-002").mkdir()
    (tmp_path / "LAB-002" / "scenario.yaml").write_bytes((ROOT / "LAB-001" / "scenario.yaml").read_bytes())
    with pytest.raises(ScenarioError, match="폴더 이름"):
        load_scenario(tmp_path / "LAB-002")


@pytest.mark.parametrize("old, new, message", [
    ("title: 라우터 두 대", "title: 라우터 두 대\nimage: evil", "알 수 없는 키: image"),
    ("id: LAB-900", "id: LAB-9", "id 형식"),
    ("type: build", "type: troubleshoot", "type은 build"),
    ("concepts: [NET-010]", "concepts: []", "concepts"),
    ("concepts: [NET-010]", "concepts: [net-010]", "개념 id 형식"),
    ("type: build", "type: build\ntime_limit_minutes: 0", "time_limit_minutes"),
    ("pc1: {kind: host}", "pc1: {kind: host, binds: [/:/host]}", "알 수 없는 키: binds"),
    ("pc1: {kind: host}", "pc1: {kind: switch}", "kind는 host, router"),
    ("pc1: {kind: host}", "PC1: {kind: host}", "노드 이름"),
    ("  pc2: {kind: host}", "  pc2: {kind: host}\n  a: {kind: host}\n  b: {kind: host}\n  c: {kind: host}",
     "노드는 1~6개"),
    ("[pc1:eth1, r1:eth1]", "[pc1:eth0, r1:eth1]", "eth1부터"),
    ("[pc1:eth1, r1:eth1]", "[pc9:eth1, r1:eth1]", "nodes에 없는 노드입니다: pc9"),
    ("[r2:eth1, pc2:eth1]", "[r2:eth1, pc1:eth1]", "pc1:eth1를 두 번"),
    ("[r2:eth1, pc2:eth1]", "[r2:eth1, r2:eth3]", "같은 노드끼리"),
    ("lan1:    {pool: 10.0.0.0/8, prefix: 24}", "lan1:    {pool: 8.0.0.0/8, prefix: 24}", "사설 대역"),
    ("lan1:    {pool: 10.0.0.0/8, prefix: 24}", "lan1:    {pool: 10.0.0.1/8, prefix: 24}", "IPv4 대역"),
    ("lan1:    {pool: 10.0.0.0/8, prefix: 24}", "lan1:    {pool: 10.0.0.0/8, prefix: 31}", "prefix는"),
    ("lan1:    {pool: 10.0.0.0/8, prefix: 24}", "lan1:    {pool: 10.0.0.0/16, prefix: 12}", "prefix는"),
    ("lan1:    {pool: 10.0.0.0/8, prefix: 24}", "lan1:    {pool: 10.0.0.0/8, prefix: {min: 26, max: 24}}",
     "prefix는"),
    ("pc1:eth1: lan1.host(10)", "pc1:eth1: lan9.host(10)", "parameters에 없는 대역입니다: lan9"),
    ("pc1:eth1: lan1.host(10)", "pc1:eth1: lan1.host(0)", "사용 가능 주소"),
    ("r1:eth2:  transit.host(1)", "r1:eth2:  transit.host(3)", r"/30 대역의 사용 가능 주소\(2개\)"),
    ("pc1:eth1: lan1.host(10)", "pc1:eth1: 10.0.0.1/24", "host\\(n\\)"),
    ("pc1:eth1: lan1.host(10)", "pc1:eth3: lan1.host(10)", "links에 없는 인터페이스"),
    ("r2:eth2:  transit.host(2)", "r2:eth2:  transit.host(-2)", "주소가 같습니다"),
    ("goal: PC1({lan1})", "goal: PC1({lan9})", "goal: parameters에 없는 대역"),
    ("ping: {from: pc1, to: pc2:eth1}", "ping: {from: pc1, to: pc2:eth1}\n    route: {node: r1, to: pc2:eth1}",
     "하나만"),
    ("ping: {from: pc1, to: pc2:eth1}", "ping: {from: pc1, to: 10.0.0.1}", "노드:ethN"),
    ("ping: {from: pc1, to: pc2:eth1}", "ping: {from: pc7, to: pc2:eth1}", "from가 nodes에 없는"),
    ("ping: {from: pc1, to: pc2:eth1}", "ping: {from: pc1, to: pc2:eth1, count: 9}", "알 수 없는 키: count"),
    ("route: {node: pc1, to: pc2:eth1}", "route: {node: pc1, to: pc2:eth1, protocol: [kernel]}",
     "protocol을 쓸 수 없습니다"),
    ("protocol: [static, static, ospf]", "protocol: [statik]", "protocol은"),
    ("- id: r1-route", "- id: pc1-to-pc2", "검사 id가 겹칩니다"),
    ("- id: r1-route", "- id: R1", "검사 id는"),
    ("description: PC1 → PC2 ping", "description: ''", "description가 비어"),
])
def test_invalid_scenarios(old, new, message):
    assert old in LAB_002_LIKE
    with pytest.raises(ScenarioError, match=message):
        parse(LAB_002_LIKE.replace(old, new, 1))


def test_target_needs_an_address():
    text = LAB_002_LIKE.replace("    pc2:eth1: lan2.host(10)\n", "")
    with pytest.raises(ScenarioError, match="pc2:eth1의 주소가 preset이나 address 검사에 없습니다"):
        parse(text)


def test_preset_and_address_check_must_agree():
    text = LAB_002_LIKE + """  - id: pc1-address
    description: PC1 주소
    address: {interface: pc1:eth1, address: lan1.host(11)}
"""
    with pytest.raises(ScenarioError, match="pc1:eth1의 주소가"):
        parse(text)


def test_same_address_check_and_preset_is_fine():
    text = LAB_002_LIKE + """  - id: pc1-address
    description: PC1 주소
    address: {interface: pc1:eth1, address: lan1.host(10)}
"""
    assert parse(text).checks[-1].address.index == 10


def test_distinct_addresses_are_checked_for_every_prefix_in_range():
    # /24~/28에서는 host(5)와 host(-2)가 다르지만 /29에서는 둘 다 .5다
    text = (ROOT / "LAB-001" / "scenario.yaml").read_text()
    text = text.replace("prefix: {min: 24, max: 30}", "prefix: {min: 24, max: 29}")
    text = text.replace("net.host(1)", "net.host(5)").replace("net.host(-1)", "net.host(-2)")
    with pytest.raises(ScenarioError, match="/29일 때"):
        parse(text)


def test_broken_yaml():
    with pytest.raises(ScenarioError, match="YAML"):
        parse("id: [")
    with pytest.raises(ScenarioError, match="매핑"):
        parse("- 1")
