"""Progress is committed with SQL state and resumes independently of API memory."""
import asyncio

import pytest
from pydantic import ValidationError
from sqlalchemy import event, select
from sqlalchemy.orm import Session, sessionmaker

from backend.db.agent_models import AgentRunEvent
from backend.db.models import Resume
from backend.schemas.workflow import AnalyzeResponse, DocumentParseResponse, SseProgressEvent
from backend.services import agent_runs, progress, run_events
from backend.tests.career_fixtures import career_db, career_engine
from backend.tests.test_long_task_core import parse_request


def test_workflow_responses_expose_task_id_for_sse_subscription():
    assert DocumentParseResponse(documents=[], task_id='task-parse').task_id == 'task-parse'
    assert AnalyzeResponse(run_id=1, job_title='Backend', candidates=[], task_id='task-match').task_id == 'task-match'


def test_sse_progress_event_uses_frontend_contract_keys():
    payload = SseProgressEvent(task_id='task-1', document_id='resume:1', filename='resume.pdf',
                              stage='extract', status='running', progress=40, overall_progress=40,
                              message='提取', data={'document_type': 'resume'}).model_dump(by_alias=True)
    assert payload['taskId'] == 'task-1' and payload['documentId'] == 'resume:1'
    assert payload['overallProgress'] == 40


def test_progress_refuses_terminal_events_before_business_commit(career_db, career_engine):
    run_id = agent_runs.create_run(career_db, 1, parse_request()).id
    epoch = agent_runs.claim_run(career_db, run_id)
    factory = sessionmaker(career_engine)
    with pytest.raises(ValidationError):
        progress.TaskProgress(run_id, epoch, factory).publish(stage='completed', status='success', progress=100, message='未提交成功')
    career_db.rollback()
    assert career_db.query(AgentRunEvent).filter_by(run_id=run_id, type='task.progress').count() == 0


def test_progress_and_business_write_rollback_together(career_db, career_engine):
    run_id = agent_runs.create_run(career_db, 1, parse_request()).id
    epoch = agent_runs.claim_run(career_db, run_id)
    def fail_event(connection, cursor, statement, parameters, context, many):
        if statement.startswith('INSERT INTO agent_run_events'):
            raise RuntimeError('event unavailable')
    event.listen(career_engine, 'before_cursor_execute', fail_event)
    try:
        with Session(career_engine, autoflush=False) as db:
            db.get(Resume, 1).raw_text = 'must roll back'
            with pytest.raises(RuntimeError, match='event unavailable'):
                progress.append_progress(db, run_id, epoch, stage='save', progress=90, message='保存')
    finally:
        event.remove(career_engine, 'before_cursor_execute', fail_event)
    career_db.rollback()
    assert career_db.get(Resume, 1).raw_text == ''
    assert career_db.query(AgentRunEvent).filter_by(run_id=run_id, type='task.progress').count() == 0


def test_legacy_idle_heartbeat_releases_database_connection(career_db, career_engine, monkeypatch):
    run_id = agent_runs.create_run(career_db, 1, parse_request()).id
    career_db.close()
    clock = [0.0]
    monkeypatch.setattr(run_events, 'monotonic', lambda: clock[0])
    async def advance(_):
        clock[0] += 15
    monkeypatch.setattr(run_events.asyncio, 'sleep', advance)
    async def consume():
        stream = run_events.stream_task_events(sessionmaker(career_engine), 1, run_id, 1)
        assert await anext(stream) == ': connected\n\n'
        assert await anext(stream) == ': heartbeat\n\n'
        assert career_engine.pool.checkedout() == 0
        await stream.aclose()
    asyncio.run(consume())
