"""Persistent lifecycle history and owner-only, cursor-based SSE replay."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.agent_models import AgentAction, AgentRun, AgentRunEvent
from backend.db.models import utcnow
from backend.schemas.agent_runs import ActionResponse, RunCreate, RunStatus
from backend.services import agent_runs
from backend.tests.career_fixtures import career_engine, career_db
from backend.tests.test_agent_run_routes import run_client, headers, create


def history(db, run_id):
    db.rollback()
    return list(db.scalars(select(AgentRunEvent).where(AgentRunEvent.run_id == run_id).order_by(AgentRunEvent.seq)))


def new_run(db):
    db.autoflush = False
    db.expire_on_commit = False
    return agent_runs.create_run(db, 1, RunCreate(kind='tailoring', jd_id=1, resume_id=1, request_id='events-1'))


def test_lifecycle_history_survives_retries_and_duplicate_requests(career_db):
    run_id = new_run(career_db).id
    assert new_run(career_db).id == run_id
    epoch = agent_runs.claim_run(career_db, run_id)
    assert agent_runs.claim_run(career_db, run_id) is None
    agent_runs.finish_run(career_db, run_id, epoch, RunStatus.FAILED, error_code='agent_failed')
    agent_runs.retry_run(career_db, 1, run_id)
    agent_runs.cancel_run(career_db, 1, run_id)
    agent_runs.cancel_run(career_db, 1, run_id)
    events = history(career_db, run_id)
    assert [e.seq for e in events] == [1, 2, 3, 4, 5]
    assert [e.payload['status'] for e in events] == ['queued', 'running', 'failed', 'queued', 'cancelled']
    assert events[2].payload['error_code'] == 'agent_failed'


def test_wait_answer_and_worker_recovery_are_in_history(career_db):
    run_id = new_run(career_db).id
    epoch = agent_runs.claim_run(career_db, run_id)
    career_db.add(AgentAction(id='action', run_id=run_id, interrupt_id='int', kind='input', payload={'question': '职责？'}))
    agent_runs.finish_run(career_db, run_id, epoch, RunStatus.WAITING_INPUT)
    agent_runs.answer_action(career_db, 1, run_id, 'action', ActionResponse(decision='submit', answers={'role': '开发'}, expected_revision=1))
    agent_runs.claim_run(career_db, run_id)
    agent_runs.recover_stale_runs(career_db, utcnow() + timedelta(seconds=91))
    events = history(career_db, run_id)
    assert [e.payload['status'] for e in events] == ['queued', 'running', 'waiting_input', 'queued', 'running', 'queued']


def test_status_and_event_rollback_together(career_db, career_engine):
    run_id = new_run(career_db).id
    # A failed event INSERT must not publish a state transition without its history.
    from sqlalchemy import event
    def reject_event(connection, cursor, statement, parameters, context, many):
        if statement.startswith('INSERT INTO agent_run_events'):
            raise RuntimeError('event storage unavailable')
    event.listen(career_engine, 'before_cursor_execute', reject_event)
    try:
        with Session(career_engine, autoflush=False) as db:
            with pytest.raises(RuntimeError, match='event storage'):
                agent_runs.claim_run(db, run_id)
    finally:
        event.remove(career_engine, 'before_cursor_execute', reject_event)
    career_db.rollback()
    assert career_db.get(AgentRun, run_id).status == RunStatus.QUEUED
    assert [e.seq for e in history(career_db, run_id)] == [1]


def test_concurrent_append_uses_unique_monotonic_sequence(career_db, career_engine):
    from backend.services.run_events import append_event
    run_id = new_run(career_db).id
    def append(index):
        with Session(career_engine, autoflush=False, expire_on_commit=False) as db:
            # Start a read snapshot before contending for the write lock (MySQL RR).
            db.get(AgentRun, run_id)
            append_event(db, run_id, 'assistant.delta', {'text': f'片段{index}'})
            db.commit()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(append, range(12)))
    events = history(career_db, run_id)
    assert [e.seq for e in events] == list(range(1, 14))
    assert {e.payload['text'] for e in events[1:]} == {f'片段{i}' for i in range(12)}


def sse_events(response):
    return [json.loads(line.removeprefix('data: ')) for line in response.text.splitlines() if line.startswith('data: ')]


def test_sse_replays_after_cursor_and_protects_ownership(run_client, career_db):
    run_id = create(run_client).json()['runId']
    run_client.post(f'/api/agent/runs/{run_id}/cancel', headers=headers())
    url = f'/api/agent/runs/{run_id}/events'
    assert run_client.get(url).status_code == 401
    assert run_client.get(url, headers=headers('bob')).status_code == 404
    response = run_client.get(url, headers=headers())
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/event-stream')
    events = sse_events(response)
    assert [(e['seq'], e['payload']['status']) for e in events] == [(1, 'queued'), (2, 'cancelled')]
    assert all(e['runId'] == run_id and e['createdAt'] for e in events)
    assert 'id: 2\nevent: run.event\n' in response.text
    response = run_client.get(url + '?after=0', headers={**headers(), 'Last-Event-ID': '1'})
    assert [e['seq'] for e in sse_events(response)] == [2]
    assert sse_events(run_client.get(url + '?after=2', headers=headers())) == []
    invalid = run_client.get(url + '?after=99', headers=headers())
    assert invalid.status_code == 409 and invalid.json()['code'] == 'cursor_reset'
    assert run_client.get(url, headers={**headers(), 'Last-Event-ID': 'oops'}).status_code == 422


def test_live_stream_releases_connections_and_closing_does_not_cancel(career_db, career_engine):
    import asyncio
    from sqlalchemy.orm import sessionmaker
    from backend.services.run_events import stream_events
    run_id = new_run(career_db).id
    factory = sessionmaker(career_engine, autoflush=False, expire_on_commit=False)

    async def consume():
        stream = stream_events(factory, 1, run_id, 0)
        assert await anext(stream) == ': connected\n\n'
        assert json.loads((await anext(stream)).split('data: ')[1])['payload']['status'] == 'queued'
        assert career_engine.pool.checkedout() == 0
        # A different transaction can advance while this subscriber is open.
        with factory() as writer:
            agent_runs.cancel_run(writer, 1, run_id)
        assert json.loads((await anext(stream)).split('data: ')[1])['payload']['status'] == 'cancelled'
        await stream.aclose()
        assert career_engine.pool.checkedout() == 0
    asyncio.run(consume())

    # Leaving a second task's page must not cancel its execution.
    with factory() as writer:
        second = agent_runs.create_run(writer, 1, RunCreate(kind='tailoring', jd_id=1, resume_id=1, request_id='leave'))
        second_id = second.id
    async def leave():
        stream = stream_events(factory, 1, second_id, 0)
        await anext(stream)
        await anext(stream)
        await stream.aclose()
    asyncio.run(leave())
    with factory() as db:
        assert db.get(AgentRun, second_id).status == RunStatus.QUEUED


def test_trimmed_history_requires_snapshot_reset(run_client, career_db):
    from sqlalchemy import delete
    run_id = create(run_client).json()['runId']
    run_client.post(f'/api/agent/runs/{run_id}/cancel', headers=headers())
    career_db.execute(delete(AgentRunEvent).where(AgentRunEvent.run_id == run_id, AgentRunEvent.seq == 1))
    career_db.commit()
    response = run_client.get(f'/api/agent/runs/{run_id}/events?after=0', headers=headers())
    assert response.status_code == 409 and response.json()['code'] == 'cursor_reset'


def test_terminal_backfill_drains_more_than_one_page(run_client, career_db):
    from backend.services.run_events import append_event
    run_id = create(run_client).json()['runId']
    for _ in range(105):
        append_event(career_db, run_id, 'assistant.delta', {'text': '正文'})
    career_db.commit()
    run_client.post(f'/api/agent/runs/{run_id}/cancel', headers=headers())
    events = sse_events(run_client.get(f'/api/agent/runs/{run_id}/events', headers=headers()))
    assert [event['seq'] for event in events] == list(range(1, 108))
    assert events[-1]['payload']['status'] == 'cancelled'


def test_idle_stream_sends_heartbeat_without_retaining_sql_connection(career_db, career_engine, monkeypatch):
    import asyncio
    from sqlalchemy.orm import sessionmaker
    from backend.services import run_events
    run_id = new_run(career_db).id
    clock = [0.0]
    monkeypatch.setattr(run_events, 'monotonic', lambda: clock[0])
    async def advance_clock(_):
        clock[0] += 15
    monkeypatch.setattr(run_events.asyncio, 'sleep', advance_clock)
    async def consume():
        stream = run_events.stream_events(sessionmaker(career_engine), 1, run_id, 1)
        await anext(stream)
        assert await anext(stream) == ': heartbeat\n\n'
        assert career_engine.pool.checkedout() == 0
        await stream.aclose()
    asyncio.run(consume())


def test_snapshot_state_and_cursor_share_one_database_read(career_db, career_engine):
    from sqlalchemy import event
    run_id = new_run(career_db).id
    armed = [True]
    def worker_advances_after_snapshot_query(connection, cursor, statement, parameters, context, many):
        if armed[0] and statement.startswith('SELECT') and 'agent_runs' in statement:
            armed[0] = False
            with Session(career_engine, autoflush=False) as writer:
                agent_runs.claim_run(writer, run_id)
    event.listen(career_engine, 'after_cursor_execute', worker_advances_after_snapshot_query)
    try:
        with Session(career_engine, autoflush=False) as reader:
            snapshot = agent_runs.run_snapshot(reader, 1, run_id)
    finally:
        event.remove(career_engine, 'after_cursor_execute', worker_advances_after_snapshot_query)
    assert (snapshot['status'], snapshot['lastSeq']) in [('queued', 1), ('running', 2)]
