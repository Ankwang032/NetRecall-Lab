"""대시보드 API (설계서 §E-3). 저장된 기록에서 계산만 하고, 실습 시간 제한 정리도 부르지 않는다(읽기만)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.deps import get_session
from backend.api.labs import RunSummary, run_summary
from backend.models.concept import utcnow
from backend.services import dashboard
from backend.services.lab_service import last_runs, load_scenarios

router = APIRouter(prefix="/dashboard")
SessionDep = Annotated[Session, Depends(get_session)]


class LabStat(BaseModel):
    scenario_id: str
    title: str
    runs: int                    # 실행 수
    last_run: RunSummary | None  # 가장 최근 실행. 하나의 성공률 점수로 합치지 않는다 (§D-2)


class DashboardSummary(BaseModel):
    today: dashboard.Today
    reviews_by_day: list[dashboard.DayReviews]
    due_by_day: list[dashboard.DayDue]
    errors_by_week: list[dashboard.WeekErrors]
    stages: dashboard.Stages
    categories: list[dashboard.CategoryStat]
    weak_concepts: list[dashboard.WeakConcept]
    rules: dashboard.Rules
    labs: list[LabStat]


@router.get("/summary")
def get_summary(request: Request, session: SessionDep) -> DashboardSummary:
    stats = dashboard.summary(session, utcnow())
    counts = dashboard.run_counts(session)
    last = last_runs(session)
    return DashboardSummary(
        **vars(stats),
        labs=[LabStat(scenario_id=s.id, title=s.title, runs=counts.get(s.id, 0),
                      last_run=run_summary(session, last[s.id]) if s.id in last else None)
              for s in load_scenarios(request.app.state.scenarios_dir)[0]],
    )
