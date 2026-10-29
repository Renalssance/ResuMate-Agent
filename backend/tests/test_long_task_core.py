"""Durable legacy task contracts, using disposable SQLite and MySQL databases."""
import asyncio
import json
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import event, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from backend.db import database
from backend.db.agent_models import AgentRun, AgentRunEvent
from backend.db.models import AnalysisJob, JobDescription, Resume
from backend.schemas.agent_runs import RunCreate, RunStatus
from backend.services import agent_runs, background_tasks, progress, run_events
from backend.tests.career_fixtures import career_db, career_engine


def parse_request(request_id='parse-1', **extra):
    return RunCreate(kind='document_parse', documentId='resume:1', parseMode='reparse', requestId=request_id, **extra)


def followup_request(request_id='followup-1'):
    return RunCreate(kind='answer_followup', followup={'question': '怎样排查？', 'answer': '先看指标'}, requestId=request_id)


@pytest.mark.parametrize('data', [
    {'kind': 'document_parse', 'documentId': 'resume:1', 'parseMode': 'upload'},
    {'kind': 'match_analysis', 'jdId': 1, 'resumeIds': [1]},
    {'kind': 'question_generation', 'analysisJobId': 1, 'candidateId': 1, 'questionCount': 3},
    {'kind': 'answer_followup', 'followup': {'question': '怎样排查？', 'answer': '先看指标'}},
])
def test_new_kinds_accept_only_their_own_request_fields(data):
    request = RunCreate(**data, requestId='request')
    assert request.kind == data['kind']
    with pytest.raises(ValidationError):
        RunCreate(**data, requestId='request', resumeVersionId='unrelated')


def test_document_run_identity_dedupes_and_captures_owned_source(career_db):
    request = parse_request()
    run = agent_runs.create_run(career_db, 1, request)
    assert str(UUID(run.id)) == run.id
    assert run.input_json['documentId'] == 'resume:1'
    assert run.input_json['sourceRef'] == ''
    assert run.input_versions['document']
    assert agent_runs.create_run(career_db, 1, request).id == run.id
    assert career_db.query(AgentRun).count() == 1
    with pytest.raises(agent_runs.RunError) as error:
        agent_runs.create_run(career_db, 2, parse_request('foreign'))
    assert error.value.status == 404


def test_upload_lookup_reuses_before_storage_and_rejects_kind_conflicts(career_db):
    request = RunCreate(kind='document_parse', documentId='resume:1', parseMode='upload', requestId='upload-1')
    run = agent_runs.create_run(career_db, 1, request)
    assert agent_runs.find_upload_run(career_db, 1, 'upload-1', 'resume').id == run.id
    assert agent_runs.find_upload_run(career_db, 2, 'upload-1', 'resume') is None
    with pytest.raises(agent_runs.RunError) as error:
        agent_runs.find_upload_run(career_db, 1, 'upload-1', 'jd')
    assert error.value.code == 'request_conflict'


def test_match_job_and_candidates_rollback_when_queued_event_fails(career_db, career_engine):
    request = RunCreate(kind='match_analysis', jdId=1, resumeIds=[1], requestId='match-1')
    def reject_event(connection, cursor, statement, parameters, context, many):
        if statement.startswith('INSERT INTO agent_run_events'):
            raise RuntimeError('event storage unavailable')
    event.listen(career_engine, 'before_cursor_execute', reject_event)
    try:
        with pytest.raises(RuntimeError, match='event storage'):
            agent_runs.create_run(career_db, 1, request)
        career_db.rollback()
    finally:
        event.remove(career_engine, 'before_cursor_execute', reject_event)
    assert career_db.query(AnalysisJob).count() == 0
    assert career_db.query(AgentRun).count() == 0
    run = agent_runs.create_run(career_db, 1, request)
    job = career_db.get(AnalysisJob, run.input_json['analysisJobId'])
    assert len(job.candidates) == 1 and job.candidates[0].resume_id == 1
    assert agent_runs.create_run(career_db, 1, request).id == run.id
    assert career_db.query(AnalysisJob).count() == 1


def test_result_is_durable_immutable_and_exposed_without_tailoring_artifacts(career_db):
    run_id = agent_runs.create_run(career_db, 1, followup_request()).id
    epoch = agent_runs.claim_run(career_db, run_id)
    agent_runs.finish_run(career_db, run_id, epoch, RunStatus.SUCCEEDED, result_json={'follow_up': '原始结果'})
    agent_runs.finish_run(career_db, run_id, epoch, RunStatus.SUCCEEDED, result_json={'follow_up': '不可覆盖'})
    career_db.expire_all()
    assert agent_runs.run_snapshot(career_db, 1, run_id)['result'] == {'follow_up': '原始结果'}
    assert agent_runs.run_artifacts(career_db, 1, run_id) == []


def test_retry_revalidates_new_kind_source_instead_of_tailoring_context(career_db):
    run_id = agent_runs.create_run(career_db, 1, parse_request()).id
    epoch = agent_runs.claim_run(career_db, run_id)
    agent_runs.finish_run(career_db, run_id, epoch, RunStatus.FAILED, error_code='parse_failed')
    assert agent_runs.retry_run(career_db, 1, run_id).status == RunStatus.QUEUED
    epoch = agent_runs.claim_run(career_db, run_id)
    agent_runs.finish_run(career_db, run_id, epoch, RunStatus.FAILED, error_code='parse_failed')
    career_db.get(Resume, 1).user_id = 2
    career_db.commit()
    with pytest.raises(agent_runs.RunError) as error:
        agent_runs.retry_run(career_db, 1, run_id)
    assert error.value.status == 404


def test_progress_reads_prior_sql_progress_and_fences_cancellation(career_db, career_engine):
    run_id = agent_runs.create_run(career_db, 1, parse_request()).id
    epoch = agent_runs.claim_run(career_db, run_id)
    factory = sessionmaker(career_engine, expire_on_commit=False, autoflush=False)
    progress.TaskProgress(run_id, epoch, factory).publish(stage='extract', progress=30, message='提取', stage_progress=50, current=1, total=2)
    progress.TaskProgress(run_id, epoch, factory).publish(stage='analyze', progress=20, message='分析')
    career_db.rollback()
    rows = list(career_db.scalars(select(AgentRunEvent).where(AgentRunEvent.run_id == run_id, AgentRunEvent.type == 'task.progress').order_by(AgentRunEvent.seq)))
    assert [row.payload['overall_progress'] for row in rows] == [30, 30]
    assert rows[0].payload['stage_progress'] == 50
    agent_runs.cancel_run(career_db, 1, run_id)
    with pytest.raises(agent_runs.RunError, match='取消'):
        progress.TaskProgress(run_id, epoch, factory).publish(stage='save', progress=90, message='保存')
    career_db.rollback()
    assert career_db.query(AgentRunEvent).filter_by(run_id=run_id, type='task.progress').count() == 2


def test_async_submit_survives_broker_down_without_running_handler(career_db, monkeypatch):
    monkeypatch.setattr(background_tasks, 'publish_run', lambda run_id: False, raising=False)
    response = background_tasks.submit_task(career_db, 1, followup_request(), prefer='respond-async')
    assert response.status_code == 202
    accepted = json.loads(response.body)
    assert set(accepted) == {'taskId'}
    assert response.headers['preference-applied'] == 'respond-async'
    run = career_db.get(AgentRun, accepted['taskId'])
    assert run.status == RunStatus.QUEUED and run.result_json is None
    assert career_db.query(AgentRunEvent).filter_by(run_id=run.id).count() == 1


def test_sync_wait_closes_request_connection_and_times_out_with_identity(career_db, career_engine, monkeypatch):
    monkeypatch.setattr(background_tasks, 'publish_run', lambda run_id: False, raising=False)
    clock = [0.0]
    monkeypatch.setattr(background_tasks, 'monotonic', lambda: clock[0], raising=False)
    def advance(seconds):
        assert career_engine.pool.checkedout() == 0
        clock[0] += 46
    monkeypatch.setattr(background_tasks, 'sleep', advance, raising=False)
    response = background_tasks.submit_task(career_db, 1, followup_request(), prefer='')
    body = json.loads(response.body)
    assert response.status_code == 202 and body['status'] == 'queued' and body['code'] == 'task_pending'
    assert response.headers['location'].endswith(body['taskId'])


def test_legacy_replay_advances_filtered_pages_and_skips_old_failed_attempt(career_db, career_engine):
    run_id = agent_runs.create_run(career_db, 1, followup_request()).id
    epoch = agent_runs.claim_run(career_db, run_id)
    agent_runs.finish_run(career_db, run_id, epoch, RunStatus.FAILED, error_code='first_attempt')
    agent_runs.retry_run(career_db, 1, run_id)
    epoch = agent_runs.claim_run(career_db, run_id)
    for _ in range(105):
        run_events.append_event(career_db, run_id, 'assistant.delta', {'text': 'not legacy progress'})
    agent_runs.finish_run(career_db, run_id, epoch, RunStatus.SUCCEEDED, result_json={'follow_up': '最终回答'})
    async def consume():
        return [frame async for frame in run_events.stream_task_events(sessionmaker(career_engine), 1, run_id, 0)]
    frames = asyncio.run(consume())
    data = [json.loads(frame.split('data: ')[1]) for frame in frames if 'data: ' in frame]
    assert len(data) == 1 and data[0]['status'] == 'success'
    assert data[0]['data'] == {'follow_up': '最终回答'}
    assert any(frame.startswith('id: 111\n') for frame in frames)


def test_old_database_upgrade_preserves_existing_run(career_db, career_engine):
    run_id = agent_runs.create_run(career_db, 1, RunCreate(kind='tailoring', jdId=1, resumeId=1, requestId='upgrade')).id
    career_db.close()
    with career_engine.begin() as connection:
        if 'result_json' in {col['name'] for col in inspect(connection).get_columns('agent_runs')}:
            connection.execute(text('ALTER TABLE agent_runs DROP COLUMN result_json'))
    if career_engine.dialect.name == 'sqlite':
        database.ensure_sqlite_schema(career_engine)
        database.ensure_sqlite_schema(career_engine)
    else:
        sql = (Path(__file__).resolve().parents[2] / 'deploy/schema/004_long_task_results.sql').read_text()
        with career_engine.begin() as connection:
            for statement in sql.split(';'):
                if statement.strip():
                    connection.execute(text(statement))
    with career_engine.connect() as connection:
        assert connection.execute(text('SELECT id,result_json FROM agent_runs')).one() == (run_id, None)


@pytest.mark.parametrize('path', ['queued_cancel', 'running_cancel', 'worker_lost'])
def test_terminal_parse_status_survives_without_handler_cleanup(career_db, path):
    from datetime import timedelta
    from backend.db.models import utcnow
    row = career_db.get(Resume, 1)
    row.file_path = '/retained/original.txt'
    career_db.commit()
    run_id = agent_runs.create_run(career_db, 1, parse_request()).id
    if path == 'queued_cancel':
        agent_runs.cancel_run(career_db, 1, run_id)
    elif path == 'running_cancel':
        epoch = agent_runs.claim_run(career_db, run_id)
        agent_runs.cancel_run(career_db, 1, run_id)
        agent_runs.finish_run(career_db, run_id, epoch, RunStatus.SUCCEEDED, result_json={'unexpected': 'cancelled'})
    else:
        agent_runs.claim_run(career_db, run_id)
        career_db.get(AgentRun, run_id).attempt = 3
        career_db.commit()
        agent_runs.recover_stale_runs(career_db, now=utcnow() + timedelta(seconds=91))
    career_db.expire_all()
    assert career_db.get(Resume, 1).parse_status == ('failed' if path == 'worker_lost' else 'cancelled')
    assert career_db.get(Resume, 1).file_path == '/retained/original.txt'
    assert career_db.get(AgentRun, run_id).result_json is None
