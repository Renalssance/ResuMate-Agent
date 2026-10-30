"""Real file and worker-process limits; no provider/network requests."""
from datetime import timedelta
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from uuid import uuid4

import fitz
import pytest

from backend.db.agent_models import AgentRun, AgentRunEvent, ToolOperation
from backend.db.models import Resume, utcnow
from backend.schemas.agent_runs import RunCreate, RunStatus
from backend.services import agent_runs
from backend.services.documents import extract_stored_pages, UnsupportedDocumentError
from backend.tests.career_fixtures import career_engine, career_db


@pytest.mark.parametrize('pages', [100, 101])
def test_all_pdf_pages_obey_limit_before_extraction(tmp_path, monkeypatch, pages):
    path = tmp_path / 'many.pdf'
    with fitz.open() as pdf:
        for _ in range(pages):
            pdf.new_page().insert_text((40, 40), 'Readable native resume text with sufficient content.')
        pdf.save(path)
    calls = []
    original = fitz.Page.get_text
    def read(page, *args, **kwargs):
        calls.append(page.number)
        return original(page, *args, **kwargs)
    monkeypatch.setattr(fitz.Page, 'get_text', read)
    if pages == 101:
        with pytest.raises(UnsupportedDocumentError, match='100'):
            extract_stored_pages(path, path.name)
        assert calls == []
    else:
        assert len(extract_stored_pages(path, path.name)) == 100 and len(calls) == 100


def wait_for(read, condition, timeout=8):
    deadline = time.monotonic() + timeout
    value = read()
    while not condition(value) and time.monotonic() < deadline:
        time.sleep(.03)
        value = read()
    assert condition(value), value
    return value


def running(pid):
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True)
    return bool(result.stdout.strip()) and not result.stdout.strip().startswith('Z')


def start_worker(db, engine, tmp_path, *, stage):
    root = tmp_path / uuid4().hex
    root.mkdir()
    (root / 'block-stage').write_text(stage)
    source = root / 'source.txt'
    source.write_text('Candidate resume source with enough readable content.')
    row = db.get(Resume, 1)
    row.file_path, row.filename, row.raw_text, row.structured_data = str(source), source.name, '', {}
    db.commit()
    run_id = agent_runs.create_run(db, 1, RunCreate(kind='document_parse', requestId=uuid4().hex,
        documentId='resume:1', parseMode='upload')).id
    db.commit()
    env = {**os.environ, 'DATABASE_URL': engine.url.render_as_string(hide_password=False),
           'AGENT_STATE_DIR': str(tmp_path / 'agent'), 'TEST_DOCUMENT_PROCESS_ROOT': str(root)}
    log = (root / 'worker.txt').open('w')
    process = subprocess.Popen([sys.executable, '-m', 'backend.tests.fixtures.document_worker', run_id],
                               env=env, stdout=log, stderr=subprocess.STDOUT)
    return process, log, root, run_id


@pytest.mark.parametrize('stage', ['extract', 'model', 'embedding'])
def test_whole_parse_timeout_terminates_work_and_releases_slot(career_db, career_engine, tmp_path, stage):
    worker, log, root, rid = start_worker(career_db, career_engine, tmp_path, stage=stage)
    try:
        wait_for(lambda: (root / 'started.json').exists(), bool)
        worker.wait(timeout=5)
        career_db.rollback()
        run = career_db.get(AgentRun, rid)
        assert run.status == RunStatus.FAILED and run.error_code == 'document_parse_timeout'
        assert run.result_json is None and run.attempt == 1
        assert career_db.get(Resume, 1).parse_status == 'failed'
        assert career_db.query(ToolOperation).filter_by(run_id=rid).count() == 0
        assert career_db.query(AgentRunEvent).filter_by(run_id=rid, type='artifact.created').count() == 0
        child = json.loads((root / 'started.json').read_text())['pid']
        assert not running(child)
        (root / 'release').touch()
        assert not (root / 'continued').exists()
    finally:
        if worker.poll() is None: worker.kill()
        worker.wait(timeout=5)
        log.close()
    # Same real execution lock can admit the next parse after the timed-out child exited.
    next_worker, next_log, next_root, next_id = start_worker(career_db, career_engine, tmp_path, stage='none')
    try:
        next_worker.wait(timeout=6)
        career_db.rollback()
        assert career_db.get(AgentRun, next_id).status == RunStatus.SUCCEEDED, (next_root / 'worker.txt').read_text()
    finally:
        if next_worker.poll() is None: next_worker.kill()
        next_worker.wait(timeout=5)
        next_log.close()


def test_parent_sigkill_stops_child_before_recovery_can_write(career_db, career_engine, tmp_path):
    worker, log, root, rid = start_worker(career_db, career_engine, tmp_path, stage='model')
    child = None
    try:
        wait_for(lambda: (root / 'started.json').exists(), bool)
        child = json.loads((root / 'started.json').read_text())['pid']
        assert child != worker.pid
        worker.kill()
        worker.wait(timeout=5)
        wait_for(lambda: running(child), lambda value: not value)
        (root / 'release').touch()
        assert not (root / 'continued').exists()
        career_db.rollback()
        run = career_db.get(AgentRun, rid)
        assert run.status == RunStatus.RUNNING and run.result_json is None
        assert career_db.query(ToolOperation).count() == 0
        # The caller holds the actual lock when recovering a genuinely stopped attempt.
        run.heartbeat_at = utcnow() - timedelta(minutes=5)
        career_db.commit()
        from backend import worker_tasks
        old = os.environ.get('AGENT_STATE_DIR')
        os.environ['AGENT_STATE_DIR'] = str(tmp_path / 'agent')
        try:
            with worker_tasks.execution_lock() as held:
                assert held and agent_runs.recover_stale_runs(career_db) == 1
        finally:
            if old is None: os.environ.pop('AGENT_STATE_DIR', None)
            else: os.environ['AGENT_STATE_DIR'] = old
        assert career_db.get(AgentRun, rid).status == RunStatus.QUEUED
    finally:
        if worker.poll() is None: worker.kill()
        worker.wait(timeout=5)
        if child and running(child): os.kill(child, signal.SIGKILL)
        log.close()


@pytest.mark.parametrize('fails', [False, True])
def test_document_child_owns_usage_cache_resources(monkeypatch, fails):
    from backend.infrastructure import redis_client
    from backend.services import document_process, document_tasks
    events = []
    class Client:
        def close(self): events.append('closed')
    client = Client()
    monkeypatch.setattr(redis_client, '_sync_client', None)
    monkeypatch.setattr(redis_client, '_sync_pid', None)
    monkeypatch.setattr(redis_client.Redis, 'from_url', lambda *args, **kwargs: client)
    monkeypatch.setattr(document_process, '_watch_parent', lambda: None)
    monkeypatch.setattr(sys, 'argv', ['document_process', 'synthetic-run', '3'])
    def run(run_id, epoch):
        assert (run_id, epoch) == ('synthetic-run', 3)
        assert redis_client.get_sync_redis() is client
        events.append('handler')
        if fails: raise ValueError('synthetic handler failure')
    monkeypatch.setattr(document_tasks, 'run_document_parse', run)
    if fails:
        with pytest.raises(ValueError, match='synthetic handler failure'):
            document_process.main()
    else:
        document_process.main()
    assert events == ['handler', 'closed']
    assert redis_client._sync_client is None


def test_document_child_exits_cleanly_while_parent_pipe_is_open(career_db, career_engine):
    # A delivery for a missing Run returns normally through the real child main.
    # Keep the parent writer open, exactly as the production Popen.wait path does.
    child = subprocess.Popen([sys.executable, '-m', 'backend.services.document_process', 'missing-run', '1'],
        env={**os.environ, 'DATABASE_URL': career_engine.url.render_as_string(hide_password=False)},
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        code = child.wait(timeout=6)
        stderr = child.stderr.read().decode()
        assert code == 0 and 'Fatal Python error' not in stderr, stderr
    finally:
        if child.poll() is None: child.kill()
        child.wait(timeout=5)
        child.stdin.close()
        child.stdout.close()
        child.stderr.close()
