import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.auth.security import create_access_token
from backend.db.database import get_db
from backend.routes import tasks
from backend.schemas.agent_runs import RunCreate, RunStatus
from backend.services import agent_runs, progress
from backend.tests.career_fixtures import career_db, career_engine
from backend.tests.test_long_task_core import followup_request


@pytest.fixture
def task_client(career_db, career_engine):
    app = FastAPI()
    app.include_router(tasks.router)
    def request_db():
        with Session(career_engine, autoflush=False, expire_on_commit=False) as db:
            yield db
    app.dependency_overrides[get_db] = request_db
    with TestClient(app) as client:
        yield client


def headers(username='alice'):
    return {'Authorization': f'Bearer {create_access_token(username, "user")}'}


def test_legacy_task_events_require_token_and_sql_owner_before_streaming(task_client, career_db):
    run_id = agent_runs.create_run(career_db, 1, followup_request()).id
    epoch = agent_runs.claim_run(career_db, run_id)
    agent_runs.finish_run(career_db, run_id, epoch, RunStatus.SUCCEEDED, result_json={'follow_up': '私有回答'})
    url = f'/api/tasks/{run_id}/events'
    assert task_client.get(url).status_code == 401
    assert task_client.get(url, headers=headers('bob')).status_code == 404
    assert task_client.get('/api/tasks/unknown/events', headers=headers()).status_code == 404
    response = task_client.get(url, headers=headers())
    assert response.status_code == 200
    assert '"follow_up":"私有回答"' in response.text
    assert '"status":"success"' in response.text
    assert 'id: 3\ndata: ' in response.text
    assert 'data: ' not in task_client.get(url, headers={**headers(), 'Last-Event-ID': '3'}).text
    assert task_client.get(url + '?after=99', headers=headers()).status_code == 409


def test_legacy_stream_closes_auth_session_before_yielding(task_client, career_db, career_engine, monkeypatch):
    run_id = agent_runs.create_run(career_db, 1, followup_request()).id
    career_db.close()
    checked_out = []
    async def finite_stream(factory, user_id, task_id, after):
        checked_out.append(career_engine.pool.checkedout())
        yield ': connected\n\n'
        checked_out.append(career_engine.pool.checkedout())
    monkeypatch.setattr(tasks.run_events, 'stream_task_events', finite_stream)
    response = task_client.get(f'/api/tasks/{run_id}/events', headers=headers())
    assert response.status_code == 200 and checked_out == [0, 0]


@pytest.mark.parametrize('mode,result,expected_key', [
    ('upload', {'documents': [{'id': 'resume:1', 'filename': '原件.txt'}], 'taskId': 'saved'}, 'documents'),
    ('reparse', {'id': 'resume:1', 'filename': '原件.txt'}, 'document'),
    ('saved_job', {'id': 'jd:1', 'vectorized': False}, 'document'),
])
def test_legacy_terminal_projection_preserves_document_result_shape(task_client, career_db, mode, result, expected_key):
    document_id = 'jd:1' if mode == 'saved_job' else 'resume:1'
    run_id = agent_runs.create_run(career_db, 1, RunCreate(kind='document_parse', documentId=document_id,
        parseMode=mode, requestId='shape')).id
    epoch = agent_runs.claim_run(career_db, run_id)
    progress.append_progress(career_db, run_id, epoch, stage='extract', progress=50, message='处理')
    agent_runs.finish_run(career_db, run_id, epoch, RunStatus.SUCCEEDED, result_json=result)
    response = task_client.get(f'/api/tasks/{run_id}/events?after=2', headers=headers())
    frames = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert [frame['status'] for frame in frames] == ['running', 'success']
    assert frames[-1]['data'][expected_key] == (result['documents'] if mode == 'upload' else result)
    assert 'id: 3\ndata: ' in response.text and 'id: 4\ndata: ' in response.text


def test_cancelled_legacy_stream_is_terminal_failed_with_cancelled_stage(task_client, career_db):
    run_id = agent_runs.create_run(career_db, 1, followup_request()).id
    agent_runs.cancel_run(career_db, 1, run_id)
    response = task_client.get(f'/api/tasks/{run_id}/events', headers=headers())
    terminal = json.loads(next(line[6:] for line in response.text.splitlines() if line.startswith('data: ')))
    assert terminal['status'] == 'failed' and terminal['stage'] == 'cancelled'
    assert terminal['message'] == '任务已取消' and terminal['data']['code'] == 'cancelled'
