"""ContainerlabRuntime 단위 테스트. subprocess를 가짜로 바꿔 Docker 없이 명령 인자와 오류 처리를 본다."""
import subprocess
from types import SimpleNamespace

import pytest
import yaml

from integrations.labs.base import Endpoint, ExecResult, LabRuntimeError, RenderedTopology, TopologyLink, TopologyNode
from integrations.labs.containerlab import runtime as rt
from integrations.labs.containerlab.runtime import ContainerlabRuntime
from integrations.labs.containerlab.topology import TopologyError

TOPOLOGY = RenderedTopology(
    (TopologyNode("pc1", "host"), TopologyNode("r1", "router")),
    (TopologyLink(Endpoint("pc1", "eth1"), Endpoint("r1", "eth1")),),
)


class FakeProcesses:
    """argv 앞부분으로 결과를 고른다. 부른 argv를 모두 남긴다."""

    def __init__(self, monkeypatch, rules):
        self.rules = rules  # [(argv 앞부분, (종료 코드, stdout, stderr) 또는 예외)]
        self.calls = []
        monkeypatch.setattr(rt.subprocess, "run", self.run)
        monkeypatch.setattr(rt.time, "sleep", lambda s: None)

    def run(self, argv, **kwargs):
        self.calls.append(list(argv))
        for prefix, result in self.rules:
            if list(argv[:len(prefix)]) == prefix:
                if isinstance(result, Exception):
                    raise result
                code, out, err = result
                return SimpleNamespace(returncode=code, stdout=out, stderr=err)
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def test_exec_runs_argv_in_the_node_container_without_a_shell(monkeypatch):
    fake = FakeProcesses(monkeypatch, [(["docker", "exec"], (1, "3 packets transmitted, 0 received", ""))])
    result = ContainerlabRuntime("/tmp/x").exec("nr-5", "pc1", ["ping", "-c", "3", "10.0.0.1"])
    assert fake.calls == [["docker", "exec", "clab-nr-5-pc1", "ping", "-c", "3", "10.0.0.1"]]
    assert result == ExecResult(1, "3 packets transmitted, 0 received", "")  # 명령의 실패는 그대로 돌려준다


@pytest.mark.parametrize("stderr", [
    "Error response from daemon: No such container: clab-nr-5-pc1",
    'OCI runtime exec failed: exec failed: unable to start container process: exec: "vtysh": executable file not found',
])
def test_docker_failures_raise(monkeypatch, stderr):
    FakeProcesses(monkeypatch, [(["docker", "exec"], (1, "", stderr))])
    with pytest.raises(LabRuntimeError, match="pc1: "):
        ContainerlabRuntime("/tmp/x").exec("nr-5", "pc1", ["true"])


def test_exec_timeout_raises(monkeypatch):
    FakeProcesses(monkeypatch, [(["docker", "exec"], subprocess.TimeoutExpired("docker", 15))])
    with pytest.raises(LabRuntimeError, match="15초 안에 끝나지 않았습니다: sleep 99"):
        ContainerlabRuntime("/tmp/x").exec("nr-5", "pc1", ["sleep", "99"])


@pytest.mark.parametrize("run_name, node", [("lab-5", "pc1"), ("nr-5", "PC1"), ("nr-5", "pc1;id"), ("nr-5 ", "pc1")])
def test_names_are_checked_before_running(monkeypatch, run_name, node):
    fake = FakeProcesses(monkeypatch, [])
    with pytest.raises(LabRuntimeError):
        ContainerlabRuntime("/tmp/x").exec(run_name, node, ["true"])
    assert fake.calls == []


def test_deploy_writes_checked_topology_and_prepares_routers(monkeypatch, tmp_path):
    fake = FakeProcesses(monkeypatch, [
        (["docker", "exec", "clab-nr-5-r1", "vtysh"], (0, '{"0.0.0.0/0":[]}', "")),
    ])
    ContainerlabRuntime(tmp_path).deploy("nr-5", TOPOLOGY)
    path = tmp_path / "nr-5.clab.yml"
    assert yaml.safe_load(path.read_text())["topology"]["nodes"]["r1"]["network-mode"] == "none"
    assert fake.calls == [
        ["containerlab", "deploy", "-t", str(path)],
        ["docker", "exec", "clab-nr-5-r1", "touch", "/etc/frr/vtysh.conf"],
        ["docker", "exec", "clab-nr-5-r1", "vtysh", "-c", "show ip route json"],
    ]


def test_deploy_waits_until_frr_answers(monkeypatch, tmp_path):
    answers = iter([(1, "", "zebra is not running"), (0, "% Can't open", ""), (0, "{}", "")])
    calls = []

    def run(argv, **kwargs):
        calls.append(list(argv))
        if argv[:4] == ["docker", "exec", "clab-nr-5-r1", "vtysh"]:
            code, out, err = next(answers)
            return SimpleNamespace(returncode=code, stdout=out, stderr=err)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(rt.subprocess, "run", run)
    monkeypatch.setattr(rt.time, "sleep", lambda s: None)
    ContainerlabRuntime(tmp_path).deploy("nr-5", TOPOLOGY)
    assert sum(c[3:4] == ["vtysh"] for c in calls) == 3


def test_failed_deploy_cleans_up_and_raises(monkeypatch, tmp_path):
    fake = FakeProcesses(monkeypatch, [
        (["containerlab", "deploy"], (1, "", "INFO 시작\nERRO failed to pull image\n")),
        (["docker", "ps"], (0, "nr-5\nnr-5\nother-lab\n", "")),
    ])
    with pytest.raises(LabRuntimeError, match="배포에 실패했습니다: INFO 시작\nERRO failed to pull image"):
        ContainerlabRuntime(tmp_path).deploy("nr-5", TOPOLOGY)
    assert ["containerlab", "destroy", "--name", "nr-5", "--cleanup"] in fake.calls
    assert not (tmp_path / "nr-5.clab.yml").exists()


def test_static_check_failure_does_not_deploy(monkeypatch, tmp_path):
    fake = FakeProcesses(monkeypatch, [])
    many = RenderedTopology(tuple(TopologyNode(f"n{i}", "host") for i in range(7)), ())
    with pytest.raises(TopologyError):
        ContainerlabRuntime(tmp_path).deploy("nr-5", many)
    assert fake.calls == []


def test_destroy_only_existing_runs(monkeypatch, tmp_path):
    fake = FakeProcesses(monkeypatch, [(["docker", "ps"], (0, "nr-7\n", ""))])
    runtime = ContainerlabRuntime(tmp_path)
    runtime.destroy("nr-5")  # 없는 실습: containerlab을 부르지 않는다
    runtime.destroy("nr-7")
    destroys = [c for c in fake.calls if c[:2] == ["containerlab", "destroy"]]
    assert destroys == [["containerlab", "destroy", "--name", "nr-7", "--cleanup"]]


def test_list_runs_keeps_only_netrecall_labs(monkeypatch):
    fake = FakeProcesses(monkeypatch, [(["docker", "ps"], (0, "nr-3\nnr-3\nmy-lab\nnr-12\nnr-x\n", ""))])
    assert ContainerlabRuntime("/tmp/x").list_runs() == ["nr-12", "nr-3"]
    assert fake.calls == [["docker", "ps", "-a", "--filter", "label=containerlab", "--format", '{{.Label "containerlab"}}']]


def test_missing_binaries_raise(monkeypatch):
    FakeProcesses(monkeypatch, [(["docker"], FileNotFoundError("docker"))])
    with pytest.raises(LabRuntimeError, match="docker를 실행하지 못했습니다"):
        ContainerlabRuntime("/tmp/x").list_runs()
