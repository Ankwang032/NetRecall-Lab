import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.api import lab_terminal as terminal_api
from backend.main import create_app
from backend.models.concept import utcnow
from backend.services.lab_terminal import MAX_TERMINALS, Tickets, same_origin
from integrations.labs.base import ExecResult
from tests.fakes import FakeLabRuntime

ORIGIN = {"origin": "http://testserver"}  # TestClient의 Host는 testserver


class ObedientRuntime(FakeLabRuntime):
    """배포 때 preset 명령이 모두 성공한다. 이 파일은 터미널만 본다."""

    def exec(self, run_name, node, argv):
        super().exec(run_name, node, argv)
        return ExecResult(0, "", "")


@pytest.fixture
def runtime():
    return ObedientRuntime()


@pytest.fixture
def client(tmp_path, runtime):
    # 저장소 시나리오: LAB-002에 Linux 노드(pc1)와 라우터(r1)가 있다
    return TestClient(create_app(f"sqlite:///{tmp_path / 'api.db'}", tmp_path / "concepts", lab_runtime=runtime))


def start(client) -> int:
    return client.post("/labs/LAB-002/runs").json()["run_id"]


def ticket(client, run_id, node="r1", **body) -> str:
    res = client.post(f"/lab-runs/{run_id}/terminal-tickets", json={"node": node, **body})
    assert res.status_code == 201, res.text
    return res.json()["ticket"]


def read_until(ws, text: str) -> str:
    out = b""
    while text.encode() not in out:
        out += ws.receive_bytes()
    return out.decode()


def test_terminal_runs_the_node_command_in_a_pty(client, runtime):
    run_id = start(client)
    res = client.post(f"/lab-runs/{run_id}/terminal-tickets", json={"node": "r1"})
    assert {k: res.json()[k] for k in ("node", "shell")} == {"node": "r1", "shell": "vtysh"}  # 라우터 기본은 vtysh

    with client.websocket_connect(f"/lab-runs/{run_id}/terminal?ticket={res.json()['ticket']}", headers=ORIGIN) as ws:
        ws.send_text(json.dumps({"type": "resize", "cols": 120, "rows": 30}))
        ws.send_text(json.dumps({"type": "input", "data": "show ip route\n"}))
        assert "show ip route" in read_until(ws, "show ip route")  # 가짜 런타임은 cat: 입력이 돌아온다
    assert runtime.terminals == [("nr-1", "r1", "vtysh")]


def test_ticket_rules(client, runtime):
    assert client.post("/lab-runs/9/terminal-tickets", json={"node": "r1"}).status_code == 404
    run_id = start(client)
    assert ticket(client, run_id, "r1", shell="sh")  # 라우터는 sh도 된다
    assert client.post(f"/lab-runs/{run_id}/terminal-tickets", json={"node": "r9"}).status_code == 404
    res = client.post(f"/lab-runs/{run_id}/terminal-tickets", json={"node": "pc1", "shell": "vtysh"})
    assert res.status_code == 422 and "sh만" in res.json()["detail"]
    assert client.post(f"/lab-runs/{run_id}/terminal-tickets", json={"node": "pc1", "shell": "bash"}).status_code == 422
    client.post(f"/lab-runs/{run_id}/finish")
    assert client.post(f"/lab-runs/{run_id}/terminal-tickets", json={"node": "r1"}).status_code == 409


def rejected(client, url, headers=ORIGIN) -> int:
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(url, headers=headers):
            pass
    return exc.value.code


def test_websocket_rejections(client, runtime):
    run_id = start(client)
    url = f"/lab-runs/{run_id}/terminal?ticket="
    # 다른 사이트의 스크립트 (Origin이 다르거나 없음)
    assert rejected(client, url + ticket(client, run_id), {"origin": "https://evil.example"}) == 1008
    assert rejected(client, url + ticket(client, run_id), {}) == 1008
    # 발급표 없음, 다른 실행의 발급표, 다시 쓴 발급표
    assert rejected(client, url) == 1008
    assert rejected(client, f"/lab-runs/{run_id + 1}/terminal?ticket=" + ticket(client, run_id)) == 1008
    used = ticket(client, run_id)
    with client.websocket_connect(url + used, headers=ORIGIN):
        pass
    assert rejected(client, url + used) == 1008
    # 시간이 지난 발급표
    client.app.state.terminal_tickets = Tickets(seconds=-1)
    assert rejected(client, url + ticket(client, run_id)) == 1008
    client.app.state.terminal_tickets = Tickets()
    # 터미널이 너무 많음
    client.app.state.terminal_count = MAX_TERMINALS
    assert rejected(client, url + ticket(client, run_id)) == 1013
    client.app.state.terminal_count = 0
    # 발급받은 뒤 실습을 끝냄
    late = ticket(client, run_id)
    client.post(f"/lab-runs/{run_id}/finish")
    assert rejected(client, url + late) == 1008
    assert runtime.terminals == [("nr-1", "r1", "vtysh")]  # 실제로 연 것은 한 번뿐


def test_port_forwarding_origin(client, runtime):
    run_id = start(client)
    headers = {"origin": "https://abc-8000.app.github.dev", "x-forwarded-host": "abc-8000.app.github.dev"}
    with client.websocket_connect(f"/lab-runs/{run_id}/terminal?ticket={ticket(client, run_id)}", headers=headers):
        pass


def test_same_origin():
    assert same_origin({"origin": "http://127.0.0.1:8000", "host": "127.0.0.1:8000"})
    assert not same_origin({"origin": "http://127.0.0.1:5173", "host": "127.0.0.1:8000"})
    assert not same_origin({"origin": "null", "host": "127.0.0.1:8000"})
    assert not same_origin({"host": "127.0.0.1:8000"})


def test_tells_why_it_closed_when_the_shell_ends(client, runtime):
    runtime.terminal_command = ["sh", "-c", "echo bye"]
    run_id = start(client)
    with client.websocket_connect(f"/lab-runs/{run_id}/terminal?ticket={ticket(client, run_id)}", headers=ORIGIN) as ws:
        assert "bye" in read_until(ws, "bye")
        closed = json.loads(ws.receive_text())
    assert closed == {"type": "closed", "message": "터미널이 끝났습니다 (실습을 끝냈거나 셸에서 나왔습니다)"}


def test_bad_message_closes(client, runtime):
    run_id = start(client)
    with client.websocket_connect(f"/lab-runs/{run_id}/terminal?ticket={ticket(client, run_id)}", headers=ORIGIN) as ws:
        ws.send_text("not json")
        assert json.loads(ws.receive_text())["message"] == "알 수 없는 메시지를 받아 닫았습니다"


def test_closes_at_time_limit(client, runtime, monkeypatch):
    run_id = start(client)
    almost = utcnow() + timedelta(minutes=60) - timedelta(seconds=1)  # 시간 제한 60분의 1초 전
    monkeypatch.setattr(terminal_api, "utcnow", lambda: almost)
    with client.websocket_connect(f"/lab-runs/{run_id}/terminal?ticket={ticket(client, run_id)}", headers=ORIGIN) as ws:
        assert json.loads(ws.receive_text())["message"] == "시간 제한이 지나 터미널을 닫았습니다"
