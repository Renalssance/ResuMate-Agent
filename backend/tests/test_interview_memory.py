"""Practice feedback requires confirmation and shares durable memory revocation."""
import pytest

from backend.db.agent_models import AgentRun, AgentSession
from backend.db.career_models import BusinessMemory, InterviewTurn, ProfileFact
from backend.schemas.agent_runs import RunStatus
from backend.schemas.interviews import InterviewCreate
from backend.services import agent_runs, interviews, interview_commands, memory
from backend.tests.career_fixtures import career_engine, career_db
from backend.tests.interview_fixtures import seed_application, seed_question, answer_command


def feedback_seed(db):
    seed_application(db)
    created = interviews.create_interview(db, 1, InterviewCreate(requestId='practice', applicationId=1))
    turn = seed_question(db, created)
    turn.answer = 'I used one transaction'
    turn.feedback = {'summary': 'Practice feedback', 'strengths': [], 'improvements': [],
                     'practiceFocus': 'Explain transaction boundaries with an example'}
    db.add(InterviewTurn(interview_id=created['interviewId'], turn_index=2, question='What if it fails?',
                        question_context={'mode': 'follow_up', 'refs': []}))
    db.commit()
    return created, turn


def test_confirmation_is_owned_idempotent_and_never_creates_profile_fact(career_db):
    created, turn = feedback_seed(career_db)
    iid = created['interviewId']
    before = career_db.query(ProfileFact).count()
    for uid, confirmed, code in [(1, False, 'confirmation_required'), (2, True, 'not_found')]:
        with pytest.raises(agent_runs.RunError) as err:
            interviews.confirm_feedback_memory(career_db, uid, iid, 1, confirmed=confirmed)
        assert err.value.code == code
    assert career_db.query(BusinessMemory).count() == 0
    saved = interviews.confirm_feedback_memory(career_db, 1, iid, 1, confirmed=True)
    assert saved['content'] == turn.feedback['practiceFocus']
    assert saved['sourceRef'] == {'kind': 'interview_turn', 'interviewId': iid, 'turnId': turn.id}
    assert interviews.confirm_feedback_memory(career_db, 1, iid, 1, confirmed=True) == saved
    assert career_db.query(BusinessMemory).count() == 1
    assert career_db.query(ProfileFact).count() == before
    memory.delete_memory(career_db, 1, saved['id'])
    with pytest.raises(agent_runs.RunError) as err:
        interviews.confirm_feedback_memory(career_db, 1, iid, 1, confirmed=True)
    assert err.value.code == 'memory_deleted'


def test_missing_feedback_cannot_create_memory(career_db):
    created, _ = feedback_seed(career_db)
    with pytest.raises(agent_runs.RunError) as err:
        interviews.confirm_feedback_memory(career_db, 1, created['interviewId'], 2, confirmed=True)
    assert err.value.code == 'feedback_missing'
    assert career_db.query(BusinessMemory).count() == 0


@pytest.mark.parametrize('running', [False, True])
def test_next_generation_uses_confirmed_memory_and_delete_fences_session(career_db, running):
    created, _ = feedback_seed(career_db)
    iid = created['interviewId']
    saved = interviews.confirm_feedback_memory(career_db, 1, iid, 1, confirmed=True)
    ack = interview_commands.handle_command(career_db, 1, iid, answer_command(turn=2))
    run = career_db.get(AgentRun, ack['resultRef'])
    assert run.input_versions['memories'] == [{'memoryId': saved['id']}]
    assert memory.memories_for_run(career_db, run) == [saved]
    epoch = agent_runs.claim_run(career_db, run.id) if running else None
    deletion = memory.delete_memory(career_db, 1, saved['id'])
    assert deletion['newSessionRequired'] is True
    assert deletion['cleanupStatus'] == 'pending'
    assert set(deletion['affectedRunIds']) == {created['runId'], run.id}
    assert memory.memories_for_run(career_db, run) == []
    assert interviews.interview_snapshot(career_db, 1, iid)['sessionInvalidated'] is True
    assert agent_runs.run_snapshot(career_db, 1, run.id)['sessionInvalidated'] is True
    assert memory.list_memories(career_db, 1)['pendingDeletions'][0]['memoryId'] == saved['id']
    if running:
        with pytest.raises(agent_runs.RunError) as err:
            interviews.guard_interview_execution(career_db, run.id, epoch)
        assert err.value.code == 'session_context_invalidated'
        career_db.rollback()
        interviews.finish_interview_generation(career_db, run.id, epoch, RunStatus.SUCCEEDED,
                                               result_json={'forbidden': True})
    else:
        assert agent_runs.claim_run(career_db, run.id) is None
    current = career_db.get(AgentRun, run.id)
    assert current.status == RunStatus.CANCELLED and current.result_json is None
    assert career_db.get(AgentSession, run.session_id).context_invalidated_at is not None


def test_deleted_interview_memory_removes_real_checkpoint_only_after_worker_lock(career_db, career_engine,
                                                                               monkeypatch, tmp_path):
    import sqlite3
    from sqlalchemy.orm import sessionmaker
    from backend import worker_tasks
    from backend.tests.test_agent_memory import checkpoint_history
    created, _ = feedback_seed(career_db)
    iid = created['interviewId']
    saved = interviews.confirm_feedback_memory(career_db, 1, iid, 1, confirmed=True)
    ack = interview_commands.handle_command(career_db, 1, iid, answer_command(turn=2))
    run = career_db.get(AgentRun, ack['resultRef'])
    path = tmp_path / 'checkpoints.sqlite'
    checkpoint_history(path, run.session_id, 'private interview practice')
    checkpoint_history(path, 'unrelated', 'preserve unrelated graph')
    monkeypatch.setattr(worker_tasks, 'SessionLocal', sessionmaker(career_engine, expire_on_commit=False, autoflush=False))
    monkeypatch.setenv('AGENT_STATE_DIR', str(tmp_path))
    with worker_tasks.execution_lock() as acquired:
        assert acquired
        memory.delete_memory(career_db, 1, saved['id'])
        assert worker_tasks.recover_runs() == 0
        with sqlite3.connect(path) as connection:
            assert connection.execute('SELECT count(*) FROM checkpoints WHERE thread_id=?', (run.session_id,)).fetchone()[0] == 3
    assert worker_tasks.recover_runs() == 0
    career_db.rollback()
    assert career_db.get(AgentSession, run.session_id).checkpoint_deleted_at is not None
    with sqlite3.connect(path) as connection:
        for table in ('checkpoints', 'writes'):
            assert connection.execute(f'SELECT count(*) FROM {table} WHERE thread_id=?', (run.session_id,)).fetchone()[0] == 0
            assert connection.execute(f'SELECT count(*) FROM {table} WHERE thread_id=?', ('unrelated',)).fetchone()[0] == 3
    assert memory.list_memories(career_db, 1)['pendingDeletions'] == []
