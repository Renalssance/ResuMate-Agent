"""Admission-boundary tests; controlled decisions do not simulate Redis atomicity."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.middleware import rate_limit
from backend.routes import api, agent_runs, chat, documents


ACCEPTANCES = [
    ('/api/agent/runs', {'json': {'kind': 'tailoring', 'jdId': 1, 'resumeId': 1, 'requestId': 'same-request'}}),
    ('/api/agent/runs/run-1/retry', {}),
    ('/api/documents', {'data': {'document_type': 'resume'}, 'files': {'files': ('resume.txt', b'Synthetic resume')}}),
    ('/api/documents/resume:1/parse', {}),
    ('/api/jobs/1/parse', {}),
    ('/api/runs', {'json': {'jd_document_id': 'jd:1', 'resume_document_ids': ['resume:1']}}),
    ('/api/runs/1/candidates/1/questions', {}),
    ('/api/followups/analyze', {'json': {'question': 'Describe the work', 'answer': 'Synthetic answer'}}),
    ('/api/resume-versions/version-1/export', {'json': {'requestId': 'export-one'}}),
]


def app_with_routes():
    app = FastAPI()
    app.include_router(api.router)
    user_calls, db_calls = [], []
    def user():
        user_calls.append(1)
        return SimpleNamespace(id=7, username='sql-user')
    def db():
        db_calls.append(1)
        return object()  # Any handler reaching SQL will fail instead of writing real data.
    app.dependency_overrides[get_current_user] = user
    app.dependency_overrides[get_db] = db
    return app, user_calls, db_calls


def require_capacity():
    assert hasattr(rate_limit, 'require_run_capacity'), 'Run admission dependency is required'
    return rate_limit.require_run_capacity


def test_local_app_reuses_original_auth_override_without_bearer(controlled_rate_limiter):
    app = FastAPI()
    calls = []
    def user():
        calls.append(1)
        return SimpleNamespace(id=7)
    app.dependency_overrides[get_current_user] = user
    @app.post('/probe', dependencies=[Depends(require_capacity())])
    def probe(current=Depends(get_current_user)):
        return {'user': current.id}
    response = TestClient(app).post('/probe')
    assert response.status_code == 200 and response.json() == {'user': 7}
    assert controlled_rate_limiter.calls == [(7, 'run')]
    assert calls == [1]


@pytest.mark.parametrize('status', [429, 503])
@pytest.mark.parametrize(('path', 'request_kwargs'), ACCEPTANCES)
def test_nine_acceptance_routes_reject_before_files_or_sql(path, request_kwargs, status, controlled_rate_limiter, monkeypatch):
    if status == 429:
        controlled_rate_limiter.result = (False, 12)
    else:
        from backend.infrastructure.redis_client import RedisUnavailable
        controlled_rate_limiter.error = RedisUnavailable('unavailable')
    writes = []
    async def upload(*args):
        writes.append('file')
        raise AssertionError('Admission must run before file storage')
    monkeypatch.setattr(documents, 'store_upload', upload)
    app, user_calls, db_calls = app_with_routes()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(path, **request_kwargs)
    assert response.status_code == status, response.text
    assert controlled_rate_limiter.calls == [(7, 'run')]
    assert user_calls == [1] and db_calls == [] and writes == []
    if status == 429:
        assert response.headers['Retry-After'] == '12'
    if path.startswith(('/api/agent/runs', '/api/resume-versions')):
        assert response.json()['code'] == ('rate_limited' if status == 429 else 'dependency_unavailable')
        assert response.json()['requestId']
    else:
        assert set(response.json()) == {'detail'}


def test_missing_auth_is_still_401_and_does_not_consume_limit(controlled_rate_limiter):
    app, _, _ = app_with_routes()
    app.dependency_overrides.pop(get_current_user)
    response = TestClient(app).post('/api/agent/runs', json=ACCEPTANCES[0][1]['json'])
    assert response.status_code == 401
    assert controlled_rate_limiter.calls == []


def test_auth_login_and_register_share_ip_even_with_optional_bearer(controlled_rate_limiter):
    controlled_rate_limiter.result = (False, 9)
    app, _, db_calls = app_with_routes()
    client = TestClient(app, raise_server_exceptions=False)
    for path in ['/auth/login', '/auth/register']:
        response = client.post(path, json={'username': 'alice', 'password': 'synthetic-password'},
            headers={'X-Forwarded-For': '203.0.113.7, 127.0.0.1', 'Authorization': 'Bearer ignored-on-auth'})
        assert response.status_code == 429
        assert response.headers['Retry-After'] == '9'
    assert controlled_rate_limiter.calls == [('ip:203.0.113.7', 'auth')] * 2
    assert db_calls == []


def test_chat_uses_sql_confirmed_numeric_user(controlled_rate_limiter, monkeypatch):
    async def model_trap(*args):
        raise AssertionError('Rejected chat must not reach an Agent/model')
        yield ''
    monkeypatch.setattr(chat, 'chat_with_agent_stream', model_trap)
    controlled_rate_limiter.result = (False, 4)
    app, user_calls, _ = app_with_routes()
    response = TestClient(app, raise_server_exceptions=False).post('/chat/stream', json={'message': 'hello'})
    assert response.status_code == 429
    assert controlled_rate_limiter.calls == [(7, 'chat')]
    assert user_calls == [1]


def test_accepted_replays_each_count_and_snapshot_cancel_actions_remain_available(controlled_rate_limiter, monkeypatch):
    app, _, _ = app_with_routes()
    queued = SimpleNamespace(id='existing-run', status='queued')
    monkeypatch.setattr(agent_runs.agent_runs, 'create_run', lambda *args: queued)
    monkeypatch.setattr(agent_runs, 'publish_run', lambda run_id: False)
    monkeypatch.setattr(agent_runs.agent_runs, 'run_snapshot', lambda *args: {'runId': queued.id, 'status': 'queued'})
    monkeypatch.setattr(agent_runs.agent_runs, 'cancel_run', lambda *args: SimpleNamespace(id=queued.id, status='cancelled'))
    monkeypatch.setattr(agent_runs.agent_runs, 'answer_action', lambda *args: queued)
    client = TestClient(app)
    for _ in range(2):
        response = client.post('/api/agent/runs', **ACCEPTANCES[0][1])
        assert response.status_code == 202 and response.json()['runId'] == queued.id
    assert controlled_rate_limiter.calls == [(7, 'run')] * 2
    from backend.infrastructure.redis_client import RedisUnavailable
    controlled_rate_limiter.error = RedisUnavailable('down')
    assert client.get('/api/agent/runs/existing-run').status_code == 200
    assert client.post('/api/agent/runs/existing-run/cancel').status_code == 202
    assert client.post('/api/agent/runs/existing-run/actions/action-1', json={'decision': 'submit', 'answers': {}, 'expectedRevision': 1}).status_code == 202
    assert controlled_rate_limiter.calls == [(7, 'run')] * 2


@pytest.mark.real_redis
def test_missing_app_state_never_allows_and_runtime_getter_reads_current_app_state():
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7)
    @app.post('/probe', dependencies=[Depends(require_capacity())])
    def probe():
        return {'ok': True}
    client = TestClient(app)
    assert client.post('/probe').status_code == 503
    first = SimpleNamespace(allow_request=AsyncMock(return_value=(True, 0)))
    app.state.rate_limiter = first
    assert client.post('/probe').status_code == 200
    second = SimpleNamespace(allow_request=AsyncMock(return_value=(False, 3)))
    app.state.rate_limiter = second
    assert client.post('/probe').status_code == 429
    first.allow_request.assert_awaited_once_with(7, 'run')
    second.allow_request.assert_awaited_once_with(7, 'run')
