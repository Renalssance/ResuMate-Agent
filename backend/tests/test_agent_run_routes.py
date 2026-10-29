from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app import app
from backend.auth.security import create_access_token
from backend.db.database import get_db
from backend.db.models import Resume
from backend.db.agent_models import AgentRun, AgentSession
from backend.tests.career_fixtures import career_engine, career_db


@pytest.fixture
def run_client(career_db, career_engine):
    def get_test_db():
        with Session(career_engine, autoflush=False, expire_on_commit=False) as db:
            yield db
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = get_test_db
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def headers(user='alice'):
    return {'Authorization': 'Bearer ' + create_access_token(username=user, role='user')}


def create(client, **extra):
    return client.post('/api/agent/runs', headers=headers(), json={
        'kind': 'tailoring', 'jdId': 1, 'resumeId': 1, 'requestId': 'req-1', **extra,
    })


def test_create_returns_durable_queued_run_and_snapshot(run_client, career_db):
    response = create(run_client)
    assert response.status_code == 202
    data = response.json()
    assert data['status'] == 'queued'
    career_db.expire_all()
    run = career_db.get(AgentRun, data['runId'])
    assert run.user_id == 1
    snapshot = run_client.get('/api/agent/runs/' + run.id, headers=headers()).json()
    assert snapshot['runId'] == run.id
    assert snapshot['lastSeq'] == 1 and snapshot['actions'] == []
    assert snapshot['input'] == {'jdId': 1, 'resumeId': 1}


def test_duplicate_request_returns_same_run_and_conflicting_reuse_rejected(run_client, career_db):
    first = create(run_client).json()
    second = create(run_client).json()
    assert first == second
    conflict = create(run_client, sessionId='different')
    assert conflict.status_code == 409
    assert conflict.json()['code'] == 'request_conflict'
    assert career_db.query(AgentRun).count() == 1
    assert career_db.query(AgentSession).count() == 1


def test_other_user_cannot_read_cancel_retry_or_use_session(run_client, career_db):
    run_id = create(run_client).json()['runId']
    for method, suffix in [('GET',''), ('POST','/cancel'), ('POST','/retry')]:
        response = run_client.request(method, '/api/agent/runs/' + run_id + suffix, headers=headers('bob'))
        assert response.status_code == 404
        assert response.json()['code'] == 'not_found'
    career_db.expire_all()
    session_id = career_db.get(AgentRun, run_id).session_id
    response = run_client.post('/api/agent/runs', headers=headers('bob'), json={
        'kind':'tailoring','jdId':1,'resumeId':1,'requestId':'bob-1','sessionId':session_id})
    assert response.status_code == 404


def test_authentication_and_body_owner_are_not_bypassable(run_client):
    missing = run_client.post('/api/agent/runs', json={})
    assert missing.status_code == 401
    assert missing.json()['code'] == 'unauthorized'
    assert missing.headers['www-authenticate'] == 'Bearer'
    spoofed = create(run_client, user_id=2)
    assert spoofed.status_code == 422
    assert spoofed.json()['code'] == 'invalid_request'
    assert spoofed.json()['requestId']


def test_foreign_resume_is_rejected(run_client, career_db):
    career_db.add(Resume(id=2,user_id=2,filename='bob.txt'))
    career_db.commit()
    response = create(run_client, resumeId=2)
    assert response.status_code == 404
    assert career_db.query(AgentRun).count() == 0


def test_session_has_one_active_run_and_cancel_releases_it(run_client, career_db):
    run_id = create(run_client).json()['runId']
    career_db.expire_all()
    session_id = career_db.get(AgentRun, run_id).session_id
    assert create(run_client, requestId='req-2', sessionId=session_id).status_code == 409
    cancelled = run_client.post('/api/agent/runs/' + run_id + '/cancel', headers=headers())
    assert cancelled.status_code == 202 and cancelled.json()['status'] == 'cancelled'
    assert run_client.post('/api/agent/runs/' + run_id + '/cancel', headers=headers()).json() == cancelled.json()
    assert create(run_client, requestId='req-2', sessionId=session_id).status_code == 202


def test_running_cancel_sets_request_without_pretending_execution_stopped(run_client, career_db):
    run_id = create(run_client).json()['runId']
    run = career_db.get(AgentRun, run_id)
    run.status = 'running'
    career_db.commit()
    response = run_client.post('/api/agent/runs/' + run_id + '/cancel', headers=headers())
    assert response.json()['status'] == 'running'
    career_db.expire_all()
    assert career_db.get(AgentRun,run_id).cancel_requested_at is not None
    assert career_db.get(AgentSession,run.session_id).active_run_id == run_id


def fail_run(db, run_id):
    db.expire_all()
    run = db.get(AgentRun,run_id)
    run.status = 'failed'
    run.error_code = 'model_timeout'
    db.get(AgentSession,run.session_id).active_run_id = None
    db.commit()


def test_only_failed_run_retries_and_keeps_input_snapshot(run_client, career_db):
    run_id = create(run_client).json()['runId']
    url = '/api/agent/runs/' + run_id + '/retry'
    assert run_client.post(url,headers=headers()).status_code == 409
    fail_run(career_db,run_id)
    assert run_client.post(url,headers=headers()).json()['status'] == 'queued'
    career_db.expire_all()
    run = career_db.get(AgentRun,run_id)
    assert run.attempt == 2 and run.error_code is None
    assert {key: run.input_json[key] for key in ('jdId', 'resumeId')} == {'jdId':1,'resumeId':1}
    assert run.input_json['contextSnapshot']['resume']['id'] == 1
    assert run_client.post(url,headers=headers()).status_code == 409


def test_changed_legacy_input_requires_new_run(run_client, career_db):
    run_id = create(run_client).json()['runId']
    career_db.get(AgentRun,run_id).input_json = {'jdId':1,'resumeId':1}
    career_db.commit()
    fail_run(career_db,run_id)
    resume = career_db.get(Resume,1)
    resume.updated_at += timedelta(seconds=1)
    career_db.commit()
    response = run_client.post('/api/agent/runs/' + run_id + '/retry',headers=headers())
    assert response.status_code == 409
    assert response.json()['code'] == 'input_changed'


def test_concurrent_duplicate_requests_create_one_run(run_client, career_db):
    with ThreadPoolExecutor(max_workers=4) as executor:
        responses = list(executor.map(lambda _: create(run_client), range(4)))
    assert [r.status_code for r in responses] == [202] * 4
    assert len({r.json()['runId'] for r in responses}) == 1
    career_db.expire_all()
    assert career_db.query(AgentRun).count() == 1
    assert career_db.query(AgentSession).count() == 1


def wait_for_input(db, run_id, kind='input'):
    from backend.db.agent_models import AgentAction
    db.expire_all()
    run = db.get(AgentRun, run_id)
    run.status = 'waiting_input' if kind == 'input' else 'waiting_approval'
    db.add(AgentAction(id='action-1', run_id=run_id, interrupt_id='interrupt-1',
                       kind=kind, payload={'field':'project_role'}))
    db.commit()


def test_action_response_is_durable_idempotent_and_conflict_checked(run_client, career_db):
    from backend.db.agent_models import AgentAction
    run_id = create(run_client).json()['runId']
    wait_for_input(career_db,run_id)
    url = '/api/agent/runs/' + run_id + '/actions/action-1'
    body = {'decision':'submit','answers':{'project_role':'backend'},'expectedRevision':1}
    assert run_client.post(url,headers=headers('bob'),json=body).status_code == 404
    assert run_client.post(url,headers=headers(),json={**body,'expectedRevision':2}).status_code == 409
    first = run_client.post(url,headers=headers(),json=body)
    assert first.status_code == 202 and first.json()['status'] == 'queued'
    assert run_client.post(url,headers=headers(),json=body).json() == first.json()
    conflict = run_client.post(url,headers=headers(),json={**body,'answers':{'project_role':'lead'}})
    assert conflict.status_code == 409
    career_db.expire_all()
    assert career_db.get(AgentAction,'action-1').response['answers'] == {'project_role':'backend'}
    assert career_db.get(AgentAction,'action-1').answered_at is not None


def test_rejecting_approval_cancels_run_and_releases_session(run_client, career_db):
    run_id = create(run_client).json()['runId']
    wait_for_input(career_db,run_id,'approval')
    response = run_client.post('/api/agent/runs/' + run_id + '/actions/action-1',headers=headers(),
                               json={'decision':'reject','answers':{},'expectedRevision':1})
    assert response.status_code == 202 and response.json()['status'] == 'cancelled'
    career_db.expire_all()
    run = career_db.get(AgentRun,run_id)
    assert career_db.get(AgentSession,run.session_id).active_run_id is None


def test_concurrent_requests_share_one_session_slot(run_client, career_db):
    first_id = create(run_client).json()['runId']
    career_db.expire_all()
    session_id = career_db.get(AgentRun, first_id).session_id
    run_client.post('/api/agent/runs/' + first_id + '/cancel', headers=headers())
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda n: create(run_client,requestId=f'new-{n}',sessionId=session_id),range(2)))
    assert sorted(r.status_code for r in responses) == [202,409]
    # End the earlier read transaction: MySQL REPEATABLE READ keeps its snapshot.
    career_db.rollback()
    assert career_db.query(AgentRun).count() == 2


def test_cancel_preserves_succeeded_result(run_client, career_db):
    run_id = create(run_client).json()['runId']
    run = career_db.get(AgentRun,run_id)
    run.status = 'succeeded'
    run.output_refs = ['version-1']
    career_db.get(AgentSession,run.session_id).active_run_id = None
    career_db.commit()
    response = run_client.post('/api/agent/runs/' + run_id + '/cancel',headers=headers())
    assert response.json()['status'] == 'succeeded'
    career_db.expire_all()
    assert career_db.get(AgentRun,run_id).output_refs == ['version-1']


def test_answer_cannot_resurrect_task_cancelled_after_read(run_client, career_db, career_engine, monkeypatch):
    if career_engine.dialect.name != 'sqlite':
        pytest.skip('MySQL row lock excludes this SQLite read/write interleaving')
    from backend.services import agent_runs
    from sqlalchemy import update
    run_id = create(run_client).json()['runId']
    wait_for_input(career_db,run_id)
    original_get = agent_runs.get_run

    def read_then_other_tab_cancels(db, user_id, target_id, **kwargs):
        run = original_get(db,user_id,target_id,**kwargs)
        # SQLite ignores FOR UPDATE: another tab can commit between read and write.
        with Session(career_engine) as other:
            other.execute(update(AgentRun).where(AgentRun.id == run_id).values(status='cancelled'))
            other.execute(update(AgentSession).where(AgentSession.id == run.session_id).values(active_run_id=None))
            other.commit()
        return run
    monkeypatch.setattr(agent_runs,'get_run',read_then_other_tab_cancels)
    response = run_client.post('/api/agent/runs/' + run_id + '/actions/action-1',headers=headers(),
                               json={'decision':'submit','answers':{'project_role':'backend'},'expectedRevision':1})
    assert response.status_code == 409
    career_db.rollback()
    assert career_db.get(AgentRun,run_id).status == 'cancelled'


def test_input_action_requires_an_answer(run_client, career_db):
    run_id = create(run_client).json()['runId']
    wait_for_input(career_db,run_id)
    response = run_client.post('/api/agent/runs/' + run_id + '/actions/action-1',headers=headers(),
                               json={'decision':'submit','answers':{},'expectedRevision':1})
    assert response.status_code == 422
