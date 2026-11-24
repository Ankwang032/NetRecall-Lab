"""FastAPI 앱.

실행: uvicorn backend.main:create_app --factory --reload
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.api.assessments import router as assessments_router
from backend.api.concepts import router as concepts_router
from backend.api.labs import router as labs_router
from backend.api.notion import router as notion_router
from backend.api.reviews import router as reviews_router
from backend.database import init_db, make_engine, make_session_factory
from backend.models.concept import utcnow
from backend.services.lab_service import cleanup_orphans
from integrations.labs.base import LabRuntime, LabRuntimeError
from integrations.labs.containerlab.runtime import containerlab_from_env
from integrations.llm import LLMClient
from integrations.llm.gemini import gemini_from_env
from integrations.sources.notion import NotionClient, notion_from_env

DEFAULT_CONCEPTS_DIR = Path(__file__).resolve().parent.parent / "samples" / "concepts"
DEFAULT_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"
DEFAULT_SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "lab_scenarios"
log = logging.getLogger(__name__)


def create_app(
    database_url: str | None = None,
    concepts_dir: str | Path | None = None,
    llm: LLMClient | None = None,
    frontend_dir: str | Path | None = None,
    notion: NotionClient | None = None,
    notion_database: str | None = None,
    lab_runtime: LabRuntime | None = None,
    scenarios_dir: str | Path | None = None,
) -> FastAPI:
    engine = make_engine(database_url)
    init_db(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 비정상 종료 대비: DB에서 끝났는데 남은 실습 컨테이너를 지우고, 시간 제한이 지난 실습을 정리한다
        try:
            with app.state.session_factory() as session:
                removed = cleanup_orphans(session, app.state.lab_runtime, utcnow())
            if removed:
                log.info("남은 실습을 정리했습니다: %s", ", ".join(removed))
        except LabRuntimeError as exc:  # Docker·Containerlab이 없어도 앱은 뜬다. 실습 API만 실패한다
            log.warning("실습 정리를 건너뜁니다: %s", exc)
        yield

    app = FastAPI(title="NetRecall Lab", lifespan=lifespan)
    app.state.session_factory = make_session_factory(engine)
    # .env 파일은 셸이 아니라 ~를 풀지 않으므로 여기서 홈 폴더로 바꾼다
    app.state.concepts_dir = Path(
        concepts_dir or os.environ.get("NETRECALL_CONCEPTS_DIR", DEFAULT_CONCEPTS_DIR)
    ).expanduser()
    # GEMINI_API_KEY가 없으면 None: AI 기능만 503이고 나머지는 동작한다
    app.state.llm = llm or gemini_from_env()
    # NOTION_TOKEN이 없으면 None: Notion 가져오기 API만 503이다
    app.state.notion = notion or notion_from_env()
    # 동기화할 Notion 데이터베이스 주소나 id. 없으면 POST /sync/notion만 503이다
    app.state.notion_database = notion_database or os.environ.get("NETRECALL_NOTION_DATABASE")
    # 실습 실행 환경. 만들 때는 아무것도 실행하지 않는다
    app.state.lab_runtime = lab_runtime or containerlab_from_env()
    app.state.scenarios_dir = Path(scenarios_dir or DEFAULT_SCENARIOS_DIR)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(concepts_router)
    app.include_router(reviews_router)
    app.include_router(assessments_router)
    app.include_router(notion_router)
    app.include_router(labs_router)

    # 빌드된 UI(frontend에서 npm run build)가 있으면 /에서 보여 준다. 위 API 경로가 먼저 매칭된다
    ui_dir = Path(frontend_dir or DEFAULT_FRONTEND_DIR)
    if ui_dir.is_dir():
        app.mount("/", StaticFiles(directory=ui_dir, html=True), name="ui")
    return app
