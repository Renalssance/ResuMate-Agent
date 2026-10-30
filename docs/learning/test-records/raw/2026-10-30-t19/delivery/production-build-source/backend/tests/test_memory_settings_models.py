"""T12 storage/settings contract; test databases only."""
from pathlib import Path

from fastapi import HTTPException
import pytest
from sqlalchemy import inspect, text

from backend.db import career_models, database
from backend.db.agent_models import AgentSession
from backend.db.models import UserLlmSettings
from backend.schemas.settings import LlmSettingsUpdate
from backend.services.llm_settings import read_llm_settings, resolve_effective_llm_settings, save_llm_settings
from backend.tests.career_fixtures import career_engine, career_db


def test_unknown_capacity_is_not_guessed_and_setting_roundtrips(career_db):
    initial = read_llm_settings(1, career_db)
    assert 'context_window_tokens' in type(initial).model_fields
    assert initial.context_window_tokens is None
    saved = save_llm_settings(1, LlmSettingsUpdate(context_window_tokens=32000, max_tokens=4096), career_db)
    assert saved.context_window_tokens == 32000
    assert resolve_effective_llm_settings(1, career_db).context_window_tokens == 32000
    save_llm_settings(1, LlmSettingsUpdate(model='custom-compatible'), career_db)
    assert read_llm_settings(1, career_db).context_window_tokens == 32000
    save_llm_settings(1, LlmSettingsUpdate(context_window_tokens=None), career_db)
    assert read_llm_settings(1, career_db).context_window_tokens is None


def test_partial_settings_update_validates_merged_output_reserve(career_db):
    save_llm_settings(1, LlmSettingsUpdate(context_window_tokens=16000, max_tokens=4096), career_db)
    with pytest.raises(HTTPException) as failure:
        save_llm_settings(1, LlmSettingsUpdate(max_tokens=16000), career_db)
    assert failure.value.status_code == 422
    assert read_llm_settings(1, career_db).max_tokens == 4096
    with pytest.raises(HTTPException):
        save_llm_settings(1, LlmSettingsUpdate(context_window_tokens=4096), career_db)
    assert read_llm_settings(1, career_db).context_window_tokens == 16000


def test_memory_and_session_cleanup_state_persist(career_db):
    memory_type = getattr(career_models, 'BusinessMemory', None)
    assert memory_type is not None
    from backend.db.models import utcnow
    memory = memory_type(user_id=1, kind='preference', content='偏好简洁表达', source_ref={'kind': 'manual'}, confirmed_at=utcnow())
    session = AgentSession(user_id=1, purpose='tailoring')
    career_db.add_all([memory, session]); career_db.commit()
    assert session.context_invalidated_at is None and session.checkpoint_deleted_at is None
    session.context_invalidated_at = utcnow()
    memory.content = ''; memory.source_ref = {}; memory.deleted_at = utcnow()
    career_db.commit(); career_db.expire_all()
    assert memory.content == '' and memory.source_ref == {} and memory.deleted_at is not None
    assert session.context_invalidated_at is not None and session.checkpoint_deleted_at is None


def test_supported_old_database_upgrade_preserves_rows(career_db, career_engine):
    career_db.add(UserLlmSettings(user_id=1, model='existing-model', max_tokens=4096))
    career_db.add(AgentSession(id='existing-session', user_id=1, purpose='tailoring'))
    career_db.commit(); career_db.close()
    # Simulate the immediately preceding supported schema, not an invented database.
    with career_engine.begin() as connection:
        if 'business_memories' in inspect(connection).get_table_names():
            connection.execute(text('DROP TABLE business_memories'))
        if 'context_window_tokens' in {c['name'] for c in inspect(connection).get_columns('user_llm_settings')}:
            connection.execute(text('ALTER TABLE user_llm_settings DROP COLUMN context_window_tokens'))
        for name in ('context_invalidated_at', 'checkpoint_deleted_at'):
            if name in {c['name'] for c in inspect(connection).get_columns('agent_sessions')}:
                connection.execute(text(f'ALTER TABLE agent_sessions DROP COLUMN {name}'))
    if career_engine.dialect.name == 'sqlite':
        database.Base.metadata.create_all(career_engine)
        database.ensure_sqlite_schema(career_engine)
        database.ensure_sqlite_schema(career_engine)
    else:
        sql = (Path(__file__).resolve().parents[2] / 'deploy/schema/003_context_and_memory.sql').read_text()
        with career_engine.begin() as connection:
            for statement in sql.split(';'):
                if statement.strip(): connection.execute(text(statement))
    with career_engine.connect() as connection:
        assert connection.execute(text('SELECT model,context_window_tokens FROM user_llm_settings')).one() == ('existing-model', None)
        assert connection.execute(text('SELECT id,context_invalidated_at,checkpoint_deleted_at FROM agent_sessions')).one() == ('existing-session', None, None)
        assert 'business_memories' in inspect(connection).get_table_names()
