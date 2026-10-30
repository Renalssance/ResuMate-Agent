"""Durable parsing: stable accepted input, replay and atomic business writes."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backend.auth.security import get_current_user
from backend.db.agent_models import AgentRun, AgentRunEvent, ToolOperation
from backend.db.database import get_db
from backend.db.models import JobDescription, Resume
from backend.rag.mysql import DocumentEmbeddingChunk, MySQLRagStore
from backend.routes import documents
from backend.services import background_tasks
from backend.services.documents import store_upload
from backend.tests.career_fixtures import career_db, career_engine


@pytest.fixture
def parse_app(career_db, career_engine, tmp_path, monkeypatch):
    factory = sessionmaker(career_engine, expire_on_commit=False)
    monkeypatch.setattr(background_tasks, 'publish_run', lambda *args: False, raising=False)
    monkeypatch.setattr(documents, 'get_rag_store', lambda: SimpleNamespace(replace_document_chunks=lambda **kw: None))
    async def isolated_upload(file):
        return await store_upload(file, storage_root=tmp_path / 'originals')
    monkeypatch.setattr(documents, 'store_upload', isolated_upload)
    app = FastAPI()
    app.include_router(documents.router)
    app.include_router(documents.followup_router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    def request_db():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = request_db
    with TestClient(app) as client:
        yield client, factory, tmp_path / 'originals'


def upload(client, request_id='upload-one'):
    return client.post('/api/documents', data={'document_type': 'resume', 'task_id': request_id},
        files={'files': ('resume.txt', b'Candidate resume source with enough readable content.')},
        headers={'Prefer': 'respond-async'})


def test_upload_accepts_one_pending_document_and_persistent_run_before_work(parse_app):
    client, factory, originals = parse_app
    response = upload(client)
    assert response.status_code == 202
    run_id = response.json()['taskId']
    assert run_id != 'upload-one'
    with factory() as db:
        run = db.get(AgentRun, run_id)
        assert run is not None and run.status == 'queued'
        row = db.get(Resume, int(run.input_json['documentId'].split(':')[1]))
        assert row.parse_status == 'pending' and row.structured_data == {}
        assert row.file_path and len(list(originals.iterdir())) == 1
        assert db.scalar(select(AgentRunEvent).where(AgentRunEvent.run_id == run_id)).type == 'run.status'
    duplicate = upload(client)
    assert duplicate.json() == response.json()
    assert len(list(originals.iterdir())) == 1
    with factory() as db:
        assert db.query(Resume).count() == 2  # seeded resume plus one accepted upload
        assert db.query(AgentRun).count() == 1


def execute(factory, run_id, monkeypatch, parse=None, rag=None):
    from backend.services import document_tasks
    from backend.services.agent_runs import claim_run
    monkeypatch.setattr(document_tasks, 'SessionLocal', factory)
    monkeypatch.setattr(document_tasks, '_parse_profile', parse or (lambda *a, **kw: {'candidate_name': 'Ada'}))
    monkeypatch.setattr(document_tasks, 'get_rag_store', lambda: rag or SimpleNamespace(replace_document_chunks=lambda **kw: None))
    with factory() as db:
        epoch = claim_run(db, run_id)
    assert epoch is not None
    document_tasks.run_document_parse(run_id, epoch)
    return document_tasks, epoch


def test_uploaded_document_replay_keeps_one_identity_result_and_operation(parse_app, monkeypatch):
    client, factory, originals = parse_app
    run_id = upload(client).json()['taskId']
    calls = []
    tasks, epoch = execute(factory, run_id, monkeypatch, parse=lambda *a, **kw: calls.append(1) or {'candidate_name': 'Ada'})
    with factory() as db:
        run = db.get(AgentRun, run_id)
        assert run.status == 'succeeded'
        result = run.result_json
        assert result['taskId'] == run_id
        assert result['documents'][0]['parse_status'] == 'success'
        assert db.query(ToolOperation).filter_by(run_id=run_id).one().operation_key == 'parse:' + run.input_json['documentId']
        assert db.query(AgentRunEvent).filter_by(run_id=run_id, type='artifact.created').count() == 1
    tasks.run_document_parse(run_id, epoch)
    with factory() as db:
        assert db.get(AgentRun, run_id).result_json == result
        assert db.query(Resume).count() == 2
        assert db.query(ToolOperation).filter_by(run_id=run_id).count() == 1
    assert calls == [1] and len(list(originals.iterdir())) == 1


def test_accepted_failure_keeps_original_and_document_for_retry(parse_app, monkeypatch):
    client, factory, originals = parse_app
    run_id = upload(client).json()['taskId']
    def fail(*a, **kw):
        raise ValueError('profile extraction failed')
    execute(factory, run_id, monkeypatch, parse=fail)
    with factory() as db:
        run = db.get(AgentRun, run_id)
        row = db.get(Resume, int(run.input_json['documentId'].split(':')[1]))
        assert run.status == 'failed' and row.parse_status == 'failed'
        assert row.structured_data == {} and run.result_json is None
        assert db.query(ToolOperation).filter_by(run_id=run_id).count() == 0
    assert len(list(originals.iterdir())) == 1
    from backend.services.agent_runs import retry_run
    with factory() as db:
        retry_run(db, 1, run_id)
    execute(factory, run_id, monkeypatch)
    with factory() as db:
        assert db.get(AgentRun, run_id).status == 'succeeded'
        assert db.query(Resume).count() == 2
        assert db.query(ToolOperation).filter_by(run_id=run_id).count() == 1


@pytest.mark.parametrize('mutation', ['delete', 'reassign', 'cancel'])
def test_changed_source_or_cancel_after_model_never_indexes_or_writes(parse_app, monkeypatch, mutation):
    client, factory, originals = parse_app
    run_id = upload(client).json()['taskId']
    indexed = []
    def parse(*a, **kw):
        from backend.services.agent_runs import cancel_run
        with factory() as db:
            run = db.get(AgentRun, run_id)
            row = db.get(Resume, int(run.input_json['documentId'].split(':')[1]))
            if mutation == 'delete':
                db.delete(row)
            elif mutation == 'reassign':
                row.user_id = 2
            else:
                cancel_run(db, 1, run_id)
            db.commit()
        return {'candidate_name': 'Ada'}
    execute(factory, run_id, monkeypatch, parse=parse,
        rag=SimpleNamespace(replace_document_chunks=lambda **kw: indexed.append(kw)))
    with factory() as db:
        run = db.get(AgentRun, run_id)
        assert run.status == ('cancelled' if mutation == 'cancel' else 'failed')
        assert run.result_json is None
        assert db.query(ToolOperation).filter_by(run_id=run_id).count() == 0
        row = db.get(Resume, int(run.input_json['documentId'].split(':')[1]))
        if row:
            assert row.structured_data == {}
    assert indexed == []


def test_parse_business_result_operation_event_and_success_rollback_together(parse_app, monkeypatch):
    client, factory, originals = parse_app
    run_id = upload(client).json()['taskId']
    from backend.services import document_tasks
    original = document_tasks.append_event
    def fail_artifact(db, run_id, event_type, payload):
        if event_type == 'artifact.created':
            raise RuntimeError('artifact transaction failure')
        return original(db, run_id, event_type, payload)
    monkeypatch.setattr(document_tasks, 'append_event', fail_artifact)
    execute(factory, run_id, monkeypatch)
    with factory() as db:
        run = db.get(AgentRun, run_id)
        row = db.get(Resume, int(run.input_json['documentId'].split(':')[1]))
        assert run.status == 'failed' and run.result_json is None
        assert row.structured_data == {} and row.raw_text == ''
        assert db.query(ToolOperation).filter_by(run_id=run_id).count() == 0
        assert db.query(AgentRunEvent).filter_by(run_id=run_id, type='artifact.created').count() == 0


def test_saved_job_parse_keeps_result_shape_and_updates_timestamp(parse_app, monkeypatch):
    client, factory, originals = parse_app
    response = client.post('/api/documents/jd:1/parse', headers={'Prefer': 'respond-async'})
    run_id = response.json()['taskId']
    indexed = []
    with factory() as db:
        from datetime import datetime
        db.get(JobDescription, 1).updated_at = datetime(2026, 1, 1)
        db.commit()
        previous = db.get(JobDescription, 1).updated_at
    execute(factory, run_id, monkeypatch, parse=lambda *a, **kw: {'job_title': 'New role'},
        rag=SimpleNamespace(replace_document_chunks=lambda **kw: indexed.append(kw)))
    with factory() as db:
        run = db.get(AgentRun, run_id)
        row = db.get(JobDescription, 1)
        assert run.result_json['id'] == 'jd:1' and run.result_json['vectorized'] is False
        assert row.raw_text == 'Build APIs' and row.updated_at > previous
    assert indexed == []


@pytest.mark.parametrize('backend', ['mysql', 'chroma'])
@pytest.mark.parametrize('mutation', ['delete', 'cancel'])
def test_source_changed_during_embedding_cannot_write_index(parse_app, monkeypatch, tmp_path, backend, mutation):
    from backend.rag.mysql import MySQLRagStore, DocumentEmbeddingChunk
    from backend.rag.chroma import ChromaRagStore
    from backend.services.agent_runs import cancel_run
    client, factory, originals = parse_app
    run_id = upload(client).json()['taskId']
    class Embeddings:
        contract = {'provider': 'test', 'model': 'deterministic'}
        def embed_many(self, texts):
            with factory() as db:
                run = db.get(AgentRun, run_id)
                if mutation == 'cancel':
                    cancel_run(db, 1, run_id)
                else:
                    db.delete(db.get(Resume, int(run.input_json['documentId'].split(':')[1])))
                    db.commit()
            return [[1.0, 0.0] for _ in texts]
    rag = (MySQLRagStore(session_factory=factory, embedding_client=Embeddings()) if backend == 'mysql'
        else ChromaRagStore(path=tmp_path / 'chroma', embedding_client=Embeddings()))
    execute(factory, run_id, monkeypatch, rag=rag)
    with factory() as db:
        assert db.get(AgentRun, run_id).status == ('cancelled' if mutation == 'cancel' else 'failed')
        assert db.get(AgentRun, run_id).result_json is None
        if backend == 'mysql':
            assert db.query(DocumentEmbeddingChunk).count() == 0
        else:
            assert rag.collection.count() == 0


def test_new_file_reparse_advances_timestamp_and_preserves_old_upload_response(parse_app, monkeypatch):
    from datetime import datetime
    client, factory, originals = parse_app
    run_id = upload(client).json()['taskId']
    execute(factory, run_id, monkeypatch)
    with factory() as db:
        original = db.get(AgentRun, run_id).result_json
        document_id = original['documents'][0]['id']
        db.get(Resume, int(document_id.split(':')[1])).updated_at = datetime(2026, 1, 1)
        db.commit()
    response = client.post('/api/documents/' + document_id + '/parse', headers={'Prefer': 'respond-async'})
    execute(factory, response.json()['taskId'], monkeypatch, parse=lambda *args, **kwargs: {'candidate_name': 'Grace'})
    with factory() as db:
        row = db.get(Resume, int(document_id.split(':')[1]))
        assert row.updated_at > datetime(2026, 1, 1) and row.structured_data['candidate_name'] == 'Grace'
        assert db.get(AgentRun, run_id).result_json == original
    replay = client.post('/api/documents', data={'document_type': 'resume', 'task_id': 'upload-one'},
        files={'files': ('unused.txt', b'This duplicate request must not create a source.')})
    assert replay.status_code == 200 and replay.json() == original
    assert len(list(originals.iterdir())) == 1
