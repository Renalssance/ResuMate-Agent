import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.db.database import Base
from backend.db.models import User
from backend.schemas.settings import LlmSettingsUpdate
from backend.services.llm_settings import read_llm_settings, resolve_effective_llm_settings, save_llm_settings


@pytest.fixture
def account(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'server-secret')
    monkeypatch.setenv('OPENAI_BASE_URL', 'https://server.example/v1')
    monkeypatch.setenv('LLM_MODEL', 'server-model')
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(username='new-user', password_hash='unused', role='user')
        db.add(user)
        db.commit()
        yield db, user.id
    engine.dispose()


def test_new_account_starts_without_provider_configuration(account):
    db, user_id = account
    settings = read_llm_settings(user_id, db)
    assert not settings.has_api_key
    assert settings.api_key_hint == ''
    assert settings.base_url == ''
    assert settings.model == ''
    assert resolve_effective_llm_settings(user_id, db).api_key == ''


def test_saved_settings_and_cleared_key_do_not_inherit_server_values(account):
    db, user_id = account
    save_llm_settings(user_id, LlmSettingsUpdate(api_key='personal-key', base_url='https://own.example/v1', model='own-model'), db)
    save_llm_settings(user_id, LlmSettingsUpdate(api_key='', model='updated-model'), db)
    assert resolve_effective_llm_settings(user_id, db).api_key == 'personal-key'
    settings = save_llm_settings(user_id, LlmSettingsUpdate(clear_api_key=True, base_url='', model=''), db)
    assert not settings.has_api_key
    assert settings.base_url == ''
    assert settings.model == ''


def test_non_account_calls_keep_environment_configuration(account):
    db, _ = account
    assert resolve_effective_llm_settings(None, db).api_key == 'server-secret'


@pytest.mark.parametrize('caller', ['harness', 'chat', 'interview_tool'])
def test_account_calls_reject_missing_base_url(account, monkeypatch, caller):
    from backend.agent import agent, interview_tools
    from backend.agents import harness

    db, user_id = account
    save_llm_settings(user_id, LlmSettingsUpdate(api_key='personal-key', model='own-model'), db)
    settings = resolve_effective_llm_settings(user_id, db)
    if caller == 'harness':
        monkeypatch.setattr(harness, 'resolve_effective_llm_settings', lambda *_: settings)
        with pytest.raises(RuntimeError, match='Base URL'):
            harness.AgentHarness(user_id)
    elif caller == 'chat':
        monkeypatch.setattr(agent, 'SessionLocal', lambda: db)
        with pytest.raises(RuntimeError, match='Base URL'):
            agent.create_agent_with_interview_tools('new-user')
    else:
        monkeypatch.setattr(interview_tools, 'resolve_effective_llm_settings', lambda *_: settings)
        assert interview_tools._get_llm(user_id=user_id) is None
