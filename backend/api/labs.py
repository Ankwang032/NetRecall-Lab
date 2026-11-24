"""실습 API.

흐름: GET /labs → POST /labs/{id}/runs (배포, 목표·주소표·접속 명령) → 학습자가 자기 터미널에서 docker exec로 설정
     → POST /lab-runs/{id}/attempts (검증, 반복) → POST /lab-runs/{id}/finish (정리)
동시에 진행하는 실습은 하나다. 시간 제한은 실습 API를 부를 때 확인한다.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.deps import get_lab_runtime, get_session
from backend.core.time import to_kst
from backend.models import LabAttempt, LabRun
from backend.models.concept import utcnow
from backend.services import lab_service as labs
from integrations.labs.base import LabRuntime

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]
RuntimeDep = Annotated[LabRuntime, Depends(get_lab_runtime)]
UNIQUE_DESCRIPTION = "검사가 가리키는 주소가 의도한 인터페이스에만 있다"


class ScenarioInfo(BaseModel):
    id: str
    title: str
    type: str
    concepts: list[str]
    time_limit_minutes: int


class ScenarioErrorInfo(BaseModel):
    scenario: str  # 폴더 이름
    message: str


class ScenarioListResponse(BaseModel):
    scenarios: list[ScenarioInfo]
    errors: list[ScenarioErrorInfo]


class StartRequest(BaseModel):
    evaluation_id: int | None = None  # 이 실습을 추천한 답안 평가


class NodeInfo(BaseModel):
    name: str
    kind: str
    connect: str  # 학습자가 자기 터미널에서 칠 접속 명령


class AddressInfo(BaseModel):
    interface: str
    address: str


class CheckInfo(BaseModel):
    id: str
    description: str


class RunResponse(BaseModel):
    run_id: int
    scenario_id: str
    title: str
    status: str
    goal: str
    networks: dict[str, str]    # 대역 이름 → 이번 실행의 대역
    addresses: list[AddressInfo]  # 배포할 때 넣은 주소
    nodes: list[NodeInfo]
    checks: list[CheckInfo]
    attempts: int
    started_at: datetime
    expires_at: datetime
    passed_at: datetime | None
    finished_at: datetime | None
    error: str | None


class ResultInfo(BaseModel):
    check_id: str
    description: str
    kind: str
    passed: bool
    message: str
    output: str


class AttemptResponse(BaseModel):
    attempt_id: int
    run_id: int
    run_status: str
    passed: bool
    attempted_at: datetime
    results: list[ResultInfo]


@router.get("/labs")
def list_labs(request: Request) -> ScenarioListResponse:
    scenarios, errors = labs.load_scenarios(_scenarios_dir(request))
    return ScenarioListResponse(
        scenarios=[ScenarioInfo(id=s.id, title=s.title, type=s.type, concepts=list(s.concepts),
                                time_limit_minutes=s.time_limit_minutes) for s in scenarios],
        errors=[ScenarioErrorInfo(scenario=name, message=message) for name, message in errors],
    )


@router.post("/labs/{scenario_id}/runs", status_code=201)
def start(scenario_id: str, request: Request, session: SessionDep, runtime: RuntimeDep,
          body: Annotated[StartRequest | None, Body()] = None) -> RunResponse:
    now = utcnow()
    labs.expire_overdue(session, runtime, now)
    try:
        scenario = labs.find_scenario(_scenarios_dir(request), scenario_id)
        run = labs.start_run(session, runtime, scenario, now, evaluation_id=body.evaluation_id if body else None)
    except (labs.ScenarioNotFound, labs.EvaluationNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except labs.RunInProgress as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except labs.DeployFailed as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return run_response(session, run, _scenarios_dir(request))


@router.get("/lab-runs/current")
def current(request: Request, session: SessionDep, runtime: RuntimeDep) -> RunResponse | None:
    labs.expire_overdue(session, runtime, utcnow())
    run = labs.current_run(session)
    return run_response(session, run, _scenarios_dir(request)) if run else None


@router.get("/lab-runs/{run_id}")
def get(run_id: int, request: Request, session: SessionDep, runtime: RuntimeDep) -> RunResponse:
    labs.expire_overdue(session, runtime, utcnow())
    return run_response(session, _run(session, run_id), _scenarios_dir(request))


@router.post("/lab-runs/{run_id}/attempts", status_code=201)
def attempt(run_id: int, session: SessionDep, runtime: RuntimeDep) -> AttemptResponse:
    try:
        result = labs.verify_run(session, runtime, run_id, utcnow())
    except labs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except labs.RunNotActive as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return attempt_response(session, result, _run(session, run_id))


@router.post("/lab-runs/{run_id}/finish")
def finish(run_id: int, request: Request, session: SessionDep, runtime: RuntimeDep) -> RunResponse:
    try:
        run = labs.finish_run(session, runtime, run_id, utcnow())
    except labs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return run_response(session, run, _scenarios_dir(request))


# ---- 응답 (CLI도 쓴다) ----

def run_response(session: Session, run: LabRun, scenarios_dir: Path) -> RunResponse:
    lab = labs.rendered_lab(run)
    attempts = [a for a in labs.attempts_of(session, run.id) if a.kind == "verify"]
    passed_at = next((a.attempted_at for a in attempts if a.passed), None)
    scenario = next((s for s in labs.load_scenarios(scenarios_dir)[0] if s.id == run.scenario_id), None)
    return RunResponse(
        run_id=run.id, scenario_id=run.scenario_id, title=scenario.title if scenario else run.scenario_id,
        status=run.status, goal=run.goal, networks=lab.networks,
        addresses=[AddressInfo(interface=str(e), address=a) for e, a in lab.preset_addresses],
        nodes=[NodeInfo(name=n.name, kind=n.kind, connect=_connect(lab.run_name, n.name, n.kind))
               for n in lab.topology.nodes],
        checks=[CheckInfo(id=c.id, description=c.description) for c in lab.checks],
        attempts=len(attempts),
        started_at=to_kst(run.started_at), expires_at=to_kst(run.expires_at),
        passed_at=to_kst(passed_at) if passed_at else None,
        finished_at=to_kst(run.finished_at) if run.finished_at else None,
        error=run.error,
    )


def attempt_response(session: Session, attempt: LabAttempt, run: LabRun) -> AttemptResponse:
    lab = labs.rendered_lab(run)
    hidden = labs.hidden_addresses(lab)
    checks = {c.id: c for c in lab.checks}
    results = []
    for r in labs.results_of(session, attempt.id):
        check = checks.get(r.check_id)
        results.append(ResultInfo(
            check_id=r.check_id, passed=r.passed,
            description=check.description if check else UNIQUE_DESCRIPTION,
            kind=check.kind if check else "unique",  # 시나리오에 없는 검사는 주소 유일성 자동 검사뿐이다
            message=labs.redact(r.message, hidden), output=labs.redact(r.output, hidden),
        ))
    return AttemptResponse(attempt_id=attempt.id, run_id=run.id, run_status=run.status, passed=bool(attempt.passed),
                           attempted_at=to_kst(attempt.attempted_at), results=results)


def _connect(run_name: str, node: str, kind: str) -> str:
    shell = "vtysh" if kind == "router" else "sh"
    return f"docker exec -it clab-{run_name}-{node} {shell}"


def _run(session: Session, run_id: int) -> LabRun:
    try:
        return labs.get_run(session, run_id)
    except labs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _scenarios_dir(request: Request) -> Path:
    return request.app.state.scenarios_dir

