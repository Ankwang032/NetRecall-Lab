"""명령줄 도구. 서버 없이 같은 DB·실습 환경을 쓴다.

    python -m backend.cli [--env-file .env] lab list
    python -m backend.cli lab start LAB-001 [--level easy|normal|hard]
    python -m backend.cli lab status [실행 id]
    python -m backend.cli lab verify [실행 id]     # 통과하면 종료 코드 0, 아니면 1
    python -m backend.cli lab hint [검사 번호]      # 진행 중인 실습. 번호를 빼면 마지막 검증에서 처음 실패한 검사
    python -m backend.cli lab finish [실행 id]

실행 id를 빼면 진행 중인 실습을 쓴다. 노드 설정은 출력된 접속 명령(docker exec)으로 자기 터미널에서 한다.
"""
from __future__ import annotations

import argparse
import math
import shlex
import sys
from datetime import datetime

from dotenv import load_dotenv

from backend.api.labs import AttemptResponse, RunResponse, attempt_response, run_response
from backend.database import init_db, make_engine, make_session_factory
from backend.main import DEFAULT_SCENARIOS_DIR
from backend.models.concept import utcnow
from backend.services import lab_service as labs
from integrations.labs.containerlab.runtime import containerlab_from_env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.cli", description="NetRecall Lab 명령줄 도구")
    parser.add_argument("--env-file", help="환경변수 파일 (예: .env)")
    groups = parser.add_subparsers(dest="group", required=True)
    lab = groups.add_parser("lab", help="실습").add_subparsers(dest="command", required=True)
    lab.add_parser("list", help="실습 시나리오 목록")
    start = lab.add_parser("start", help="실습 시작 (배포)")
    start.add_argument("scenario_id")
    start.add_argument("--level", choices=list(labs.LEVELS), default="normal",
                       help="도움 수준: easy(힌트 3단계), normal(2단계), hard(힌트 없음, 검사 목록·검사별 결과 숨김)")
    lab.add_parser("hint", help="힌트 한 단계 더 보기").add_argument("number", nargs="?", type=int)
    for name, text in (("status", "실습 상태"), ("verify", "검증"), ("finish", "끝내기 (정리)")):
        lab.add_parser(name, help=text).add_argument("run_id", nargs="?", type=int)
    args = parser.parse_args(argv)

    if args.env_file:
        load_dotenv(args.env_file)
    engine = make_engine()
    init_db(engine)
    runtime = containerlab_from_env()
    command = "python -m backend.cli" + (f" --env-file {shlex.quote(args.env_file)}" if args.env_file else "")
    try:
        with make_session_factory(engine)() as session:
            return _lab(args, session, runtime, command)
    except labs.LabError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    finally:
        engine.dispose()


def _lab(args, session, runtime, command: str) -> int:
    now = utcnow()
    if args.command == "list":
        scenarios, errors = labs.load_scenarios(DEFAULT_SCENARIOS_DIR)
        for s in scenarios:
            print(f"{s.id}  {s.title}  (개념 {', '.join(s.concepts)}, {s.time_limit_minutes}분)")
        for name, message in errors:
            print(f"{name}  읽지 못함: {message}", file=sys.stderr)
        return 0

    labs.expire_overdue(session, runtime, now)
    if args.command == "start":
        run = labs.start_run(session, runtime, labs.find_scenario(DEFAULT_SCENARIOS_DIR, args.scenario_id), now,
                             level=args.level)
        info = run_response(session, run, DEFAULT_SCENARIOS_DIR)
        _print_run(info, now)
        print("\n다음:")
        print(f"  검증    {command} lab verify   (노드를 설정한 뒤. 몇 번이든 다시 할 수 있습니다)")
        if info.hint_limit:
            print(f"  힌트    {command} lab hint [검사 번호]   (막혔을 때. 번호를 빼면 처음 실패한 검사)")
        print(f"  끝내기  {command} lab finish   ({FINISH_NOTE})")
        return 0
    if args.command == "hint":
        return _hint(session, runtime, args.number, now)

    run_id = args.run_id or _current_id(session)
    if args.command == "status":
        _print_run(run_response(session, labs.get_run(session, run_id), DEFAULT_SCENARIOS_DIR), now)
        return 0
    if args.command == "verify":
        attempt = labs.verify_run(session, runtime, run_id, now)
        run = labs.get_run(session, run_id)
        result = attempt_response(session, attempt, run)
        _print_attempt(result, run_response(session, run, DEFAULT_SCENARIOS_DIR), now, command)
        return 0 if result.passed else 1
    run = labs.finish_run(session, runtime, run_id, now)
    print(f"실행 {run.id}을 끝냈습니다 ({run.status})" + (f": {run.error}" if run.error else ""))
    if run.destroyed_at:
        print("실습 환경을 지웠습니다. 마지막 설정은 기록에 남았습니다")
    return 0


def _current_id(session) -> int:
    run = labs.current_run(session)
    if run is None:
        raise labs.RunNotFound("진행 중인 실습이 없습니다. 실행 id를 주세요")
    return run.id


FINISH_NOTE = "실습 환경을 지웁니다. 마지막 설정은 기록에 남습니다"
LEVEL_NOTES = {
    "easy": "힌트는 검사마다 3단계까지",
    "normal": "힌트는 검사마다 2단계까지",
    "hard": "힌트 없음. 끝낼 때까지 검사 목록과 검사별 결과를 보여 주지 않습니다",
}


def _hint(session, runtime, number: int | None, now: datetime) -> int:
    run_id = _current_id(session)
    check_id = None
    if number is not None:
        checks = labs.numbered_checks(labs.rendered_lab(labs.get_run(session, run_id)))
        if not 1 <= number <= len(checks):
            raise labs.CheckNotFound(f"검사 번호는 1~{len(checks)}입니다")
        check_id = checks[number - 1][0]
    try:
        h = labs.reveal_hint(session, runtime, run_id, check_id, now)
    except labs.HintsUnavailable as exc:
        print(exc)
        return 1
    level = labs.get_run(session, run_id).level
    print(f"{h.number}. {h.description} · 힌트 {len(h.hints)}/{h.total}")
    for i, text in enumerate(h.hints, 1):
        print(f"  {i}) {text}")
    if not h.new:
        print(f"\n더 볼 수 있는 힌트가 없습니다"
              + (f" ({labs.LEVEL_NAMES[level]} 난이도는 {h.limit}단계까지)" if h.limit < h.total else ""))
    return 0


def _remaining(run: RunResponse, now: datetime) -> str:
    """끝나지 않은 실행의 남은 시간. 시간 제한이 지나면 다음 lab 명령 때 정리된다."""
    seconds = (run.expires_at - now).total_seconds()
    left = f"{math.ceil(seconds / 60)}분" if seconds >= 60 else "1분 미만"
    return f"남은 시간 {left} ({run.expires_at:%H:%M} KST까지, 지나면 다음 lab 명령 때 환경을 지웁니다)"


def _print_run(run: RunResponse, now: datetime) -> None:
    print(f"실행 {run.run_id} · {run.scenario_id} {run.title} ({run.status})")
    print(f"난이도: {labs.LEVEL_NAMES[run.level]} ({LEVEL_NOTES[run.level]})")
    print("\n목표:")
    print("  " + run.goal.replace("\n", "\n  "))
    if run.networks:
        print("\n대역:")
        for name, network in run.networks.items():
            print(f"  {name} = {network}")
    if run.addresses:
        print("\n배포할 때 넣은 주소:")
        for a in run.addresses:
            print(f"  {a.interface:<10} {a.address}")
    print("\n접속 (자기 터미널에서):")
    for n in run.nodes:
        print(f"  {n.name:<4} {n.kind:<6} {n.connect}")
    print("\n검사:")
    for i, c in enumerate(run.checks, 1):
        print(f"  {i}. {c.description}")
    if not run.checks:
        print("  (어려움: 끝낼 때까지 보여 주지 않습니다. 목표만 보고 직접 확인하세요)")
    when = f"끝낸 시각 {run.finished_at:%Y-%m-%d %H:%M} KST" if run.finished_at else _remaining(run, now)
    print(f"\n{when} · 검증 {run.attempts}번 · 힌트 {run.hints_used}번" + (f" · {run.error}" if run.error else ""))


def _print_attempt(attempt: AttemptResponse, run: RunResponse, now: datetime, command: str) -> None:
    print(f"검증 결과: {'통과' if attempt.passed else '실패'} (실행 {attempt.run_id}, {attempt.run_status})")
    for i, r in enumerate(attempt.results, 1):
        print(f"  {i}. {'O' if r.passed else 'X'} {r.description}: {r.message}")
        if not r.passed and r.output:
            print("        " + r.output.replace("\n", "\n        "))
    if attempt.passed:
        summary = "모든 검사를 통과했습니다"
    elif attempt.results:
        summary = f"{attempt.total_count}개 중 {attempt.total_count - attempt.passed_count}개 실패"
    else:  # 어려움: 어느 검사인지 알려 주지 않는다
        summary = f"{attempt.total_count}개 중 {attempt.passed_count}개 통과"
    print(f"\n{summary} · {_remaining(run, now)}")
    if attempt.passed:
        print(f"끝내기: {command} lab finish   ({FINISH_NOTE})")
        return
    print(f"고친 뒤 다시 검증: {command} lab verify")
    if run.hint_limit:
        first = next(i for i, r in enumerate(attempt.results, 1) if not r.passed)
        print(f"막히면 힌트: {command} lab hint {first}")


if __name__ == "__main__":
    sys.exit(main())
