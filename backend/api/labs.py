"""실습 API.

흐름: GET /labs → POST /labs/{id}/runs (배포, 목표·주소표·접속 명령) → 학습자가 자기 터미널에서 docker exec로 설정
     → POST /lab-runs/{id}/attempts (검증, 반복) → 막히면 POST /lab-runs/{id}/hints → POST /lab-runs/{id}/finish (정리)
동시에 진행하는 실습은 하나다. 시간 제한은 실습 API를 부를 때 확인한다.
도움 수준(level): easy는 힌트 3단계, normal은 2단계, hard는 힌트가 없고 끝낼 때까지 검사 목록·검사별 결과를 숨긴다.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.deps import get_lab_runtime, get_session
from backend.core.time import to_kst
from backend.models import LabAttempt, LabRun
from backend.models.concept import utcnow
from backend.services import lab_service as labs
from backend.services.lab_checks import UNIQUE_DESCRIPTION
from integrations.labs.base import LabRuntime

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]
RuntimeDep = Annotated[LabRuntime, Depends(get_lab_runtime)]


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
    level: Literal["easy", "normal", "hard"] = "normal"


class HintRequest(BaseModel):
    check_id: str | None = None  # 없으면 마지막 검증에서 처음 실패한 검사


class HintResponse(BaseModel):
    check_id: str
    number: int          # 검증 결과의 번호
    description: str
    hints: list[str]     # 지금까지 연 힌트
    new: bool            # 이번에 새 단계를 열었는가
    limit: int           # 이 난이도에서 볼 수 있는 단계 수
    total: int           # 검사의 힌트 수


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
    level: str                  # easy | normal | hard
    hint_limit: int             # 검사마다 볼 수 있는 힌트 단계 수 (hard는 0)
    checks: list[CheckInfo]     # hard는 끝낼 때까지 비어 있다
    attempts: int
    hints_used: int
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
    passed_count: int
    total_count: int
    results: list[ResultInfo]  # hard는 비어 있다 (몇 개 통과했는지만 알려 준다)


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
    body = body or StartRequest()
    try:
        scenario = labs.find_scenario(_scenarios_dir(request), scenario_id)
        run = labs.start_run(session, runtime, scenario, now, evaluation_id=body.evaluation_id, level=body.level)
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


@router.post("/lab-runs/{run_id}/hints")
def hint(run_id: int, session: SessionDep, runtime: RuntimeDep,
         body: Annotated[HintRequest | None, Body()] = None) -> HintResponse:
    try:
        h = labs.reveal_hint(session, runtime, run_id, (body or HintRequest()).check_id, utcnow())
    except (labs.RunNotFound, labs.CheckNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (labs.RunNotActive, labs.HintsUnavailable) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return HintResponse(check_id=h.check_id, number=h.number, description=h.description, hints=list(h.hints),
                        new=h.new, limit=h.limit, total=h.total)


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
        level=run.level, hint_limit=labs.LEVELS[run.level],
        checks=[] if _hidden(run) else [CheckInfo(id=c.id, description=c.description) for c in lab.checks],
        attempts=len(attempts), hints_used=labs.hints_used(session, run.id),
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
                           attempted_at=to_kst(attempt.attempted_at),
                           passed_count=sum(r.passed for r in results), total_count=len(results),
                           results=[] if _hidden(run) else results)


def _hidden(run: LabRun) -> bool:
    """어려움 난이도는 진행 중에 검사 목록과 검사별 결과를 보여 주지 않는다. 끝나면 보여 준다."""
    return run.level == "hard" and run.finished_at is None


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

