from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker
from backend.db.agent_models import AgentRun, AgentRunEvent
from backend.db.models import Resume, JobDescription
from backend.schemas.agent_runs import RunCreate
from backend.services import agent_runs
from backend.tests.career_fixtures import career_engine, career_db


def setup_attachment(db, tmp_path):
    source = tmp_path / 'notes.txt'
    source.write_text('This is the attachment content')
    run = agent_runs.create_run(db, 1, RunCreate(kind='chat', message='总结附件', requestId='attachment'))
    run.input_json = {**run.input_json, 'attachment': {'filename': 'notes.txt', 'sourcePath': str(source),
        'contentHash': 'existing-upload-hash', 'size': source.stat().st_size}}
    db.commit()
    return run, agent_runs.claim_run(db, run.id), source


@pytest.fixture
def attachments(career_engine, monkeypatch):
    from backend.services import chat_attachments
    monkeypatch.setattr(chat_attachments, 'SessionLocal', sessionmaker(career_engine, expire_on_commit=False))
    return chat_attachments


def test_duplicate_reuses_owned_document_without_parsing(attachments, career_db, tmp_path, monkeypatch):
    run, epoch, source = setup_attachment(career_db, tmp_path)
    row = career_db.get(Resume, 1)
    row.content_hash = 'existing-upload-hash'
    row.raw_text = 'Saved resume content'
    career_db.commit()
    def forbidden(*args, **kwargs):
        raise AssertionError('Duplicate must not invoke classification')
    monkeypatch.setattr(attachments, 'classify_attachment', forbidden)
    result = attachments.prepare_attachment(run.id, epoch)
    assert result['documentId'] == 'resume:1'
    assert result['text'] == 'Saved resume content'
    assert '资料库中已有文件' in result['notice']
    assert '/documents?document=resume%3A1' in result['notice']
    assert career_db.query(Resume).count() == 1
    assert not source.exists()
    assert attachments.prepare_attachment(run.id, epoch) == result


@pytest.mark.parametrize('kind', ['resume', 'jd', 'other'])
def test_new_attachment_classifies_saves_only_library_types(attachments, career_db, tmp_path, monkeypatch, kind):
    run, epoch, source = setup_attachment(career_db, tmp_path)
    career_db.add(Resume(user_id=2, filename='foreign.txt', content_hash='existing-upload-hash', raw_text='private'))
    career_db.commit()
    monkeypatch.setattr(attachments, 'classify_attachment', lambda *a, **kw: kind)
    monkeypatch.setattr(attachments, '_parse_profile', lambda *a, **kw: {'candidate_name': 'Alice', 'job_title': 'Engineer'})
    result = attachments.prepare_attachment(run.id, epoch)
    assert result['text'] == 'This is the attachment content'
    career_db.expire_all()
    assert career_db.query(Resume).filter_by(user_id=1).count() == (2 if kind == 'resume' else 1)
    assert career_db.query(JobDescription).filter_by(user_id=1).count() == (2 if kind == 'jd' else 1)
    if kind == 'other':
        assert result['documentId'] is None
        assert '不保存到资料库' in result['notice']
        assert not source.exists()
    else:
        assert result['documentId'].startswith(kind + ':')
        assert '已保存到资料库' in result['notice']
        assert source.exists()
    events = career_db.query(AgentRunEvent).filter_by(run_id=run.id, type='task.progress').order_by(AgentRunEvent.seq).all()
    assert events[0].payload['stage'] == 'extract'
    assert events[-1].payload['stage'] == 'complete'


def test_parse_failure_does_not_save_or_claim_success(attachments, career_db, tmp_path, monkeypatch):
    run, epoch, source = setup_attachment(career_db, tmp_path)
    def fail(*args):
        raise ValueError('model unavailable')
    monkeypatch.setattr(attachments, 'classify_attachment', fail)
    with pytest.raises(agent_runs.RunError, match='附件解析失败'):
        attachments.prepare_attachment(run.id, epoch)
    career_db.expire_all()
    assert career_db.query(Resume).count() == career_db.query(JobDescription).count() == 1
    assert 'attachmentContext' not in career_db.get(AgentRun, run.id).input_json
    assert source.exists()  # retry retains its original


def test_chat_save_does_not_require_embedding(attachments, career_db, tmp_path, monkeypatch):
    from backend.services.documents import document_record
    run, epoch, _ = setup_attachment(career_db, tmp_path)
    monkeypatch.setattr(attachments, 'classify_attachment', lambda *a: 'resume')
    monkeypatch.setattr(attachments, '_parse_profile', lambda *a, **kw: {'candidate_name': 'Alice'})
    from backend.vector.embedding import embedding_service
    def unavailable(*args, **kwargs):
        raise RuntimeError('EMBEDDING_API_KEY or OPENAI_API_KEY is required')
    monkeypatch.setattr(embedding_service, 'embed_many', unavailable)
    result = attachments.prepare_attachment(run.id, epoch)
    career_db.expire_all()
    row = career_db.get(Resume, int(result['documentId'].split(':')[1]))
    assert row.raw_text == 'This is the attachment content'
    assert row.parse_status != 'running'
    assert document_record('resume', row).vectorized is False
    assert attachments.prepare_attachment(run.id, epoch) == result


def test_existing_unparsed_document_is_completed_without_duplicate(attachments, career_db, tmp_path, monkeypatch):
    run, epoch, source = setup_attachment(career_db, tmp_path)
    row = career_db.get(Resume, 1)
    row.content_hash = 'existing-upload-hash'
    row.raw_text = ''
    row.structured_data = {}
    row.parse_status = 'failed'
    career_db.commit()
    def forbidden(*a):
        raise AssertionError('Existing type is known')
    monkeypatch.setattr(attachments, 'classify_attachment', forbidden)
    monkeypatch.setattr(attachments, '_parse_profile', lambda *a, **kw: {'candidate_name': 'Alice'})
    result = attachments.prepare_attachment(run.id, epoch)
    assert result['text'] == 'This is the attachment content'
    assert result['documentId'] == 'resume:1'
    career_db.expire_all()
    assert career_db.query(Resume).count() == 1
    assert career_db.get(Resume, 1).structured_data['candidate_name'] == 'Alice'


def test_attachment_progress_is_durable_before_model_returns_and_after_retry(attachments, career_db, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from backend.agents.harness import AgentHarness
    from backend.services.chat import session_detail
    run, epoch, _ = setup_attachment(career_db, tmp_path)

    def init(self, user_id=None, *, guard=None, progress_callback=None):
        self.model, self.guard, self.progress_callback = 'test-model', guard, progress_callback

    def complete(self, task, messages, response_format, attempt, **kwargs):
        # Read from a separate session while the model request is still in flight.
        with attachments.SessionLocal() as db:
            events = db.query(AgentRunEvent).filter_by(run_id=run.id, type='task.progress').order_by(AgentRunEvent.seq).all()
            assert events, 'The user must see progress before the model responds'
            assert events[-1].payload['data']['agent']['phase'] == 'waiting_response'
        content = ('{"document_type":"resume"}' if task == 'document.classify' else
                   '{}' if attempt == 1 else '{"candidate_name":"Alice"}')
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    monkeypatch.setattr(AgentHarness, '__init__', init)
    monkeypatch.setattr(AgentHarness, '_create_chat_completion', complete)
    monkeypatch.setattr(AgentHarness, '_record_usage_response', lambda *a: None)
    attachments.prepare_attachment(run.id, epoch)
    career_db.expire_all()
    progress = session_detail(career_db, 1, run.session_id)['turns'][0]['attachmentProgress']
    assert {event['stage'] for event in progress} >= {'extract', 'classify', 'llm_analyze', 'validate', 'save', 'complete'}
    assert any(event['current'] == event['total'] == 1 for event in progress)
    assert any(event['data'].get('agent', {}).get('phase') == 'reflecting' for event in progress)
    assert progress[-1]['stage'] == 'complete'
    assert all(event['createdAt'] for event in progress)
