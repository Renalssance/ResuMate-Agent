"""Workspace reads use persisted runs/artifacts and the real authentication boundary."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, event
from sqlalchemy.orm import Session

from backend.app import app
from backend.auth.security import create_access_token
from backend.db.agent_models import AgentRun, AgentSession
from backend.db.career_models import ResumeVersion
from backend.db.database import get_db
from backend.db.models import JobDescription, Resume
from backend.tests.career_fixtures import career_engine, career_db


@pytest.fixture
def workspace_client(career_db, career_engine):
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


def seed_run(db, run_id, *, owner=1, created_at=datetime(2026, 10, 29, 10), **extra):
    session_id = 'session-' + run_id
    db.add(AgentSession(id=session_id, user_id=owner, purpose='tailoring'))
    db.flush()
    run = AgentRun(id=run_id, session_id=session_id, user_id=owner,
                   request_id='request-' + run_id, kind='tailoring',
                   input_json={'resumeId': 1, 'jdId': 1},
                   input_versions={'resume': db.get(Resume, 1).updated_at.replace(tzinfo=None).isoformat(),
                                   'jd': db.get(JobDescription, 1).updated_at.replace(tzinfo=None).isoformat(), 'facts': []},
                   created_at=created_at, updated_at=created_at, **extra)
    db.add(run)
    db.commit()
    return run


def test_list_paginates_owned_runs_with_stable_creation_order(workspace_client, career_db):
    seed_run(career_db, 'run-a', status='failed', error_code='model_timeout')
    seed_run(career_db, 'run-c')
    seed_run(career_db, 'run-b')
    seed_run(career_db, 'run-new', created_at=datetime(2026, 10, 29, 11))
    seed_run(career_db, 'run-foreign', owner=2, created_at=datetime(2026, 10, 29, 12))
    first = workspace_client.get('/api/agent/runs?limit=2', headers=headers())
    assert first.status_code == 200
    assert [r['runId'] for r in first.json()['items']] == ['run-new', 'run-c']
    assert first.json()['hasMore'] is True
    second = workspace_client.get('/api/agent/runs?limit=2&offset=2', headers=headers()).json()
    assert [r['runId'] for r in second['items']] == ['run-b', 'run-a']
    assert second['hasMore'] is False
    assert second['items'][1] == {
        'runId': 'run-a', 'sessionId': 'session-run-a', 'kind': 'tailoring',
        'status': 'failed', 'createdAt': '2026-10-29T10:00:00+00:00',
        'updatedAt': '2026-10-29T10:00:00+00:00', 'input': {'resumeId': 1, 'jdId': 1},
        'errorCode': 'model_timeout',
    }
    assert workspace_client.get('/api/agent/runs?offset=4', headers=headers()).json() == {
        'items': [], 'hasMore': False,
    }
    bob = workspace_client.get('/api/agent/runs', headers=headers('bob')).json()
    assert [r['runId'] for r in bob['items']] == ['run-foreign']


def test_list_keeps_historical_input_after_source_deletion(workspace_client, career_db):
    seed_run(career_db, 'run-history')
    career_db.execute(delete(Resume).where(Resume.id == 1))
    career_db.execute(delete(JobDescription).where(JobDescription.id == 1))
    career_db.commit()
    response = workspace_client.get('/api/agent/runs', headers=headers())
    assert response.status_code == 200
    assert response.json()['items'][0]['input'] == {'resumeId': 1, 'jdId': 1}


@pytest.mark.parametrize('query', ['limit=0', 'limit=51', 'offset=-1', 'limit=abc'])
def test_list_rejects_invalid_pagination_in_run_error_contract(workspace_client, query):
    response = workspace_client.get('/api/agent/runs?' + query, headers=headers())
    assert response.status_code == 422
    assert response.json()['code'] == 'invalid_request'
    assert response.json()['requestId']


@pytest.mark.parametrize('path', ['/api/agent/runs', '/api/agent/runs/missing/artifacts'])
def test_workspace_reads_require_bearer_auth(workspace_client, path):
    response = workspace_client.get(path)
    assert response.status_code == 401
    assert response.json()['code'] == 'unauthorized'
    assert response.headers['www-authenticate'] == 'Bearer'
    assert response.json()['requestId']


def test_artifacts_include_owned_drafts_before_run_finishes(workspace_client, career_db):
    seed_run(career_db, 'run-draft', status='running', output_refs=[])
    seed_run(career_db, 'run-other')
    career_db.add_all([
        ResumeVersion(id='draft', user_id=1, run_id='run-draft', resume_id=1, jd_id=1,
                      structured_content={'summary': 'API development'}, fact_refs=['fact-1'],
                      revision=2, status='draft', created_at=datetime(2026, 10, 29, 11)),
        ResumeVersion(id='foreign', user_id=2, run_id='run-draft', structured_content={'private': 'Bob'}),
        ResumeVersion(id='other-run', user_id=1, run_id='run-other'),
    ])
    career_db.commit()
    response = workspace_client.get('/api/agent/runs/run-draft/artifacts', headers=headers())
    assert response.status_code == 200
    assert response.json() == [{
        'kind': 'resume_version', 'id': 'draft', 'runId': 'run-draft', 'resumeId': 1, 'jdId': 1, 'revision': 2,
        'status': 'draft', 'structuredContent': {'summary': 'API development'},
        'factRefs': ['fact-1'], 'createdAt': '2026-10-29T11:00:00+00:00',
        'basedOnOldInput': False, 'changedInputs': [], 'sources': [], 'reviewable': False,
    }]
    career_db.execute(delete(Resume).where(Resume.id == 1))
    career_db.execute(delete(JobDescription).where(JobDescription.id == 1))
    career_db.commit()
    historical = workspace_client.get('/api/agent/runs/run-draft/artifacts', headers=headers()).json()
    assert historical[0]['resumeId'] is None and historical[0]['jdId'] is None
    assert historical[0]['structuredContent'] == {'summary': 'API development'}


def test_artifacts_unknown_and_cross_owner_are_not_found(workspace_client, career_db):
    seed_run(career_db, 'run-owned')
    assert workspace_client.get('/api/agent/runs/run-owned/artifacts', headers=headers()).json() == []
    for run_id, user in [('run-owned', 'bob'), ('missing', 'alice')]:
        response = workspace_client.get(f'/api/agent/runs/{run_id}/artifacts', headers=headers(user))
        assert response.status_code == 404
        assert response.json()['code'] == 'not_found'
        assert response.json()['requestId']


def test_workspace_reads_use_bounded_queries(workspace_client, career_db, career_engine):
    seed_run(career_db, 'run-many')
    for n in range(5):
        seed_run(career_db, f'run-{n}')
        career_db.add(ResumeVersion(id=f'version-{n}', user_id=1, run_id='run-many'))
    career_db.commit()
    selects = []
    def record_select(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith('SELECT'):
            selects.append(statement)
    event.listen(career_engine, 'before_cursor_execute', record_select)
    try:
        listing = workspace_client.get('/api/agent/runs', headers=headers())
        assert listing.status_code == 200 and len(listing.json()['items']) == 6
        assert len(selects) == 2  # Authentication plus one paginated query.
        selects.clear()
        artifacts = workspace_client.get('/api/agent/runs/run-many/artifacts', headers=headers())
        assert artifacts.status_code == 200 and len(artifacts.json()) == 5
        assert len(selects) <= 6  # Auth, Run, versions, and one shared current-input comparison.
    finally:
        event.remove(career_engine, 'before_cursor_execute', record_select)
