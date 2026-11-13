"""FastAPI 앱.

실행: uvicorn backend.main:create_app --factory --reload
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from backend.api.assessments import router as assessments_router
from backend.api.concepts import router as concepts_router
from backend.api.reviews import router as reviews_router
from backend.database import init_db, make_engine, make_session_factory
from integrations.llm import LLMClient
from integrations.llm.gemini import gemini_from_env

DEFAULT_CONCEPTS_DIR = Path(__file__).resolve().parent.parent / "samples" / "concepts"


def create_app(
    database_url: str | None = None,
    concepts_dir: str | Path | None = None,
    llm: LLMClient | None = None,
) -> FastAPI:
    engine = make_engine(database_url)
    init_db(engine)

    app = FastAPI(title="NetRecall Lab")
    app.state.session_factory = make_session_factory(engine)
    app.state.concepts_dir = Path(
        concepts_dir or os.environ.get("NETRECALL_CONCEPTS_DIR", DEFAULT_CONCEPTS_DIR)
    )
    # GEMINI_API_KEY가 없으면 None: AI 기능만 503이고 나머지는 동작한다
    app.state.llm = llm or gemini_from_env()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(concepts_router)
    app.include_router(reviews_router)
    app.include_router(assessments_router)
    return app
