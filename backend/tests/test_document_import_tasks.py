"""Classified imports keep one original and use the existing guarded parser."""
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backend.db.agent_models import AgentAction, AgentRun, AgentRunEvent, ToolOperation
from backend.db.models import JobDescription, Resume
from backend.rag.mysql import DocumentEmbeddingChunk, MySQLRagStore
from backend.schemas.agent_runs import RunStatus
from backend.schemas.document_import import DocumentClassification
from backend.services import agent_runs, document_imports, document_tasks
from backend.services.documents import StoredUpload
from backend.tests.career_fixtures import career_db, career_engine


@pytest.fixture
def import_run(career_db, career_engine, tmp_path, monkeypatch):
    source = tmp_path / 'neutral.txt'
    source.write_text('教育经历\n学校\n工作经历\n公司\n项目经历\n平台', encoding='utf-8')
    factory = sessionmaker(career_engine, expire_on_commit=False)
    monkeypatch.setattr(document_imports, 'SessionLocal', factory, raising=False)
    monkeypatch.setattr(document_tasks, 'SessionLocal', factory)
    monkeypatch.setattr(document_tasks, '_parse_profile', lambda *a, **kw: {'candidate_name': 'Ada'})
    embeddings = SimpleNamespace(contract={'provider': 'test', 'model': 'deterministic'},
                                 embed_many=lambda texts: [[1.0, 0.0] for _ in texts])
    monkeypatch.setattr(document_tasks, 'get_rag_store',
        lambda: MySQLRagStore(session_factory=factory, embedding_client=embeddings))
    run = document_imports.create_document_import_run(career_db, 1,
        StoredUpload(filename='neutral.txt', path=source, size=source.stat().st_size, content_hash=''),
        'import-one')
    career_db.commit()
    agent_runs.claim_run(career_db, run.id)
    career_db.refresh(run)
    return run


@pytest.mark.parametrize('kind', ['resume', 'jd'])
def test_high_confidence_import_adopts_and_parses_same_file(career_db, import_run, monkeypatch, kind):
    from pathlib import Path
    source = Path(import_run.input_json['sourcePath'])
    if kind == 'jd':
        source.write_text('岗位职责\n构建平台\n任职要求\n熟悉 Python', encoding='utf-8')
        monkeypatch.setattr(document_tasks, '_parse_profile', lambda *a, **kw: {'job_title': 'Engineer'})
    monkeypatch.setattr(document_tasks, 'extract_stored_pages',
        lambda *a, **kw: pytest.fail('Import must reuse the classified pages'))

    document_imports.run_document_import(import_run.id, import_run.execution_epoch)

    career_db.expire_all()
    run = career_db.get(AgentRun, import_run.id)
    assert run.status == RunStatus.SUCCEEDED
    document_id = run.input_json['documentId']
    assert document_id.startswith(kind + ':')
    row = career_db.get(Resume if kind == 'resume' else JobDescription, int(document_id.split(':')[1]))
    assert row.file_path == str(source)
    assert row.raw_text == source.read_text(encoding='utf-8')
    assert row.parse_status == 'success'
    assert run.result_json['taskId'] == run.id
    assert run.result_json['documents'][0]['id'] == document_id
    chunks = list(career_db.scalars(select(DocumentEmbeddingChunk).where(
        DocumentEmbeddingChunk.document_id == row.id, DocumentEmbeddingChunk.document_type == kind)))
    assert chunks and all(chunk.filename == 'neutral.txt' and chunk.user_id == 1 for chunk in chunks)
    assert career_db.query(ToolOperation).filter_by(run_id=run.id).one().result_ref == document_id
    assert career_db.query(AgentRunEvent).filter_by(run_id=run.id, type='artifact.created').count() == 1
    monkeypatch.setattr(document_imports, 'extract_stored_pages',
        lambda *a, **kw: pytest.fail('Completed delivery must not extract again'))
    document_imports.run_document_import(run.id, run.execution_epoch)
    career_db.expire_all()
    assert career_db.query(Resume if kind == 'resume' else JobDescription).count() == 2


@pytest.mark.parametrize(('kind', 'confidence'), [('ambiguous', 'high'), ('resume', 'medium')])
def test_uncertain_import_waits_without_adopting(career_db, import_run, monkeypatch, kind, confidence):
    monkeypatch.setattr(document_imports, 'classify_document', lambda *a, **kw: DocumentClassification(
        document_type=kind, confidence=confidence, reason='正文类别不明确'))

    document_imports.run_document_import(import_run.id, import_run.execution_epoch)

    career_db.expire_all()
    run = career_db.get(AgentRun, import_run.id)
    assert run.status == RunStatus.WAITING_INPUT
    assert 'documentId' not in run.input_json
    action = career_db.query(AgentAction).filter_by(run_id=run.id).one()
    assert action.kind == 'input' and action.status == 'pending'
    assert action.payload['filename'] == 'neutral.txt'
    assert action.payload['reason'] == '正文类别不明确'
    assert action.payload['choices'] == [{'value': 'resume', 'label': '简历'}, {'value': 'jd', 'label': '岗位'}]
    assert career_db.query(Resume).count() == career_db.query(JobDescription).count() == 1


def test_failed_import_retries_same_adopted_document(career_db, import_run, monkeypatch):
    def fail_parse(*a, **kw):
        raise ValueError('Model unavailable')
    monkeypatch.setattr(document_tasks, '_parse_profile', fail_parse)
    document_imports.run_document_import(import_run.id, import_run.execution_epoch)
    career_db.expire_all()
    run = career_db.get(AgentRun, import_run.id)
    document_id = run.input_json['documentId']
    row = career_db.get(Resume, int(document_id.split(':')[1]))
    assert run.status == RunStatus.FAILED and row.parse_status == 'failed'
    assert row.structured_data == {} and row.file_path == run.input_json['sourcePath']

    agent_runs.retry_run(career_db, 1, run.id)
    epoch = agent_runs.claim_run(career_db, run.id)
    monkeypatch.setattr(document_imports, 'classify_document',
        lambda *a, **kw: pytest.fail('Retry must preserve the adopted type'))
    monkeypatch.setattr(document_tasks, '_parse_profile', lambda *a, **kw: {'candidate_name': 'Ada'})
    document_imports.run_document_import(run.id, epoch)

    career_db.expire_all()
    run = career_db.get(AgentRun, run.id)
    assert run.status == RunStatus.SUCCEEDED
    assert run.input_json['documentId'] == document_id
    assert career_db.query(Resume).count() == 2


@pytest.mark.parametrize('failure', ['timeout', 'exit'])
def test_worker_import_uses_bounded_child_and_reports_failure(career_db, import_run, monkeypatch, tmp_path, failure):
    import subprocess
    from backend import worker_tasks
    from backend.services import document_process

    import_run.status = RunStatus.QUEUED
    career_db.commit()
    factory = document_imports.SessionLocal
    monkeypatch.setattr(worker_tasks, 'SessionLocal', factory)
    from backend.db import database
    monkeypatch.setattr(database, 'SessionLocal', factory)
    monkeypatch.setenv('AGENT_STATE_DIR', str(tmp_path))
    monkeypatch.setattr(worker_tasks, 'cleanup_invalidated_sessions', lambda: None)
    commands, lifecycle = [], []
    class Child:
        stdin = SimpleNamespace(close=lambda: lifecycle.append('closed'))
        alive = True
        def wait(self, timeout=None):
            if timeout is not None and failure == 'timeout':
                raise subprocess.TimeoutExpired(commands[0], timeout)
            self.alive = False
            lifecycle.append('reaped')
            return 1
        def poll(self):
            return None if self.alive else 1
        def kill(self):
            lifecycle.append('killed')
            self.alive = False
    def start(command, **kwargs):
        commands.append(command)
        return Child()
    monkeypatch.setattr(document_process.subprocess, 'Popen', start)

    worker_tasks.execute_run(import_run.id)

    career_db.expire_all()
    run = career_db.get(AgentRun, import_run.id)
    assert commands and commands[0][-3:] == [run.id, str(run.execution_epoch), 'document_import']
    assert run.status == RunStatus.FAILED
    assert run.error_code == ('document_import_timeout' if failure == 'timeout' else 'document_import_failed')
    assert lifecycle[-2:] == ['reaped', 'closed']
    assert ('killed' in lifecycle) == (failure == 'timeout')
