"""렌더링한 토폴로지를 Containerlab 토폴로지 파일 내용으로 바꾸고, 배포 전에 정적 검사한다 (설계서 §D-4, §D-8).

- 노드 종류(host·router)의 이미지와 자원 제한은 여기 한 곳에서 정한다. 시나리오 파일은 고르지 않는다.
- 모든 노드는 관리망 없이 띄운다(network-mode: none). 노드는 실습 링크로만 통신한다.
- 정적 검사는 노드 항목의 키를 허용 목록으로 본다. 호스트 경로 마운트(binds), 실행 명령(exec) 같은 키가
  들어갈 자리가 없다.
"""
from __future__ import annotations

import re
from typing import Any

from ..base import MAX_NODES, RenderedTopology

IMAGES = {
    "host": "netrecall/lab-host:1",  # integrations/labs/images/host/Dockerfile
    "router": "quay.io/frrouting/frr:10.7.1",
}
LIMITS = {
    "host": {"cpu": 0.5, "memory": "64MB"},
    "router": {"cpu": 1, "memory": "256MB"},
}
RUN_NAME_PATTERN = re.compile(r"^nr-[0-9]+$")  # 정리할 때 이 접두사만 지운다
ENDPOINT_PATTERN = re.compile(r"^([a-z][a-z0-9]*):(eth[1-9][0-9]?)$")
NODE_KEYS = {"kind", "image", "network-mode", "cpu", "memory"}


class TopologyError(ValueError):
    pass


def clab_topology(run_name: str, topology: RenderedTopology) -> dict[str, Any]:
    nodes = {
        n.name: {"kind": "linux", "image": IMAGES[n.kind], "network-mode": "none", **LIMITS[n.kind]}
        for n in topology.nodes
    }
    links = [{"endpoints": [str(link.a), str(link.b)]} for link in topology.links]
    doc = {"name": run_name, "topology": {"nodes": nodes, "links": links}}
    check_topology(doc)
    return doc


def check_topology(doc: Any) -> None:
    """배포 직전의 토폴로지 파일 내용을 검사한다. 통과하지 못하면 배포하지 않는다."""
    if not isinstance(doc, dict) or set(doc) != {"name", "topology"}:
        raise TopologyError("최상위 키는 name, topology뿐이어야 합니다")
    if not isinstance(doc["name"], str) or not RUN_NAME_PATTERN.match(doc["name"]):
        raise TopologyError(f"실습 이름은 nr-<실행 id>여야 합니다: {doc['name']}")
    topology = doc["topology"]
    if not isinstance(topology, dict) or set(topology) != {"nodes", "links"}:
        raise TopologyError("topology의 키는 nodes, links뿐이어야 합니다")

    nodes = topology["nodes"]
    if not isinstance(nodes, dict) or not 1 <= len(nodes) <= MAX_NODES:
        raise TopologyError(f"노드는 1~{MAX_NODES}개여야 합니다")
    kind_of_image = {image: kind for kind, image in IMAGES.items()}
    for name, node in nodes.items():
        if not isinstance(node, dict) or set(node) != NODE_KEYS:
            raise TopologyError(f"{name}: 노드 키는 {', '.join(sorted(NODE_KEYS))}뿐이어야 합니다")
        if node["kind"] != "linux":
            raise TopologyError(f"{name}: kind는 linux여야 합니다")
        kind = kind_of_image.get(node["image"])
        if kind is None:
            raise TopologyError(f"{name}: 허용하지 않는 이미지입니다: {node['image']}")
        if node["network-mode"] != "none":
            raise TopologyError(f"{name}: network-mode는 none이어야 합니다")
        if (node["cpu"], node["memory"]) != (LIMITS[kind]["cpu"], LIMITS[kind]["memory"]):
            raise TopologyError(f"{name}: 자원 제한이 {kind} 노드의 값과 다릅니다")

    links = topology["links"]
    if not isinstance(links, list):
        raise TopologyError("links는 목록이어야 합니다")
    used: set[str] = set()
    for link in links:
        if not isinstance(link, dict) or set(link) != {"endpoints"}:
            raise TopologyError("링크 키는 endpoints뿐이어야 합니다")
        endpoints = link["endpoints"]
        if not isinstance(endpoints, list) or len(endpoints) != 2:
            raise TopologyError("링크는 끝점 두 개여야 합니다")
        names = []
        for endpoint in endpoints:
            m = ENDPOINT_PATTERN.match(endpoint) if isinstance(endpoint, str) else None
            if not m or m.group(1) not in nodes:
                raise TopologyError(f"링크 끝점이 틀렸습니다: {endpoint}")
            if endpoint in used:
                raise TopologyError(f"링크 끝점을 두 번 썼습니다: {endpoint}")
            used.add(endpoint)
            names.append(m.group(1))
        if names[0] == names[1]:
            raise TopologyError(f"같은 노드끼리 연결할 수 없습니다: {endpoints}")
