import copy
import random
from pathlib import Path

import pytest

from backend.services.lab_scenario import load_scenario, render
from integrations.labs.base import Endpoint, RenderedTopology, TopologyLink, TopologyNode
from integrations.labs.containerlab.topology import IMAGES, TopologyError, check_topology, clab_topology

ROOT = Path(__file__).resolve().parents[2] / "lab_scenarios"


def lab_001_doc():
    lab = render(load_scenario(ROOT / "LAB-001"), 12, random.Random(0))
    return clab_topology(lab.run_name, lab.topology)


def test_lab_001_topology():
    assert lab_001_doc() == {
        "name": "nr-12",
        "topology": {
            "nodes": {
                "pc1": {"kind": "linux", "image": IMAGES["host"], "network-mode": "none", "cpu": 0.5, "memory": "64MB"},
                "pc2": {"kind": "linux", "image": IMAGES["host"], "network-mode": "none", "cpu": 0.5, "memory": "64MB"},
            },
            "links": [{"endpoints": ["pc1:eth1", "pc2:eth1"]}],
        },
    }


def test_router_gets_frr_image_and_its_limits():
    topology = RenderedTopology(
        (TopologyNode("r1", "router"), TopologyNode("pc1", "host")),
        (TopologyLink(Endpoint("r1", "eth1"), Endpoint("pc1", "eth1")),),
    )
    r1 = clab_topology("nr-3", topology)["topology"]["nodes"]["r1"]
    assert r1 == {"kind": "linux", "image": IMAGES["router"], "network-mode": "none", "cpu": 1, "memory": "256MB"}


def tampered(change):
    doc = copy.deepcopy(lab_001_doc())
    change(doc)
    return doc


@pytest.mark.parametrize("change, message", [
    (lambda d: d.update(mgmt={"network": "host"}), "최상위 키"),
    (lambda d: d.update(name="other-lab"), "nr-<실행 id>"),
    (lambda d: d["topology"].update(kinds={}), "topology의 키"),
    (lambda d: d["topology"]["nodes"]["pc1"].update(binds=["/:/host"]), "노드 키"),
    (lambda d: d["topology"]["nodes"]["pc1"].update(exec=["sh -c id"]), "노드 키"),
    (lambda d: d["topology"]["nodes"]["pc1"].pop("network-mode"), "노드 키"),
    (lambda d: d["topology"]["nodes"]["pc1"].update({"network-mode": "host"}), "network-mode는 none"),
    (lambda d: d["topology"]["nodes"]["pc1"].update(kind="nokia_srlinux"), "kind는 linux"),
    (lambda d: d["topology"]["nodes"]["pc1"].update(image="alpine:latest"), "허용하지 않는 이미지"),
    (lambda d: d["topology"]["nodes"]["pc1"].update(memory="8GB"), "자원 제한"),
    (lambda d: d["topology"]["nodes"].update({f"n{i}": d["topology"]["nodes"]["pc1"] for i in range(5)}), "1~6개"),
    (lambda d: d["topology"]["links"].append({"endpoints": ["pc1:eth2", "pc9:eth1"]}), "끝점이 틀렸습니다"),
    (lambda d: d["topology"]["links"].append({"endpoints": ["pc1:eth1", "pc2:eth2"]}), "두 번"),
    (lambda d: d["topology"]["links"].append({"endpoints": ["pc1:eth2", "pc1:eth3"]}), "같은 노드끼리"),
    (lambda d: d["topology"]["links"][0].update(mtu=9000), "endpoints뿐"),
])
def test_static_check_rejects(change, message):
    with pytest.raises(TopologyError, match=message):
        check_topology(tampered(change))
