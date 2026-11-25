from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from backend import models  # noqa: F401
from backend.database import MIGRATIONS_DIR, Base, init_db, make_engine


def alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


def head_revision() -> str:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def test_migrations_match_models(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'm.db'}")
    init_db(engine)
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
    engine.dispose()


def test_init_db_upgrades_to_head_and_is_repeatable(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'm.db'}")
    init_db(engine)
    init_db(engine)  # 앱을 다시 시작해도 문제없어야 한다
    with engine.connect() as conn:
        assert MigrationContext.configure(conn).get_current_revision() == head_revision()
    engine.dispose()


def test_upgrade_from_0001_keeps_existing_concepts(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'm.db'}")
    config = alembic_config()
    with engine.begin() as conn:
        config.attributes["connection"] = conn
        command.upgrade(config, "0001")
        conn.execute(text(
            "INSERT INTO concepts (id, source_type, source_ref, content_hash, title, content,"
            " keywords, seed_questions, archived, created_at, updated_at) VALUES"
            " ('NET-001', 'markdown', 'a.md', 'h', 'OSI', '본문', '[]', '[]', 0,"
            " '2026-11-12 00:00:00', '2026-11-12 00:00:00')"
        ))
    init_db(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT title FROM concepts")).scalar_one() == "OSI"
        assert conn.execute(text("SELECT count(*) FROM review_cards")).scalar_one() == 0
    engine.dispose()


def test_upgrade_from_0003_marks_existing_questions_as_variant(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'm.db'}")
    config = alembic_config()
    with engine.begin() as conn:
        config.attributes["connection"] = conn
        command.upgrade(config, "0003")
        conn.execute(text(
            "INSERT INTO concepts (id, source_type, source_ref, content_hash, title, content,"
            " keywords, seed_questions, archived, created_at, updated_at) VALUES"
            " ('NET-001', 'markdown', 'a.md', 'h', 'OSI', '본문', '[]', '[]', 0,"
            " '2026-11-13 00:00:00', '2026-11-13 00:00:00')"
        ))
        conn.execute(text(
            "INSERT INTO review_cards (id, concept_id, question_hash, question, active, card_json,"
            " due_at, created_at, updated_at) VALUES (1, 'NET-001', 'h', 'Q', 1, '{}',"
            " '2026-11-13 00:00:00', '2026-11-13 00:00:00', '2026-11-13 00:00:00')"
        ))
        conn.execute(text(
            "INSERT INTO questions (card_id, concept_id, base_question, question, relative_difficulty,"
            " difficulty_reason, model, prompt_version, created_at) VALUES"
            " (1, 'NET-001', 'Q', 'V', 0, '이유', 'm', 'p', '2026-11-13 00:00:00')"
        ))
    init_db(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT kind, question FROM questions")).one() == ("variant", "V")
    engine.dispose()


def test_upgrade_from_0005_keeps_lab_runs_at_normal_level(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'm.db'}")
    config = alembic_config()
    with engine.begin() as conn:
        config.attributes["connection"] = conn
        command.upgrade(config, "0005")
        conn.execute(text(
            "INSERT INTO lab_runs (id, scenario_id, scenario_hash, mode, status, params_json, topology_json,"
            " checks_json, goal, image_digests_json, containerlab_version, started_at, expires_at) VALUES"
            " (1, 'LAB-001', 'h', 'build', 'passed', '{}', '{}', '{}', '목표', '{}', '0.83.0',"
            " '2026-11-24 14:55:54', '2026-11-24 15:55:54')"
        ))
    init_db(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT status, level FROM lab_runs")).one() == ("passed", "normal")
        assert conn.execute(text("SELECT count(*) FROM lab_hints")).scalar_one() == 0
    engine.dispose()
