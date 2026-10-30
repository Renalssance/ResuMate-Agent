"""Atomic interview acceptance, immutable replay and both database locking paths."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.agent_models import AgentRun, AgentSession
from backend.db.career_models import InterviewCommand, InterviewEvent, InterviewSession, InterviewTurn
from backend.db.models import JobApplication, JobDescription
from backend.schemas.agent_runs import RunCreate, RunStatus
from backend.schemas.interviews import InterviewCreate, INTERVIEW_COMMAND_ADAPTER
from backend.services import agent_runs, interviews, interview_commands
from backend.tests.career_fixtures import career_engine, career_db
from backend.tests.interview_fixtures import seed_application, seed_question, answer_command


def create(db, key='create-1'):
    return interviews.create_interview(db, 1, InterviewCreate(requestId=key, applicationId=1))


def command(kind, *, mid='command-1', turn=1, **payload):
    return INTERVIEW_COMMAND_ADAPTER.validate_python({'clientMessageId': mid, 'type': kind,
        'expectedTurn': turn, 'payload': payload})


def test_create_freezes_submission_and_start_job_and_replays(career_db):
    app = seed_application(career_db)
    accepted = create(career_db)
    before = interviews.interview_snapshot(career_db, 1, accepted['interviewId'])
    assert before['userId'] == 1 and before['applicationId'] == app.id
    assert before['currentTurn'] == 0 and before['turns'] == []
    assert before['generation']['runId'] == accepted['runId']
    assert before['sourceSnapshot']['revision'] == 3
    assert before['sourceSnapshot']['structuredContent'] == app.submitted_snapshot['structuredContent']
    assert before['sourceSnapshot']['job']['rawText'] == 'Build APIs'
    career_db.get(JobDescription, 1).raw_text = 'Changed afterwards'
    career_db.commit()
    assert create(career_db) == accepted
    after = interviews.interview_snapshot(career_db, 1, accepted['interviewId'])
    assert after['sourceSnapshot'] == before['sourceSnapshot']
    assert career_db.query(InterviewSession).count() == career_db.query(AgentRun).count() == 1
    with pytest.raises(agent_runs.RunError) as err:
        interviews.create_interview(career_db, 1, InterviewCreate(requestId='create-1', applicationId=2))
    assert err.value.code == 'request_conflict'


@pytest.mark.parametrize('case,code', [('foreign','not_found'), ('missing','not_found'),
    ('unsubmitted','interview_context_missing'), ('draft','interview_context_missing'), ('job','not_found')])
def test_create_rejects_missing_unowned_or_unconfirmed_material(career_db, case, code):
    app = seed_application(career_db)
    if case == 'unsubmitted': app.submitted_snapshot = None
    if case == 'draft':
        from backend.db.career_models import ResumeVersion
        from backend.schemas.resume_versions import VersionStatus
        career_db.get(ResumeVersion, app.resume_version_id).status = VersionStatus.DRAFT
    if case == 'job': app.jd_id = None
    career_db.commit()
    with pytest.raises(agent_runs.RunError) as err:
        interviews.create_interview(career_db, 2 if case == 'foreign' else 1,
            InterviewCreate(requestId='new', applicationId=999 if case == 'missing' else 1))
    assert err.value.code == code
    career_db.rollback()
    assert career_db.query(InterviewSession).count() == career_db.query(AgentRun).count() == 0


def test_lost_ack_replays_one_answer_and_one_run_even_after_finish(career_db):
    seed_application(career_db)
    accepted = create(career_db)
    row = seed_question(career_db, accepted)
    request = answer_command(text='  One transaction  ')
    first = interview_commands.handle_command(career_db, 1, accepted['interviewId'], request)
    assert first['status'] == 'accepted'
    assert career_db.get(InterviewTurn, row.id).answer == 'One transaction'
    interview_commands.handle_command(career_db, 1, accepted['interviewId'], command('session.finish', mid='finish'))
    assert interview_commands.handle_command(career_db, 1, accepted['interviewId'], request) == first
    assert career_db.query(InterviewCommand).count() == 2
    assert career_db.query(AgentRun).count() == 2
    with pytest.raises(agent_runs.RunError) as err:
        interview_commands.handle_command(career_db, 1, accepted['interviewId'], answer_command(text='different'))
    assert err.value.code == 'command_payload_conflict'


def test_different_id_cannot_answer_same_question_and_failed_write_rolls_back(career_db, monkeypatch):
    seed_application(career_db)
    accepted = create(career_db)
    row = seed_question(career_db, accepted)
    original = agent_runs.create_run_in_transaction
    def broken(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError('after Run insertion')
    monkeypatch.setattr(agent_runs, 'create_run_in_transaction', broken)
    with pytest.raises(RuntimeError):
        interview_commands.handle_command(career_db, 1, accepted['interviewId'], answer_command())
    assert career_db.get(InterviewTurn, row.id).answer is None
    assert career_db.query(InterviewCommand).count() == 0
    assert career_db.query(AgentRun).count() == 1
    assert career_db.query(InterviewEvent).filter_by(type='answer.accepted').count() == 0
    monkeypatch.setattr(agent_runs, 'create_run_in_transaction', original)
    interview_commands.handle_command(career_db, 1, accepted['interviewId'], answer_command())
    with pytest.raises(agent_runs.RunError) as err:
        interview_commands.handle_command(career_db, 1, accepted['interviewId'], answer_command('other'))
    assert err.value.code == 'answer_already_submitted'


def test_cancel_opening_retry_new_run_and_public_run_boundary(career_db):
    seed_application(career_db)
    first = create(career_db)
    iid, rid = first['interviewId'], first['runId']
    interview_commands.handle_command(career_db, 1, iid, command('generation.cancel', turn=0, runId=rid))
    assert career_db.get(AgentRun, rid).status == RunStatus.CANCELLED
    ack = interview_commands.handle_command(career_db, 1, iid,
        command('generation.retry', mid='retry', turn=0, runId=rid))
    assert ack['resultRef'] != rid
    assert career_db.get(AgentRun, rid).status == RunStatus.CANCELLED
    active = career_db.get(AgentRun, ack['resultRef'])
    for action in (lambda: agent_runs.cancel_run(career_db, 1, active.id),
                   lambda: agent_runs.retry_run(career_db, 1, rid),
                   lambda: agent_runs.create_run(career_db, 1, RunCreate(kind='tailoring', jdId=1,
                       resumeId=1, sessionId=active.session_id, requestId='bypass'))):
        with pytest.raises(agent_runs.RunError) as err:
            action()
        assert err.value.code == 'interview_command_required'
        career_db.rollback()


def test_running_cancel_and_finish_reject_late_business_writes(career_db):
    seed_application(career_db)
    accepted = create(career_db)
    epoch = agent_runs.claim_run(career_db, accepted['runId'])
    interview_commands.handle_command(career_db, 1, accepted['interviewId'],
        command('session.finish', turn=0))
    with pytest.raises(agent_runs.RunError):
        interviews.guard_interview_execution(career_db, accepted['runId'], epoch)
    career_db.rollback()
    interviews.finish_interview_generation(career_db, accepted['runId'], epoch, RunStatus.SUCCEEDED,
                                           result_json={'mustNotSave': True})
    assert career_db.get(AgentRun, accepted['runId']).status == RunStatus.CANCELLED
    assert career_db.get(AgentRun, accepted['runId']).result_json is None
    assert career_db.query(InterviewTurn).count() == 0
    assert career_db.query(InterviewEvent).filter_by(type='generation.cancelled').count() == 1


def test_two_commands_serialize_after_existing_mysql_snapshot(career_db, career_engine):
    seed_application(career_db)
    accepted = create(career_db)
    seed_question(career_db, accepted)
    career_db.close()
    stale_ready, first_done = Event(), Event()
    def stale_reader():
        with Session(career_engine, expire_on_commit=False) as db:
            assert db.scalar(select(InterviewCommand.id)) is None
            stale_ready.set()
            assert first_done.wait(10)
            return interview_commands.handle_command(db, 1, accepted['interviewId'], answer_command())
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(stale_reader)
        assert stale_ready.wait(10)
        with Session(career_engine) as first:
            ack = interview_commands.handle_command(first, 1, accepted['interviewId'], answer_command())
        first_done.set()
        assert future.result(timeout=10) == ack
    assert career_db.query(InterviewCommand).count() == 1
    assert career_db.query(AgentRun).count() == 2


@pytest.mark.parametrize('body', [dict(kind='tailoring', jdId=1, resumeId=1, interviewId='x'),
    dict(kind='interview_generation', interviewId='x', expectedTurn=9),
    dict(kind='interview_generation', interviewId='x', expectedTurn=0, resumeId=1)])
def test_run_kind_fields_do_not_mix(body):
    with pytest.raises(ValidationError):
        RunCreate(requestId='new', **body)


@pytest.fixture
def interview_client(career_db, career_engine, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.db.database import get_db
    from backend.routes.interviews import router
    import backend.routes.interviews as routes
    app = FastAPI()
    app.include_router(router)
    sessions, published = [], []
    def get_test_db():
        with Session(career_engine, autoflush=False, expire_on_commit=False) as db:
            sessions.append(db)
            yield db
    app.dependency_overrides[get_db] = get_test_db
    monkeypatch.setattr(routes, 'publish_run', published.append)
    monkeypatch.setattr(routes, 'publish_interview_hint_sync', lambda *_: None)
    with TestClient(app) as client:
        yield client, sessions, published


def test_http_admission_outside_sql_and_accepted_replay_skips_redis(career_db, interview_client,
                                                                 controlled_rate_limiter, monkeypatch):
    from backend.tests.test_agent_run_routes import headers
    from backend.infrastructure.redis_client import RedisUnavailable
    seed_application(career_db)
    client, sessions, published = interview_client
    original = controlled_rate_limiter.allow_request
    async def checked(*args):
        assert all(not db.in_transaction() for db in sessions)
        return await original(*args)
    monkeypatch.setattr(controlled_rate_limiter, 'allow_request', checked)
    first = client.post('/api/interviews', headers=headers(), json={'requestId':'http', 'applicationId':1})
    assert first.status_code == 202, first.text
    assert controlled_rate_limiter.calls == [(1, 'run')]
    controlled_rate_limiter.error = RedisUnavailable('offline')
    assert client.post('/api/interviews', headers=headers(), json={'requestId':'http', 'applicationId':1}).json() == first.json()
    assert controlled_rate_limiter.calls == [(1, 'run')]
    career_db.rollback()
    seed_question(career_db, first.json())
    controlled_rate_limiter.error = None
    url = '/api/interviews/' + first.json()['interviewId']
    body = answer_command().model_dump(mode='json', by_alias=True)
    accepted = client.post(url+'/commands', headers=headers(), json=body)
    assert accepted.status_code == 202, accepted.text
    assert len(controlled_rate_limiter.calls) == 2
    controlled_rate_limiter.error = RedisUnavailable('offline')
    assert client.post(url+'/commands', headers=headers(), json=body).json() == accepted.json()
    assert len(controlled_rate_limiter.calls) == 2
    assert client.get(url, headers=headers()).status_code == 200
    assert client.get(url, headers=headers('bob')).status_code == 404
    finish = command('session.finish', mid='close').model_dump(mode='json', by_alias=True)
    assert client.post(url+'/commands', headers=headers(), json=finish).status_code == 202
    assert len(controlled_rate_limiter.calls) == 2
    assert len(published) == 2


def test_http_failed_admission_writes_no_interview(career_db, interview_client, controlled_rate_limiter):
    from backend.tests.test_agent_run_routes import headers
    seed_application(career_db)
    client, _, _ = interview_client
    controlled_rate_limiter.result = (False, 17)
    response = client.post('/api/interviews', headers=headers(), json={'requestId':'blocked', 'applicationId':1})
    assert response.status_code == 429 and response.headers['retry-after'] == '17'
    career_db.rollback()
    assert career_db.query(InterviewSession).count() == 0


def test_two_cancel_ids_only_emit_one_actual_cancel_event(career_db):
    seed_application(career_db)
    accepted = create(career_db)
    first_command = command('generation.cancel', mid='cancel-1', turn=0, runId=accepted['runId'])
    first = interview_commands.handle_command(career_db, 1, accepted['interviewId'], first_command)
    interview_commands.handle_command(career_db, 1, accepted['interviewId'],
        command('generation.cancel', mid='cancel-2', turn=0, runId=accepted['runId']))
    assert interview_commands.handle_command(career_db, 1, accepted['interviewId'], first_command) == first
    assert career_db.query(InterviewEvent).filter_by(type='generation.cancelled').count() == 1


def test_additive_upgrade_preserves_legacy_interview_without_inventing_context(career_db, career_engine):
    from pathlib import Path
    from sqlalchemy import inspect, text
    from backend.db import database
    app = seed_application(career_db)
    version_id = app.resume_version_id
    career_db.close()
    with career_engine.begin() as connection:
        # Recreate the immediately preceding four-table skeleton with its real columns.
        for table in ('interview_commands', 'interview_events', 'interview_turns', 'interview_sessions'):
            connection.execute(text(f'DROP TABLE {table}'))
        connection.execute(text('''CREATE TABLE interview_sessions (
            id VARCHAR(36) PRIMARY KEY, user_id INTEGER NOT NULL, application_id INTEGER,
            jd_id INTEGER, resume_version_id VARCHAR(36) NOT NULL, status VARCHAR(8) NOT NULL,
            created_at DATETIME NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(application_id) REFERENCES job_applications(id) ON DELETE SET NULL,
            FOREIGN KEY(jd_id) REFERENCES job_descriptions(id) ON DELETE SET NULL,
            FOREIGN KEY(resume_version_id) REFERENCES resume_versions(id))'''))
        connection.execute(text('''CREATE TABLE interview_turns (
            id INTEGER PRIMARY KEY, interview_id VARCHAR(36) NOT NULL, turn_index INTEGER NOT NULL,
            question TEXT NOT NULL, answer TEXT, feedback JSON,
            CONSTRAINT uq_interview_turn UNIQUE(interview_id,turn_index),
            FOREIGN KEY(interview_id) REFERENCES interview_sessions(id) ON DELETE CASCADE)'''))
        connection.execute(text('''CREATE TABLE interview_commands (
            id INTEGER PRIMARY KEY, interview_id VARCHAR(36) NOT NULL, user_id INTEGER NOT NULL,
            client_message_id VARCHAR(100) NOT NULL, type VARCHAR(40) NOT NULL,
            result_ref VARCHAR(255), status VARCHAR(9) NOT NULL,
            CONSTRAINT uq_interview_command UNIQUE(interview_id,client_message_id),
            FOREIGN KEY(interview_id) REFERENCES interview_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)'''))
        InterviewEvent.__table__.create(connection)
        connection.execute(text('''INSERT INTO interview_sessions
            (id,user_id,resume_version_id,status,created_at) VALUES ('legacy',1,:version,'active',CURRENT_TIMESTAMP)'''), {'version':version_id})
        connection.execute(text("INSERT INTO interview_turns (id,interview_id,turn_index,question) VALUES (1,'legacy',1,'Original question')"))
        connection.execute(text("INSERT INTO interview_commands (id,interview_id,user_id,client_message_id,type,status) VALUES (1,'legacy',1,'old','answer.submit','accepted')"))
    if career_engine.dialect.name == 'sqlite':
        database.ensure_sqlite_schema(career_engine)
        database.ensure_sqlite_schema(career_engine)
    else:
        sql = (Path(__file__).resolve().parents[2] / 'deploy/schema/005_text_interviews.sql').read_text()
        with career_engine.begin() as connection:
            for statement in sql.split(';'):
                if statement.strip(): connection.execute(text(statement))
    with career_engine.connect() as connection:
        assert connection.execute(text('SELECT agent_session_id,source_snapshot FROM interview_sessions')).one() == (None,None)
        assert connection.execute(text('SELECT question,question_context FROM interview_turns')).one() == ('Original question',None)
        assert connection.execute(text('SELECT client_message_id,request_json,ack_json FROM interview_commands')).one() == ('old',None,None)
        assert any(index['column_names'] == ['agent_session_id'] for index in inspect(connection).get_indexes('interview_sessions'))
    with pytest.raises(agent_runs.RunError) as err:
        interviews.interview_snapshot(career_db, 1, 'legacy')
    assert err.value.code == 'interview_context_missing'


def test_initial_run_insert_failure_rolls_back_interview_and_agent_session(career_db, monkeypatch):
    seed_application(career_db)
    original = agent_runs.create_run_in_transaction
    def broken(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError('acceptance failed after insert')
    monkeypatch.setattr(agent_runs, 'create_run_in_transaction', broken)
    with pytest.raises(RuntimeError): create(career_db)
    assert career_db.query(InterviewSession).count() == 0
    assert career_db.query(AgentSession).count() == 0
    assert career_db.query(AgentRun).count() == 0


def test_concurrent_initial_request_returns_one_interview(career_db, career_engine):
    seed_application(career_db)
    career_db.close()
    def submit():
        with Session(career_engine) as db:
            return create(db, 'same-request')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))
    assert results[0] == results[1]
    assert career_db.query(InterviewSession).count() == 1
    assert career_db.query(AgentSession).count() == 1
    assert career_db.query(AgentRun).count() == 1


def test_exhausted_recovery_snapshot_is_failed_and_retry_uses_frozen_sources(career_db):
    from datetime import timedelta
    from backend.db.models import utcnow
    seed_application(career_db)
    accepted = create(career_db)
    before = interviews.interview_snapshot(career_db, 1, accepted['interviewId'])['sourceSnapshot']
    agent_runs.claim_run(career_db, accepted['runId'])
    run = career_db.get(AgentRun, accepted['runId'])
    run.attempt = 3
    career_db.commit()
    agent_runs.recover_stale_runs(career_db, now=utcnow() + timedelta(seconds=91))
    snapshot = interviews.interview_snapshot(career_db, 1, accepted['interviewId'])
    assert snapshot['generation']['status'] == 'failed'
    assert snapshot['generation']['errorCode'] == 'worker_lost'
    career_db.delete(career_db.get(JobApplication, 1))
    career_db.delete(career_db.get(JobDescription, 1))
    career_db.commit()
    ack = interview_commands.handle_command(career_db, 1, accepted['interviewId'],
        command('generation.retry', turn=0, runId=run.id))
    assert ack['resultRef'] != run.id
    assert interviews.interview_snapshot(career_db, 1, accepted['interviewId'])['sourceSnapshot'] == before


def test_latest_generation_uses_command_order_when_mysql_timestamps_tie(career_db, monkeypatch):
    from datetime import datetime
    from uuid import UUID
    from sqlalchemy import update
    identifiers = iter([UUID('ffffffff-ffff-ffff-ffff-ffffffffffff'),
                        UUID('00000000-0000-0000-0000-000000000001'),
                        UUID('00000000-0000-0000-0000-000000000002')])
    monkeypatch.setattr(agent_runs, 'uuid4', lambda: next(identifiers))
    seed_application(career_db)
    first = create(career_db)
    seed_question(career_db, first)
    ack = interview_commands.handle_command(career_db, 1, first['interviewId'], answer_command())
    # MySQL DATETIME has second precision; synthetic model turns can share a second.
    career_db.execute(update(AgentRun).values(created_at=datetime(2026, 10, 30, 10, 0)))
    career_db.commit()
    assert interviews.interview_snapshot(career_db, 1, first['interviewId'])['generation']['runId'] == ack['resultRef']
    interview_commands.handle_command(career_db, 1, first['interviewId'],
        command('generation.cancel', mid='stop', runId=ack['resultRef']))
    assert interviews.interview_snapshot(career_db, 1, first['interviewId'])['generation']['runId'] == ack['resultRef']
    retry = interview_commands.handle_command(career_db, 1, first['interviewId'],
        command('generation.retry', mid='retry-order', runId=ack['resultRef']))
    assert retry['resultRef'] != ack['resultRef']
