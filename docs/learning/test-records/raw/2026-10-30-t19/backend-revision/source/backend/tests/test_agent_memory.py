"""Confirmed memory ownership, revocation, and real checkpoint deletion."""
from datetime import timedelta
import json

import pytest
from sqlalchemy.orm import sessionmaker

from backend.db.agent_models import AgentAction, AgentRun, AgentSession
from backend.db.career_models import ResumeVersion
from backend.db.models import utcnow
from backend.schemas.agent_runs import ActionResponse, RunCreate, RunStatus
from backend.services import agent_runs
from backend.tests.career_fixtures import career_engine, career_db
from backend.tests.test_agent_run_routes import run_client, headers


def save(client, content='请用简洁中文', **extra):
    response = client.post('/api/memories', headers=headers(), json={
        'kind': 'preference', 'content': content, 'confirmed': True, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def run(db, request_id, session_id=None):
    return agent_runs.create_run(db, 1, RunCreate(kind='tailoring', jd_id=1, resume_id=1,
                                  request_id=request_id, session_id=session_id))


def test_memory_requires_confirmation_and_manual_source(run_client):
    for body in [dict(confirmed=False), dict(confirmed='true'), dict(content=' '),
                 dict(content='长' * 4001), dict(kind='experience'),
                 dict(sourceRef={'kind': 'interview_turn', 'turnId': 1})]:
        response = run_client.post('/api/memories', headers=headers(), json={
            'kind': 'preference', 'content': '简洁中文', 'confirmed': True, **body})
        assert response.status_code == 422
    response = run_client.post('/api/memories', headers=headers(), json={
        'kind': 'preference', 'content': '简洁中文'})
    assert response.status_code == 422
    item = save(run_client, '  简洁中文  ')
    assert item['content'] == '简洁中文'
    assert item['sourceRef'] == {'kind': 'manual'}
    assert item['confirmedAt'] and item['createdAt']
    assert run_client.get('/api/memories', headers=headers()).json()['items'] == [item]
    assert run_client.get('/api/memories', headers=headers('bob')).json()['items'] == []
    assert run_client.delete('/api/memories/' + item['id'], headers=headers('bob')).status_code == 404
    assert run_client.get('/api/memories').status_code == 401


def test_run_freezes_only_owned_confirmed_ids_and_deleted_body_is_erased(run_client, career_db):
    from backend.db.career_models import BusinessMemory
    from backend.services.memory import memories_for_run
    item = save(run_client)
    first = run(career_db, 'first')
    second_memory = save(run_client, '突出面试准备重点', kind='interview_feedback')
    career_db.rollback()
    assert first.input_versions['memories'] == [{'memoryId': item['id']}]
    assert '请用简洁中文' not in json.dumps(first.input_json, ensure_ascii=False)
    assert [m['id'] for m in memories_for_run(career_db, first)] == [item['id']]
    deletion = run_client.delete('/api/memories/' + item['id'], headers=headers()).json()
    assert deletion == {'memoryId': item['id'], 'cleanupStatus': 'pending',
                        'affectedRunIds': [first.id], 'newSessionRequired': True}
    career_db.rollback()
    memory = career_db.get(BusinessMemory, item['id'])
    assert memory.content == '' and memory.source_ref == {} and memory.deleted_at is not None
    assert memories_for_run(career_db, first) == []
    assert career_db.get(AgentRun, first.id).status == RunStatus.CANCELLED
    listing = run_client.get('/api/memories', headers=headers()).json()
    assert [m['id'] for m in listing['items']] == [second_memory['id']]
    assert listing['pendingDeletions'] == [{'memoryId': item['id'], 'affectedRunIds': [first.id], 'cleanupStatus': 'pending'}]
    fresh = run(career_db, 'fresh')
    assert fresh.input_versions['memories'] == [{'memoryId': second_memory['id']}]
    assert [m['id'] for m in memories_for_run(career_db, fresh)] == [second_memory['id']]


def test_unused_memory_deletion_is_complete_and_idempotent(run_client):
    item = save(run_client)
    url = '/api/memories/' + item['id']
    result = run_client.delete(url, headers=headers()).json()
    assert result == {'memoryId': item['id'], 'cleanupStatus': 'complete',
                      'affectedRunIds': [], 'newSessionRequired': False}
    assert run_client.delete(url, headers=headers()).json() == result
    assert run_client.get('/api/memories', headers=headers()).json() == {'items': [], 'pendingDeletions': []}


@pytest.mark.parametrize('status', [RunStatus.QUEUED, RunStatus.WAITING_INPUT, RunStatus.WAITING_APPROVAL,
                                    RunStatus.RUNNING, RunStatus.FAILED, RunStatus.SUCCEEDED])
def test_revoked_session_fences_tailoring_but_keeps_business_history(run_client, career_db, status):
    item = save(run_client)
    task = run(career_db, 'revoked')
    task.status = status
    if status in (RunStatus.SUCCEEDED, RunStatus.FAILED):
        career_db.get(AgentSession, task.session_id).active_run_id = None
    if status == RunStatus.RUNNING:
        task.execution_epoch = 1
    career_db.add(AgentAction(id='memory-action', run_id=task.id, interrupt_id='memory-interrupt',
                              kind='input', payload={'question': '工作内容？'}))
    career_db.add(ResumeVersion(id='preserved', user_id=1, run_id=task.id, resume_id=1, jd_id=1,
                                structured_content={'resume': {'self_summary': '原稿'}, 'changes': []}))
    career_db.commit()
    run_client.delete('/api/memories/' + item['id'], headers=headers())
    career_db.rollback()
    current = career_db.get(AgentRun, task.id)
    expected = RunStatus.CANCELLED if status in (RunStatus.QUEUED, RunStatus.WAITING_INPUT, RunStatus.WAITING_APPROVAL) else status
    assert current.status == expected
    assert career_db.get(ResumeVersion, 'preserved').structured_content['resume']['self_summary'] == '原稿'
    for operation in [lambda: run(career_db, 'forbidden', task.session_id),
                      lambda: agent_runs.retry_run(career_db, 1, task.id),
                      lambda: agent_runs.answer_action(career_db, 1, task.id, 'memory-action',
                          ActionResponse(decision='submit', answers={'role': 'API'}, expected_revision=1))]:
        with pytest.raises(agent_runs.RunError) as error:
            operation()
        assert error.value.code == 'session_context_invalidated'
        career_db.rollback()
    assert agent_runs.claim_run(career_db, task.id) is None
    if status == RunStatus.RUNNING:
        with pytest.raises(agent_runs.RunError) as error:
            agent_runs.guard_execution(career_db, task.id, 1)
        assert error.value.code == 'session_context_invalidated'
        career_db.rollback()
        agent_runs.finish_run(career_db, task.id, 1, RunStatus.SUCCEEDED)
        assert career_db.get(AgentRun, task.id).status == RunStatus.CANCELLED


def test_same_session_pdf_is_not_revoked_or_blocked(run_client, career_db):
    from backend.schemas.resume_versions import VersionStatus
    item = save(run_client)
    first = run(career_db, 'history')
    first.status = RunStatus.SUCCEEDED
    career_db.get(AgentSession, first.session_id).active_run_id = None
    career_db.add(ResumeVersion(id='confirmed', user_id=1, run_id=first.id, resume_id=1, jd_id=1,
                                status=VersionStatus.CONFIRMED, structured_content={'resume': {'self_summary': '原稿'}}))
    career_db.commit()
    export = agent_runs.create_run(career_db, 1, RunCreate(kind='resume_export',
                    resume_version_id='confirmed', session_id=first.session_id, request_id='pdf-before'))
    deletion = run_client.delete('/api/memories/' + item['id'], headers=headers()).json()
    assert deletion['affectedRunIds'] == [first.id]
    career_db.rollback()
    assert career_db.get(AgentRun, export.id).status == RunStatus.QUEUED
    epoch = agent_runs.claim_run(career_db, export.id)
    assert epoch is not None
    agent_runs.guard_execution(career_db, export.id, epoch)
    career_db.rollback()
    agent_runs.finish_run(career_db, export.id, epoch, RunStatus.FAILED, error_code='test')
    assert agent_runs.retry_run(career_db, 1, export.id).status == RunStatus.QUEUED
    agent_runs.cancel_run(career_db, 1, export.id)
    again = agent_runs.create_run(career_db, 1, RunCreate(kind='resume_export',
                    resume_version_id='confirmed', session_id=first.session_id, request_id='pdf-after'))
    assert again.status == RunStatus.QUEUED


def checkpoint_history(path, session_id, marker):
    """Use the actual saver format, including recoverable writes and summary files."""
    from langgraph.checkpoint.base import empty_checkpoint
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langchain_core.messages import HumanMessage
    config = {'configurable': {'thread_id': session_id, 'checkpoint_ns': ''}}
    with SqliteSaver.from_conn_string(str(path)) as saver:
        for index in range(3):
            checkpoint = empty_checkpoint()
            checkpoint['channel_values'] = {
                'messages': [HumanMessage(content=f'{marker}-{index}')],
                '_summarization_event': {'cutoff_index': 1, 'summary_message': HumanMessage(content=marker)},
                'files': {'/conversation_history/private.md': {'content': [marker]}}}
            config = saver.put(config, checkpoint, {'source': 'loop', 'step': index}, {})
            saver.put_writes(config, [('messages', [HumanMessage(content=marker)])], f'task-{index}')
        assert len(list(saver.list({'configurable': {'thread_id': session_id}}))) == 3


@pytest.fixture
def memory_worker(career_db, career_engine, monkeypatch, tmp_path):
    from backend import worker_tasks
    sessions = sessionmaker(career_engine, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr(worker_tasks, 'SessionLocal', sessions)
    monkeypatch.setenv('AGENT_STATE_DIR', str(tmp_path))
    return worker_tasks, tmp_path / 'checkpoints.sqlite'


def test_worker_restart_cleans_all_checkpoint_history_and_writes(run_client, career_db, memory_worker):
    import sqlite3
    from langgraph.checkpoint.sqlite import SqliteSaver
    worker, path = memory_worker
    item = save(run_client)
    first = run(career_db, 'older-task')
    first.status = RunStatus.SUCCEEDED
    career_db.get(AgentSession, first.session_id).active_run_id = None
    career_db.commit()
    second = run(career_db, 'newer-task', first.session_id)
    second.status = RunStatus.RUNNING
    second.execution_epoch = 1
    second.heartbeat_at = utcnow() - timedelta(seconds=100)
    career_db.commit()
    checkpoint_history(path, first.session_id, 'deleted private memory')
    checkpoint_history(path, 'unrelated-session', 'keep private memory')
    with worker.execution_lock() as acquired:
        assert acquired
        deletion = run_client.delete('/api/memories/' + item['id'], headers=headers()).json()
        assert deletion['cleanupStatus'] == 'pending'
        assert sorted(deletion['affectedRunIds']) == sorted([first.id, second.id])
        assert worker.recover_runs() == 0
        with SqliteSaver.from_conn_string(str(path)) as saver:
            assert len(list(saver.list({'configurable': {'thread_id': first.session_id}}))) == 3
    # The next scanner represents a restarted worker; SQL retains cleanup intent.
    assert worker.recover_runs() == 0
    career_db.rollback()
    assert career_db.get(AgentRun, second.id).status == RunStatus.CANCELLED
    assert career_db.get(AgentRun, first.id).status == RunStatus.SUCCEEDED
    assert career_db.get(AgentSession, first.session_id).checkpoint_deleted_at is not None
    with sqlite3.connect(path) as conn:
        for table in ('checkpoints', 'writes'):
            assert conn.execute(f'SELECT count(*) FROM {table} WHERE thread_id=?', (first.session_id,)).fetchone()[0] == 0
            assert conn.execute(f'SELECT count(*) FROM {table} WHERE thread_id=?', ('unrelated-session',)).fetchone()[0] == 3
    done = run_client.delete('/api/memories/' + item['id'], headers=headers()).json()
    assert done['cleanupStatus'] == 'complete'
    assert run_client.get('/api/memories', headers=headers()).json()['pendingDeletions'] == []


def test_cleanup_failure_remains_pending_until_next_scan(run_client, career_db, memory_worker, monkeypatch):
    from langgraph.checkpoint.sqlite import SqliteSaver
    worker, path = memory_worker
    item = save(run_client)
    task = run(career_db, 'pending-retry')
    checkpoint_history(path, task.session_id, 'retry deletion')
    run_client.delete('/api/memories/' + item['id'], headers=headers())
    original = SqliteSaver.delete_thread
    def unavailable(self, thread_id):
        raise OSError('disk unavailable')
    monkeypatch.setattr(SqliteSaver, 'delete_thread', unavailable)
    worker.recover_runs()
    assert run_client.get('/api/memories', headers=headers()).json()['pendingDeletions']
    monkeypatch.setattr(SqliteSaver, 'delete_thread', original)
    worker.recover_runs()
    assert run_client.get('/api/memories', headers=headers()).json()['pendingDeletions'] == []


def test_execution_finally_cleans_memory_deleted_during_model_call(run_client, career_db, career_engine, memory_worker, monkeypatch):
    from backend.agent_runtime import runner, factory, tools
    from backend.tests.agent_fixtures import DraftModel
    from langgraph.checkpoint.sqlite import SqliteSaver
    worker, path = memory_worker
    sessions = sessionmaker(career_engine, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr(runner, 'SessionLocal', sessions)
    monkeypatch.setattr(tools, 'SessionLocal', sessions)
    item = save(run_client)
    task = run(career_db, 'delete-during-call')
    # This is the one provider response already in flight when deletion arrives.
    class DeleteDuringCall(DraftModel):
        calls: int = 0
        def _generate(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                deletion = run_client.delete('/api/memories/' + item['id'], headers=headers()).json()
                assert deletion['cleanupStatus'] == 'pending'
            return super()._generate(messages, **kwargs)
    model = DeleteDuringCall()
    monkeypatch.setattr(factory, 'model_for_user', lambda user_id: model)
    worker.execute_run(task.id)
    career_db.rollback()
    stopped = career_db.get(AgentRun, task.id)
    assert stopped.status == RunStatus.CANCELLED
    assert stopped.error_code == 'session_context_invalidated'
    assert model.calls == 1
    assert career_db.query(ResumeVersion).count() == 0
    assert career_db.get(AgentSession, task.session_id).checkpoint_deleted_at is not None
    with SqliteSaver.from_conn_string(str(path)) as saver:
        assert list(saver.list({'configurable': {'thread_id': task.session_id}})) == []


@pytest.mark.parametrize('reuse_session', [False, True])
def test_mysql_create_and_delete_memory_overlap_without_deadlock(career_db, career_engine, monkeypatch, reuse_session):
    """Two actual connections recreate the former Run -> Memory -> Run cycle."""
    if career_engine.dialect.name != 'mysql':
        pytest.skip('MySQL row/FK lock ordering; SQLite serializes writers')
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    from backend.db.career_models import BusinessMemory
    from backend.schemas.memory import MemoryCreate
    from backend.services import memory

    item = memory.create_memory(career_db, 1,
        MemoryCreate(kind='preference', content='并发删除记忆', confirmed=True))
    previous = run(career_db, 'before-overlap')
    previous_id, previous_session_id = previous.id, previous.session_id
    previous.status = RunStatus.SUCCEEDED
    career_db.get(AgentSession, previous.session_id).active_run_id = None
    career_db.commit()
    capture_entered, deletion_locked, capture_query_started = Event(), Event(), Event()
    original_capture = memory.capture_memory_ids

    def capture_after_delete_takes_memory(db, user_id):
        capture_entered.set()
        assert deletion_locked.wait(5), 'deletion did not acquire its memory row'
        return original_capture(db, user_id)

    monkeypatch.setattr(memory, 'capture_memory_ids', capture_after_delete_takes_memory)

    def before_query(conn, cursor, statement, parameters, context, executemany):
        if conn.info.get('memory_test_role') == 'creator' and 'business_memories' in statement:
            capture_query_started.set()

    def after_query(conn, cursor, statement, parameters, context, executemany):
        if (conn.info.get('memory_test_role') == 'deleter'
                and statement.startswith('SELECT') and 'business_memories' in statement
                and 'FOR UPDATE' in statement):
            deletion_locked.set()
            assert capture_query_started.wait(5), 'creator did not attempt memory selection'

    event.listen(career_engine, 'before_cursor_execute', before_query)
    event.listen(career_engine, 'after_cursor_execute', after_query)

    def create_overlapping():
        with Session(career_engine, expire_on_commit=False, autoflush=False) as db:
            connection_info = db.connection().info
            connection_info['memory_test_role'] = 'creator'
            try:
                created = run(db, 'overlapping-create', previous_session_id if reuse_session else None)
                return created.id
            except agent_runs.RunError as error:
                return error.code
            finally:
                connection_info.pop('memory_test_role', None)

    def delete_overlapping():
        assert capture_entered.wait(5), 'creator did not reach memory selection'
        with Session(career_engine, expire_on_commit=False, autoflush=False) as db:
            connection_info = db.connection().info
            connection_info['memory_test_role'] = 'deleter'
            try:
                return memory.delete_memory(db, 1, item['id'])
            finally:
                connection_info.pop('memory_test_role', None)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            created = executor.submit(create_overlapping)
            deleted = executor.submit(delete_overlapping)
            creation_result = created.result(timeout=10)
            deletion_result = deleted.result(timeout=10)
    finally:
        event.remove(career_engine, 'before_cursor_execute', before_query)
        event.remove(career_engine, 'after_cursor_execute', after_query)

    career_db.rollback()
    assert career_db.get(BusinessMemory, item['id']).content == ''
    assert deletion_result['affectedRunIds'] == [previous_id]
    assert career_db.get(AgentRun, previous_id).status == RunStatus.SUCCEEDED
    if reuse_session:
        assert creation_result == 'session_context_invalidated'
        assert career_db.query(AgentRun).count() == 1
    else:
        fresh = career_db.get(AgentRun, creation_result)
        assert fresh.status == RunStatus.QUEUED
        assert fresh.input_versions['memories'] == []
        assert memory.memories_for_run(career_db, fresh) == []


def test_sqlite_memory_selection_keeps_writer_until_new_run_is_visible(career_db, career_engine, monkeypatch):
    """Moving selection earlier must not let deletion miss an uninserted Run."""
    if career_engine.dialect.name != 'sqlite':
        pytest.skip('SQLite writer transaction; MySQL overlap is tested separately')
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session
    from backend.schemas.memory import MemoryCreate
    from backend.services import memory

    item = memory.create_memory(career_db, 1,
        MemoryCreate(kind='preference', content='先冻结再提交', confirmed=True))
    original_capture = memory.capture_memory_ids

    def capture_with_other_connection_attempt(db, user_id):
        selected = original_capture(db, user_id)
        # Probe actual writer exclusion immediately; no timing or sleep guesses.
        with Session(career_engine, autoflush=False) as other:
            other.execute(text('PRAGMA busy_timeout=0'))
            with pytest.raises(OperationalError, match='database is locked'):
                memory.delete_memory(other, 1, item['id'])
            other.rollback()
        return selected

    monkeypatch.setattr(memory, 'capture_memory_ids', capture_with_other_connection_attempt)
    created = run(career_db, 'sqlite-selection-writer')
    assert created.input_versions['memories'] == [{'memoryId': item['id']}]
    with Session(career_engine) as other:
        deletion = memory.delete_memory(other, 1, item['id'])
    career_db.rollback()
    assert deletion['affectedRunIds'] == [created.id]
    assert career_db.get(AgentRun, created.id).status == RunStatus.CANCELLED


def test_snapshot_exposes_revoked_session_without_rewriting_failed_history(run_client, career_db):
    from backend.db.agent_models import AgentRunEvent
    from backend.schemas.resume_versions import VersionStatus
    item = save(run_client)
    failed = run(career_db, 'failed-before-delete')
    failed.status = RunStatus.FAILED
    failed.error_code = 'model_timeout'
    career_db.get(AgentSession, failed.session_id).active_run_id = None
    career_db.add(ResumeVersion(id='confirmed-before-delete', user_id=1, run_id=failed.id,
        resume_id=1, jd_id=1, status=VersionStatus.CONFIRMED,
        structured_content={'resume': {'self_summary': '保留的材料'}}))
    career_db.commit()
    export = agent_runs.create_run(career_db, 1, RunCreate(kind='resume_export',
        resume_version_id='confirmed-before-delete', session_id=failed.session_id, request_id='pdf-snapshot'))
    event_count = career_db.query(AgentRunEvent).filter_by(run_id=failed.id).count()
    deletion = run_client.delete('/api/memories/' + item['id'], headers=headers())
    assert deletion.status_code == 200
    snapshot = run_client.get('/api/agent/runs/' + failed.id, headers=headers()).json()
    assert snapshot['sessionInvalidated'] is True
    assert snapshot['status'] == 'failed'
    assert snapshot['errorCode'] == 'model_timeout'
    pdf = run_client.get('/api/agent/runs/' + export.id, headers=headers()).json()
    assert pdf['sessionInvalidated'] is False
    assert pdf['status'] == 'queued'
    career_db.rollback()
    assert career_db.query(AgentRunEvent).filter_by(run_id=failed.id).count() == event_count
