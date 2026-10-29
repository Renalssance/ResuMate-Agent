import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, OperationalError

from backend.tests.career_fixtures import career_engine, career_db
from backend.db.agent_models import AgentSession, AgentRun, AgentRunEvent, AgentAction, ToolOperation
from backend.schemas.agent_runs import RUN_EVENT_ADAPTER, RunStatus


def add_run(db, run_id='run-1', request_id='request-1', user_id=1):
    session = AgentSession(id='session-' + run_id, user_id=user_id, purpose='tailoring')
    db.add(session)
    db.flush()
    run = AgentRun(id=run_id, user_id=user_id, session_id=session.id,
                   request_id=request_id, kind='tailoring', input_json={'resumeId': 1})
    db.add(run)
    db.commit()
    return run


def test_request_id_is_unique_per_user(career_db):
    add_run(career_db)
    add_run(career_db, 'bob-run', user_id=2)
    with pytest.raises(IntegrityError):
        add_run(career_db, 'duplicate-run')
    career_db.rollback()
    assert career_db.get(AgentRun, 'run-1').status == RunStatus.QUEUED


def test_run_cannot_belong_to_another_users_session(career_db):
    add_run(career_db)
    career_db.add(AgentRun(id='wrong-owner', user_id=2, session_id='session-run-1',
                          request_id='other', kind='tailoring'))
    with pytest.raises(IntegrityError):
        career_db.commit()
    career_db.rollback()


@pytest.mark.parametrize('model, values', [
    (AgentRunEvent, {'seq': 1, 'type': 'run.status', 'payload': {'status': 'queued'}}),
    (AgentAction, {'interrupt_id': 'interrupt-1', 'kind': 'input', 'payload': {'field': 'role'}}),
    (ToolOperation, {'operation_key': 'draft:1:initial', 'tool_name': 'create_resume_draft'}),
])
def test_replay_keys_reject_duplicate_rows(career_db, model, values):
    add_run(career_db)
    career_db.add(model(run_id='run-1', **values))
    career_db.commit()
    career_db.add(model(run_id='run-1', **values))
    with pytest.raises(IntegrityError):
        career_db.commit()
    career_db.rollback()
    assert career_db.query(model).count() == 1


def test_invalid_status_cannot_be_persisted(career_db):
    run = add_run(career_db)
    run.status = 'made-up'
    with pytest.raises((IntegrityError, OperationalError), match='run_status'):
        career_db.commit()
    career_db.rollback()
    assert career_db.get(AgentRun, 'run-1').status == RunStatus.QUEUED


def test_event_payload_matches_discriminator():
    event = RUN_EVENT_ADAPTER.validate_python({
        'runId': 'run-1', 'seq': 1, 'createdAt': '2026-10-29T00:00:00Z',
        'type': 'run.status', 'payload': {'status': 'running'},
    })
    assert event.payload.status == RunStatus.RUNNING
    with pytest.raises(ValidationError):
        RUN_EVENT_ADAPTER.validate_python({
            'runId': 'run-1', 'seq': 1, 'createdAt': '2026-10-29T00:00:00Z',
            'type': 'run.status', 'payload': {'text': 'not a status'},
        })


def test_event_serializes_public_envelope_and_rejects_invalid_sequence():
    data = {'runId': 'r1', 'seq': 2, 'createdAt': '2026-10-29T00:00:00Z',
            'type': 'assistant.delta', 'payload': {'text': '正在准备'}}
    event = RUN_EVENT_ADAPTER.validate_python(data)
    assert event.model_dump(mode='json', by_alias=True) == data
    with pytest.raises(ValidationError):
        RUN_EVENT_ADAPTER.validate_python({**data, 'seq': 0})
