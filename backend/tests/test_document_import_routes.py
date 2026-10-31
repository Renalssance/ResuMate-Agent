from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.db.agent_models import AgentRun, AgentRunEvent, AgentSession
from backend.db.models import JobDescription, Resume
from backend.routes import agent_runs, documents
from backend.tests.career_fixtures import career_db, career_engine
from backend.tests.test_document_cloud_routes import cloud_original
from backend.tests.test_document_tasks import parse_app, upload


def post_import(client, request_id='import-one'):
    return client.post('/api/documents/import', data={'requestId': request_id},
        files={'file': ('profile.txt', b'Education\nWork Experience\nProjects', 'text/plain')})


def test_import_accepts_one_file_without_document_type(parse_app, monkeypatch):
    client, factory, originals = parse_app
    client.app.include_router(agent_runs.router)
    published = []
    def publish(run_id):
        with factory() as db:
            assert db.get(AgentRun, run_id).status == 'queued'
        published.append(run_id)
    monkeypatch.setattr(documents, 'publish_run', publish, raising=False)

    response = post_import(client)
    assert response.status_code == 202
    body = response.json()
    assert body['status'] == 'queued' and published == [body['runId']]
    run_id = body['runId']
    snapshot = client.get(f'/api/agent/runs/{run_id}').json()
    assert snapshot['kind'] == 'document_import'
    assert snapshot['input'] == {'filename': 'profile.txt'}
    assert client.get('/api/agent/runs').json()['items'][0]['input'] == {'filename': 'profile.txt'}
    assert client.get(f'/api/agent/runs/{run_id}/artifacts').json() == []
    with factory() as db:
        run = db.get(AgentRun, run_id)
        assert Path(run.input_json['sourcePath']).read_bytes() == b'Education\nWork Experience\nProjects'
        assert run.input_json['documentSize'] == 34
        assert run.input_versions == {}
        session = db.get(AgentSession, run.session_id)
        assert session.purpose == 'document_import' and session.active_run_id == run.id
        event = db.scalar(select(AgentRunEvent).where(AgentRunEvent.run_id == run.id))
        assert event.type == 'run.status' and event.payload['status'] == 'queued'
        assert db.query(Resume).count() == db.query(JobDescription).count() == 1
    assert len(list(originals.iterdir())) == 1


def test_import_request_id_reuses_run_and_does_not_store_second_original(parse_app, monkeypatch):
    client, factory, originals = parse_app
    monkeypatch.setattr(documents, 'publish_run', lambda run_id: False, raising=False)
    first = post_import(client)
    second = post_import(client)
    assert first.status_code == second.status_code == 202
    assert second.json() == first.json()
    assert len(list(originals.iterdir())) == 1
    with factory() as db:
        assert db.query(AgentRun).count() == db.query(AgentSession).count() == 1


def test_import_rejects_multiple_files(parse_app):
    client, factory, originals = parse_app
    response = client.post('/api/documents/import', files=[
        ('file', ('a.txt', b'a', 'text/plain')),
        ('file', ('b.txt', b'b', 'text/plain')),
    ])
    assert response.status_code == 422
    assert not originals.exists()


def test_import_rejects_empty_file_without_run_or_original(parse_app):
    client, factory, originals = parse_app
    with TestClient(client.app, raise_server_exceptions=False) as request_client:
        response = request_client.post('/api/documents/import',
            files={'file': ('empty.txt', b'', 'text/plain')})
    assert response.status_code == 400
    assert 'empty' in response.json()['detail']
    with factory() as db:
        assert db.query(AgentRun).count() == db.query(AgentSession).count() == 0
    assert list(originals.iterdir()) == []


def test_import_request_id_conflict_does_not_store_an_original(parse_app):
    client, factory, originals = parse_app
    assert upload(client, request_id='other-kind').status_code == 202
    response = post_import(client, request_id='other-kind')
    assert response.status_code == 409
    assert len(list(originals.iterdir())) == 1
    with factory() as db:
        assert db.query(AgentRun).count() == 1


def test_import_preaccept_failure_removes_cloud_original_and_cache(parse_app, cloud_original, monkeypatch):
    client, factory, originals = parse_app
    scratch, reference, downloads, deleted = cloud_original
    def fail(*args, **kwargs):
        raise documents.RunError(409, 'session_busy', 'session busy')
    monkeypatch.setattr(documents, 'create_document_import_run', fail, raising=False)
    response = post_import(client)
    assert response.status_code == 409
    assert not scratch.exists() and deleted == [reference]
    with factory() as db:
        assert db.query(AgentRun).count() == db.query(AgentSession).count() == 0
