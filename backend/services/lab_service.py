"""실습 실행 흐름: 시작(배포) → 검증(반복) → 끝내기(정리), 시간 제한, 남은 실습 정리.

- 동시에 진행하는 실습은 하나뿐이다.
- 시간 제한은 실습 API·CLI를 부를 때와 앱을 시작할 때 확인한다. 지난 실습은 상태를 수집한 뒤 정리한다.
- 실습 결과는 FSRS 등급에 반영하지 않는다.
- 학습자에게 주지 않은 목표 주소(preset에 없고 address 검사가 정한 주소)는 화면에 내보내기 전에 가린다.
  LAB-001처럼 주소를 계산하는 실습에서 검증 메시지가 답을 알려 주지 않게 하기 위해서다. DB에는 그대로 남긴다.
"""
from __future__ import annotations

import random
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import AnswerEvaluation, LabAttempt, LabHint, LabResult, LabRun
from integrations.labs.base import Endpoint, LabRuntime, LabRuntimeError, RenderedTopology, TopologyLink, TopologyNode

from .lab_checks import UNIQUE_CHECK_ID, UNIQUE_DESCRIPTION, UNIQUE_HINTS, CommandOutput, collect_state, verify
from .lab_preset import apply_preset
from .lab_scenario import SCENARIO_FILE, RenderedCheck, RenderedLab, Scenario, ScenarioError, load_scenario, render

LIVE = ("deploying", "active", "passed")  # 환경이 있을 수 있는 상태 (destroyed_at이 없을 때)
# 도움 수준 → 검사마다 볼 수 있는 힌트 단계 수. hard는 힌트가 없고, 끝낼 때까지 검사 목록·검사별 결과도 숨긴다
LEVELS = {"easy": 3, "normal": 2, "hard": 0}
LEVEL_NAMES = {"easy": "쉬움", "normal": "보통", "hard": "어려움"}


class LabError(Exception):
    pass


class ScenarioNotFound(LabError):
    pass


class RunNotFound(LabError):
    pass


class EvaluationNotFound(LabError):
    pass


class RunInProgress(LabError):
    def __init__(self, run_id: int) -> None:
        super().__init__(f"진행 중인 실습이 있습니다 (실행 {run_id}). 먼저 끝내세요")
        self.run_id = run_id


class RunNotActive(LabError):
    pass


class HintsUnavailable(LabError):
    pass


class CheckNotFound(LabError):
    pass


class DeployFailed(LabError):
    def __init__(self, run: LabRun) -> None:
        super().__init__(f"배포에 실패했습니다: {run.error}")
        self.run = run


# ---- 시나리오 ----

def load_scenarios(root: Path) -> tuple[list[Scenario], list[tuple[str, str]]]:
    """`root/<id>/scenario.yaml`을 모두 읽는다. 읽지 못한 것은 (폴더 이름, 이유)로 돌려준다."""
    scenarios, errors = [], []
    directories = sorted(p for p in root.iterdir() if (p / SCENARIO_FILE).is_file()) if root.is_dir() else []
    for directory in directories:
        try:
            scenarios.append(load_scenario(directory))
        except (ScenarioError, OSError) as exc:
            errors.append((directory.name, str(exc)))
    return scenarios, errors


def find_scenario(root: Path, scenario_id: str) -> Scenario:
    scenario = next((s for s in load_scenarios(root)[0] if s.id == scenario_id), None)
    if scenario is None:
        raise ScenarioNotFound(f"실습 시나리오가 없습니다: {scenario_id}")
    return scenario


# ---- 실행 ----

def current_run(session: Session) -> LabRun | None:
    return session.scalar(
        select(LabRun).where(LabRun.status.in_(LIVE), LabRun.destroyed_at.is_(None)).order_by(LabRun.id.desc())
    )


def get_run(session: Session, run_id: int) -> LabRun:
    run = session.get(LabRun, run_id)
    if run is None:
        raise RunNotFound(f"실행이 없습니다: {run_id}")
    return run


def start_run(session: Session, runtime: LabRuntime, scenario: Scenario, now: datetime,
              evaluation_id: int | None = None, rng: random.Random | None = None, level: str = "normal") -> LabRun:
    """대역을 고르고 배포한 뒤 preset을 넣는다. 배포가 실패하면 deploy_failed로 남기고 DeployFailed."""
    if level not in LEVELS:
        raise LabError(f"난이도는 {', '.join(LEVELS)} 중 하나입니다: {level}")
    active = current_run(session)
    if active is not None:
        raise RunInProgress(active.id)
    if evaluation_id is not None and session.get(AnswerEvaluation, evaluation_id) is None:
        raise EvaluationNotFound(f"답안 평가가 없습니다: {evaluation_id}")

    run = LabRun(
        scenario_id=scenario.id, scenario_hash=scenario.source_hash, evaluation_id=evaluation_id,
        mode=scenario.type, status="deploying", level=level, params_json={}, topology_json={}, checks_json={}, goal="",
        image_digests_json={}, containerlab_version="", started_at=now,
        expires_at=now + timedelta(minutes=scenario.time_limit_minutes),
    )
    session.add(run)
    session.flush()  # 실습 이름(nr-<실행 id>)에 id가 필요하다
    lab = render(scenario, run.id, rng)
    _store(run, lab)
    session.commit()

    try:
        info = runtime.describe()
        run.image_digests_json, run.containerlab_version = info.images, info.version
        runtime.deploy(lab.run_name, lab.topology)
        apply_preset(runtime, lab)
    except LabRuntimeError as exc:
        try:
            runtime.destroy(lab.run_name)
        except LabRuntimeError:
            pass
        run.status, run.error = "deploy_failed", str(exc)
        run.finished_at = run.destroyed_at = now
        session.commit()
        raise DeployFailed(run) from exc
    run.status = "active"
    session.commit()
    return run


def verify_run(session: Session, runtime: LabRuntime, run_id: int, now: datetime) -> LabAttempt:
    run = get_run(session, run_id)
    expire_overdue(session, runtime, now)
    if run.status not in ("active", "passed") or run.destroyed_at is not None:
        raise RunNotActive(_not_active_reason(run))
    lab = rendered_lab(run)
    v = verify(runtime, lab)
    attempt = LabAttempt(run_id=run.id, kind="verify", passed=v.passed, state_json=_state_json(v.state),
                         attempted_at=now)
    session.add(attempt)
    session.flush()
    session.add_all(LabResult(attempt_id=attempt.id, check_id=r.id, passed=r.passed, message=r.message,
                              output=r.output) for r in v.results)
    if v.passed:
        run.status = "passed"
    session.commit()
    return attempt


# ---- 힌트 ----

@dataclass(frozen=True)
class HintReveal:
    check_id: str
    number: int               # 검증 결과의 번호 (1부터, 주소 유일성 자동 검사가 마지막)
    description: str
    hints: tuple[str, ...]    # 지금까지 연 힌트 (목표 주소는 가림)
    new: bool                 # 이번에 새 단계를 열었는가
    limit: int                # 이 난이도에서 볼 수 있는 단계 수
    total: int                # 검사의 힌트 수


def numbered_checks(lab: RenderedLab) -> list[tuple[str, str, tuple[str, ...]]]:
    """(검사 id, 설명, 힌트)를 검증 결과와 같은 순서로. 주소 유일성 자동 검사가 마지막이다."""
    return [(c.id, c.description, c.hints) for c in lab.checks] + [(UNIQUE_CHECK_ID, UNIQUE_DESCRIPTION, UNIQUE_HINTS)]


def reveal_hint(session: Session, runtime: LabRuntime, run_id: int, check_id: str | None, now: datetime) -> HintReveal:
    """그 검사의 힌트를 한 단계 더 연다. 이 난이도에서 볼 수 있는 단계를 다 봤으면 본 것만 다시 돌려준다.

    검사를 고르지 않으면 마지막 검증에서 처음 실패한 검사(힌트가 있는 것), 검증한 적이 없으면 첫 검사다.
    """
    run = get_run(session, run_id)
    expire_overdue(session, runtime, now)
    if run.status not in ("active", "passed") or run.destroyed_at is not None:
        raise RunNotActive(_not_active_reason(run))
    if LEVELS[run.level] == 0:
        raise HintsUnavailable(f"{LEVEL_NAMES[run.level]} 난이도에서는 힌트가 없습니다")
    lab = rendered_lab(run)
    checks = numbered_checks(lab)
    if check_id is None:
        check_id = _hint_target(session, run.id, checks)
    found = next(((i, c) for i, c in enumerate(checks, 1) if c[0] == check_id), None)
    if found is None:
        raise CheckNotFound(f"검사가 없습니다: {check_id}")
    number, (_, description, hints) = found
    if not hints:
        raise HintsUnavailable(f"{number}번 검사에는 힌트가 없습니다")
    limit = min(LEVELS[run.level], len(hints))
    seen = session.scalar(select(func.count()).select_from(LabHint)
                          .where(LabHint.run_id == run.id, LabHint.check_id == check_id))
    new = seen < limit
    if new:
        seen += 1
        session.add(LabHint(run_id=run.id, check_id=check_id, step=seen, shown_at=now))
        session.commit()
    hidden = hidden_addresses(lab)
    return HintReveal(check_id, number, description, tuple(redact(h, hidden) for h in hints[:seen]), new, limit,
                      len(hints))


def hints_used(session: Session, run_id: int) -> int:
    return session.scalar(select(func.count()).select_from(LabHint).where(LabHint.run_id == run_id))


def opened_hints(session: Session, run: LabRun) -> dict[str, tuple[str, ...]]:
    """검사 id → 지금까지 연 힌트. 화면을 새로 열어도 본 힌트를 다시 보여 주기 위해 쓴다 (새 단계는 열지 않는다)."""
    steps = dict(session.execute(select(LabHint.check_id, func.max(LabHint.step))
                                 .where(LabHint.run_id == run.id).group_by(LabHint.check_id)).all())
    if not steps:
        return {}
    lab = rendered_lab(run)
    hidden = hidden_addresses(lab)
    return {check_id: tuple(redact(h, hidden) for h in hints[:steps[check_id]])
            for check_id, _, hints in numbered_checks(lab) if check_id in steps}


def last_runs(session: Session) -> dict[str, LabRun]:
    """시나리오 id → 가장 최근 실행."""
    latest = select(func.max(LabRun.id)).group_by(LabRun.scenario_id)
    return {run.scenario_id: run for run in session.scalars(select(LabRun).where(LabRun.id.in_(latest)))}


def _hint_target(session: Session, run_id: int, checks: list[tuple[str, str, tuple[str, ...]]]) -> str:
    with_hints = [c[0] for c in checks if c[2]]
    if not with_hints:
        raise HintsUnavailable("이 실습에는 힌트가 없습니다")
    verified = [a for a in attempts_of(session, run_id) if a.kind == "verify"]
    if not verified:
        return with_hints[0]
    if verified[-1].passed:
        raise HintsUnavailable("마지막 검증에서 모든 검사를 통과했습니다. 다른 검사의 힌트는 검사를 골라 보세요")
    failed = [r.check_id for r in results_of(session, verified[-1].id) if not r.passed]
    target = next((c for c in failed if c in with_hints), None)
    if target is None:
        raise HintsUnavailable("실패한 검사에 힌트가 없습니다")
    return target


def finish_run(session: Session, runtime: LabRuntime, run_id: int, now: datetime) -> LabRun:
    """학습자가 끝낸다. 통과하지 못했으면 abandoned. 이미 끝난 실행이면 그대로 돌려준다."""
    run = get_run(session, run_id)
    if run.destroyed_at is None and run.status in ("active", "passed"):
        _close(session, runtime, run, now, "abandoned")
    return run


def expire_overdue(session: Session, runtime: LabRuntime, now: datetime) -> list[int]:
    """시간 제한이 지난 실행을 정리한다. 통과하지 못했으면 expired."""
    overdue = session.scalars(
        select(LabRun).where(LabRun.status.in_(("active", "passed")), LabRun.destroyed_at.is_(None))
    ).all()
    expired = []
    for run in overdue:
        if _aware(run.expires_at) <= now:
            _close(session, runtime, run, now, "expired")
            expired.append(run.id)
    return expired


def cleanup_orphans(session: Session, runtime: LabRuntime, now: datetime) -> list[str]:
    """앱을 시작할 때 부른다 (비정상 종료 대비). 지운 실습 이름을 돌려준다.

    - 끝났는데 환경이 남은 실행, 배포 중에 앱이 멈춘 실행(deploy_failed로 바꿈)의 환경을 지운다.
    - 진행 중인데 환경이 사라진 실행(호스트 재시작 등)은 끝난 것으로 표시한다.
    - 이 DB가 만들지 않은 실습(다른 DB, 테스트)은 건드리지 않는다. 실행 기록은 배포 전에 커밋하므로
      이 DB가 만든 실습은 모두 기록이 있다.
    """
    deployed = set(runtime.list_runs())
    removed = []
    for run in session.scalars(select(LabRun).where(LabRun.destroyed_at.is_(None))).all():
        name = f"nr-{run.id}"
        in_progress = run.status in ("active", "passed")
        if in_progress and name in deployed:
            continue
        if name in deployed:
            runtime.destroy(name)
            removed.append(name)
        if run.status == "deploying":
            run.status, run.error = "deploy_failed", "배포 중에 앱이 멈췄습니다"
        elif in_progress:
            run.status = "passed" if run.status == "passed" else "abandoned"
            run.error = "실습 환경이 사라졌습니다"
        run.finished_at = run.finished_at or now
        run.destroyed_at = now
    session.commit()
    expire_overdue(session, runtime, now)
    return removed


def attempts_of(session: Session, run_id: int) -> list[LabAttempt]:
    return list(session.scalars(select(LabAttempt).where(LabAttempt.run_id == run_id).order_by(LabAttempt.id)))


def results_of(session: Session, attempt_id: int) -> list[LabResult]:
    return list(session.scalars(select(LabResult).where(LabResult.attempt_id == attempt_id).order_by(LabResult.id)))


# ---- 렌더링 결과 저장·복원 ----

def rendered_lab(run: LabRun) -> RenderedLab:
    topology, checks = run.topology_json, run.checks_json
    return RenderedLab(
        scenario_id=run.scenario_id,
        scenario_hash=run.scenario_hash,
        run_name=f"nr-{run.id}",
        networks=dict(run.params_json),
        topology=RenderedTopology(
            tuple(TopologyNode(name, kind) for name, kind in topology["nodes"]),
            tuple(TopologyLink(_endpoint(a), _endpoint(b)) for a, b in topology["links"]),
        ),
        preset_addresses=tuple((_endpoint(e), a) for e, a in topology["preset_addresses"]),
        expected_addresses={ip: _endpoint(e) for ip, e in checks["expected_addresses"].items()},
        goal=run.goal,
        checks=tuple(
            RenderedCheck(**{**c, "protocols": tuple(c["protocols"]) if c["protocols"] is not None else None,
                             "hints": tuple(c.get("hints", ()))})  # 힌트가 생기기 전(0006 이전) 실행에는 없다
            for c in checks["checks"]
        ),
        time_limit_minutes=int((_aware(run.expires_at) - _aware(run.started_at)).total_seconds() // 60),
    )


def hidden_addresses(lab: RenderedLab) -> dict[str, Endpoint]:
    """검사가 가리키지만 학습자에게 주지 않은 주소 → 있어야 할 곳."""
    given = {address.split("/")[0] for _, address in lab.preset_addresses}
    return {ip: e for ip, e in lab.expected_addresses.items() if ip not in given}


def redact(text: str, hidden: dict[str, Endpoint]) -> str:
    for ip, endpoint in hidden.items():
        text = re.sub(rf"(?<![\d.]){re.escape(ip)}(?!\d)", f"[{endpoint} 목표 주소]", text)
    return text


def _store(run: LabRun, lab: RenderedLab) -> None:
    run.params_json = lab.networks
    run.topology_json = {
        "nodes": [[n.name, n.kind] for n in lab.topology.nodes],
        "links": [[str(link.a), str(link.b)] for link in lab.topology.links],
        "preset_addresses": [[str(e), a] for e, a in lab.preset_addresses],
    }
    run.checks_json = {
        "checks": [asdict(c) for c in lab.checks],
        "expected_addresses": {ip: str(e) for ip, e in lab.expected_addresses.items()},
    }
    run.goal = lab.goal


def _close(session: Session, runtime: LabRuntime, run: LabRun, now: datetime, unpassed_status: str) -> None:
    """마지막 상태를 남기고 환경을 지운다. 통과한 실행은 passed 그대로 둔다."""
    lab = rendered_lab(run)
    state = collect_state(runtime, lab)
    session.add(LabAttempt(run_id=run.id, kind="final", passed=None, state_json=_state_json(state), attempted_at=now))
    try:
        runtime.destroy(lab.run_name)
    except LabRuntimeError as exc:
        run.error = f"정리하지 못했습니다: {exc}"  # 다음에 앱을 시작할 때 남은 실습으로 다시 지운다
    else:
        run.destroyed_at = now
    if run.status != "passed":
        run.status = unpassed_status
    run.finished_at = now
    session.commit()


def _not_active_reason(run: LabRun) -> str:
    reasons = {
        "expired": "시간 제한이 지나 정리한 실습입니다",
        "abandoned": "끝낸 실습입니다",
        "deploy_failed": "배포에 실패한 실습입니다",
        "deploying": "배포 중인 실습입니다",
    }
    return reasons.get(run.status, "끝낸 실습입니다")


def _state_json(state: dict[str, dict[str, CommandOutput]]) -> dict:
    return {node: {name: {**asdict(out), "argv": list(out.argv)} for name, out in outputs.items()}
            for node, outputs in state.items()}


def _endpoint(text: str) -> Endpoint:
    node, interface = text.split(":")
    return Endpoint(node, interface)


def _aware(value: datetime) -> datetime:
    # SQLite에서 읽은 시각은 시간대가 없다. UTC로 저장했으므로 UTC로 본다
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
