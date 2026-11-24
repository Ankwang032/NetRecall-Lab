"""배포 때 넣는 설정(preset). 시스템이 노드에 설정을 넣는 길은 이것뿐이다.

항목 종류마다 실행할 명령을 여기에 고정한다. 시나리오 파일의 값은 렌더링할 때 만든 주소·인터페이스 이름으로만
인자에 들어간다. 지금 항목 종류는 addresses(인터페이스 주소)뿐이다.
"""
from __future__ import annotations

from integrations.labs.base import LabRuntime, LabRuntimeError

from .lab_scenario import RenderedLab


def address_argv(kind: str, interface: str, address: str) -> list[str]:
    if kind == "router":  # vtysh로 넣어야 학습자가 보는 running-config에 나온다
        return ["vtysh", "-c", "configure terminal", "-c", f"interface {interface}", "-c", f"ip address {address}"]
    return ["ip", "addr", "add", address, "dev", interface]


def apply_preset(runtime: LabRuntime, lab: RenderedLab) -> None:
    kinds = {n.name: n.kind for n in lab.topology.nodes}
    for endpoint, address in lab.preset_addresses:
        r = runtime.exec(lab.run_name, endpoint.node, address_argv(kinds[endpoint.node], endpoint.interface, address))
        if r.exit_code != 0:
            raise LabRuntimeError(f"{endpoint}에 {address}를 넣지 못했습니다: {(r.stderr or r.stdout).strip()}")
