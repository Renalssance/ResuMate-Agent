"""Exercise actual SDK transports with synthetic local responses, never a provider."""
import asyncio
from types import SimpleNamespace

import httpx
import pytest
from openai import APIStatusError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.agent import agent, interview_tools
from backend.agent_runtime import factory
from backend.agents import harness
from backend.db.database import Base
from backend.db.models import User
from backend.vector.embedding import EmbeddingService


@pytest.fixture
def settings(monkeypatch):
    value = SimpleNamespace(api_key='synthetic-key', base_url='https://model.example/v1',
        model='synthetic-model', max_tokens=1024, context_window_tokens=32768,
        request_timeout_seconds=7.0)
    for module in (factory, agent, interview_tools, harness):
        monkeypatch.setattr(module, 'resolve_effective_llm_settings', lambda *args: value)
    monkeypatch.setenv('EMBEDDING_API_KEY', value.api_key)
    monkeypatch.setenv('EMBEDDING_BASE_URL', value.base_url)
    return value


@pytest.fixture
def chat_model(monkeypatch, settings, request):
    engine = create_engine('sqlite://')
    sessions = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    with sessions() as db:
        db.add(User(username='transport-user', password_hash='unused', role='user'))
        db.commit()
    monkeypatch.setattr(agent, 'SessionLocal', sessions)
    monkeypatch.setattr(agent, 'create_agent', lambda **kwargs: object())
    from evals.run import make_live_model
    from langchain_core.callbacks import BaseCallbackHandler
    monkeypatch.setenv('OPENAI_API_KEY', settings.api_key)
    monkeypatch.setenv('OPENAI_BASE_URL', settings.base_url)
    settings.max_output_tokens = settings.max_tokens
    settings.enable_thinking = False
    model = {'eval': lambda: make_live_model(settings, BaseCallbackHandler(), {}),
             'graph': lambda: factory.model_for_user(1),
             'chat': lambda: agent.create_agent_with_interview_tools('transport-user')[1],
             'tool': lambda: interview_tools._get_llm(user_id=1)}[request.param]()
    yield model
    if model.http_client is not None:
        model.http_client.close()
    if model.http_async_client is not None:
        asyncio.run(model.http_async_client.aclose())
    engine.dispose()


def intercept_redirect(monkeypatch, location, status):
    calls = []
    def respond(request):
        calls.append(request)
        if request.url.path.endswith('/sink'):
            return httpx.Response(401, json={'error': {'message': 'redirect target reached'}})
        return httpx.Response(status, headers={'location': location})
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', lambda self, request: respond(request))
    async def respond_async(self, request):
        return respond(request)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', respond_async)
    return calls


@pytest.mark.parametrize('chat_model', ['graph', 'chat', 'tool', 'eval'], indirect=True)
@pytest.mark.parametrize('asynchronous', [False, True])
@pytest.mark.parametrize('status,location', [(307, 'https://model.example/sink'), (308, 'https://other.example/sink')])
def test_chat_sdk_stops_redirect_and_applies_account_timeout(chat_model, asynchronous, status, location, monkeypatch):
    calls = intercept_redirect(monkeypatch, location, status)
    with pytest.raises(APIStatusError):
        if asynchronous:
            asyncio.run(chat_model.ainvoke('synthetic input'))
        else:
            chat_model.invoke('synthetic input')
    assert len(calls) == 1, 'a redirected request must never be sent'
    assert calls[0].extensions['timeout']['read'] == 7.0
    assert calls[0].headers['authorization'] == 'Bearer synthetic-key'


@pytest.mark.parametrize('kind', ['harness', 'embedding'])
@pytest.mark.parametrize('status,location', [(307, 'https://model.example/sink'), (308, 'https://other.example/sink')])
def test_direct_sdk_stops_redirect_and_has_finite_timeout(kind, status, location, settings, monkeypatch):
    calls = intercept_redirect(monkeypatch, location, status)
    client = harness.AgentHarness(1).client if kind == 'harness' else EmbeddingService()._remote_client()
    try:
        with pytest.raises(APIStatusError):
            if kind == 'harness':
                client.chat.completions.create(model=settings.model, messages=[{'role': 'user', 'content': 'synthetic'}])
            else:
                client.embeddings.create(model='synthetic-embedding', input=['synthetic'])
        assert len(calls) == 1
        assert calls[0].extensions['timeout']['read'] == (7.0 if kind == 'harness' else 30.0)
    finally:
        client.close()
