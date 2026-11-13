"""SQLite 연결, 세션, 스키마 마이그레이션."""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import Engine, MetaData, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DEFAULT_DATABASE_URL = "sqlite:///netrecall.db"
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

# 제약 이름을 고정한다. SQLite에서 Alembic이 제약을 바꾸려면(batch 모드) 이름이 필요하다.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def make_engine(url: str | None = None) -> Engine:
    url = url or os.environ.get("NETRECALL_DATABASE_URL", DEFAULT_DATABASE_URL)
    engine = create_engine(url)
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def _enable_sqlite_foreign_keys(dbapi_connection, _record) -> None:
    # SQLite는 연결마다 켜야 FK를 검사한다
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    """DB를 최신 리비전까지 마이그레이션한다. 앱 시작 시 자동으로 호출된다."""
    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
