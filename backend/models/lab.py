"""실습 실행 기록 테이블.

시나리오는 테이블로 만들지 않는다. 저장소 파일(lab_scenarios/)이 원본이고, 실행마다 시나리오 해시와
렌더링한 토폴로지·검사 목록을 통째로 남겨 파일이 바뀌어도 그때 실행을 재현할 수 있게 한다.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class LabRun(Base):
    """실습 실행 한 번.

    status: deploying → active → passed (모든 검사를 통과한 시도가 있음)
            → abandoned (통과 못 하고 끝냄) | expired (통과 못 하고 시간 제한) | deploy_failed
    환경이 지워졌으면 destroyed_at이 있다. passed는 끝내거나 시간 제한이 되면 지우고 상태는 그대로 둔다.
    """
    __tablename__ = "lab_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String(32), index=True)  # 파일 id, FK 아님
    scenario_hash: Mapped[str] = mapped_column(String(64))
    evaluation_id: Mapped[int | None] = mapped_column(ForeignKey("answer_evaluations.id"))  # 이 실습을 추천한 평가
    mode: Mapped[str] = mapped_column(String(16))  # build
    status: Mapped[str] = mapped_column(String(16), index=True)
    params_json: Mapped[dict] = mapped_column(JSON)    # 대역 이름 → 고른 대역
    topology_json: Mapped[dict] = mapped_column(JSON)  # 노드·링크·preset 주소
    checks_json: Mapped[dict] = mapped_column(JSON)    # 렌더링한 검사 목록과 검사가 가리키는 주소의 위치
    goal: Mapped[str] = mapped_column(Text)
    image_digests_json: Mapped[dict] = mapped_column(JSON)  # 노드 종류 → 이미지 이름·id
    containerlab_version: Mapped[str] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)  # 배포 실패·환경이 사라진 이유
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    destroyed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LabAttempt(Base):
    """검증 요청 한 번(kind=verify), 또는 정리 직전의 상태 수집(kind=final, passed 없음)."""
    __tablename__ = "lab_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("lab_runs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    passed: Mapped[bool | None]
    state_json: Mapped[dict] = mapped_column(JSON)  # 노드 → 수집 항목 → 명령·종료 코드·출력
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LabResult(Base):
    __tablename__ = "lab_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("lab_attempts.id"), index=True)
    check_id: Mapped[str] = mapped_column(String(64))
    passed: Mapped[bool]
    message: Mapped[str] = mapped_column(Text)
    output: Mapped[str] = mapped_column(Text)
