"""Alembic 실행 환경.

- 앱 시작 시: backend.database.init_db가 연결을 config.attributes["connection"]으로 넘긴다.
- CLI(alembic revision --autogenerate 등): NETRECALL_DATABASE_URL 또는 기본 DB에 연결한다.
"""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from backend import models  # noqa: F401  테이블을 Base.metadata에 등록
from backend.database import Base, make_engine

config = context.config
target_metadata = Base.metadata


def run_migrations(connection) -> None:
    # SQLite는 ALTER TABLE이 제한적이라 테이블 복사 방식(batch)으로 변경한다
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


connection = config.attributes.get("connection")
if connection is not None:
    run_migrations(connection)
else:
    if config.config_file_name is not None:
        fileConfig(config.config_file_name)
    engine = make_engine()
    with engine.connect() as conn:
        run_migrations(conn)
    engine.dispose()
