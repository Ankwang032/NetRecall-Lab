"""FastAPI 앱.

실행: uvicorn backend.main:create_app --factory --reload
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.api.assessments import router as assessments_router
from backend.api.concepts import router as concepts_router
from backend.api.notion import router as notion_router
from backend.api.reviews import router as reviews_router
from backend.database import init_db, make_engine, make_session_factory
from integrations.llm import LLMClient
from integrations.llm.gemini import gemini_from_env
from integrations.sources.notion import NotionClient, notion_from_env

DEFAULT_CONCEPTS_DIR = Path(__file__).resolve().parent.parent / "samples" / "concepts"
DEFAULT_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def create_app(
    database_url: str | None = None,
    concepts_dir: str | Path | None = None,
    llm: LLMClient | None = None,
    frontend_dir: str | Path | None = None,
    notion: NotionClient | None = None,
    notion_database: str | None = None,
) -> FastAPI:
    engine = make_engine(database_url)
    init_db(engine)

    app = FastAPI(title="NetRecall Lab")
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

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(concepts_router)
    app.include_router(reviews_router)
    app.include_router(assessments_router)
    app.include_router(notion_router)

    # 빌드된 UI(frontend에서 npm run build)가 있으면 /에서 보여 준다. 위 API 경로가 먼저 매칭된다
    ui_dir = Path(frontend_dir or DEFAULT_FRONTEND_DIR)
    if ui_dir.is_dir():
        app.mount("/", StaticFiles(directory=ui_dir, html=True), name="ui")
    return app
