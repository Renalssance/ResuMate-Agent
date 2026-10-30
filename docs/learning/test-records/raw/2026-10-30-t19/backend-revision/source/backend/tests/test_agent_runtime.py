"""Real Deep Agents/checkpoints with deterministic local model, no paid API calls."""
import json
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from sqlalchemy.orm import sessionmaker
from backend.db.agent_models import AgentRun, AgentAction
from backend.db.career_models import ResumeVersion
from backend.schemas.agent_runs import ActionResponse, RunStatus
from backend.services import agent_runs
from backend.tests.career_fixtures import career_engine, career_db
from backend.tests.test_worker_delivery import new_run


from backend.tests.agent_fixtures import DraftModel


@pytest.fixture
def runtime(career_db, career_engine, monkeypatch, tmp_path):
    from backend.agent_runtime import runner, factory, tools
    sessions = sessionmaker(career_engine, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr(runner, 'SessionLocal', sessions)
    monkeypatch.setattr(tools, 'SessionLocal', sessions)
    monkeypatch.setenv('AGENT_STATE_DIR', str(tmp_path))
    model = DraftModel()
    monkeypatch.setattr(factory, 'model_for_user', lambda user_id: model)
    return runner, model


@pytest.mark.parametrize('repeat', [False, True])
def test_agent_creates_one_business_artifact(runtime, career_db, repeat):
    runner, model = runtime
    model.repeat = repeat
    run_id = new_run(career_db).id
    runner.run_agent(run_id, agent_runs.claim_run(career_db, run_id))
    career_db.expire_all()
    run = career_db.get(AgentRun, run_id)
    assert run.status == RunStatus.SUCCEEDED
    assert career_db.query(ResumeVersion).count() == 1
    assert len(run.output_refs) == 1


def test_interrupt_answer_reopens_checkpoint_and_finishes(runtime, career_db):
    runner, model = runtime
    model.ask = True
    run_id = new_run(career_db).id
    runner.run_agent(run_id, agent_runs.claim_run(career_db, run_id))
    career_db.expire_all()
    assert career_db.get(AgentRun, run_id).status == RunStatus.WAITING_INPUT
    action = career_db.query(AgentAction).one()
    agent_runs.answer_action(career_db, 1, run_id, action.id,
                            ActionResponse(decision='submit', answers={'role': 'API'}, expected_revision=1))
    runner.run_agent(run_id, agent_runs.claim_run(career_db, run_id))
    career_db.expire_all()
    assert career_db.get(AgentRun, run_id).status == RunStatus.SUCCEEDED
    assert career_db.query(AgentAction).count() == 1
    assert career_db.query(ResumeVersion).count() == 1


def test_invalid_tool_input_never_reports_success(runtime, career_db):
    runner, model = runtime
    model.bad_fact = True
    run_id = new_run(career_db).id
    runner.run_agent(run_id, agent_runs.claim_run(career_db, run_id))
    career_db.expire_all()
    assert career_db.get(AgentRun, run_id).status == RunStatus.FAILED
    assert career_db.query(ResumeVersion).count() == 0


def test_transient_failures_stop_after_three_attempts(runtime, career_db, monkeypatch):
    import httpx
    from openai import APITimeoutError
    runner, model = runtime
    def timeout(*args, **kwargs):
        raise APITimeoutError(request=httpx.Request('POST', 'https://model.invalid'))
    monkeypatch.setattr(runner, 'build_agent', timeout)
    run_id = new_run(career_db).id
    for expected_attempt, expected_status in [(2, RunStatus.QUEUED), (3, RunStatus.QUEUED), (3, RunStatus.FAILED)]:
        runner.run_agent(run_id, agent_runs.claim_run(career_db, run_id))
        career_db.expire_all()
        run = career_db.get(AgentRun, run_id)
        assert (run.attempt, run.status) == (expected_attempt, expected_status)


def test_new_run_clears_previous_workspace(runtime, career_db):
    from backend.schemas.agent_runs import RunCreate
    from backend.agent_runtime.factory import build_agent
    from backend.worker_tasks import state_directory
    from langgraph.checkpoint.sqlite import SqliteSaver
    runner, model = runtime
    first = new_run(career_db)
    runner.run_agent(first.id, agent_runs.claim_run(career_db, first.id))
    config = {'configurable': {'thread_id': first.session_id}}
    with SqliteSaver.from_conn_string(str(state_directory() / 'checkpoints.sqlite')) as saver:
        agent = build_agent(1, saver, run_id=first.id, epoch=1)
        agent.update_state(config, {'files': {'/old-job.txt': {'content': ['Previous job private notes'],
                           'created_at': '2026-10-29T00:00:00', 'modified_at': '2026-10-29T00:00:00'}},
                                   'todos': [{'content': 'old task', 'status': 'pending'}],
                                   '_summarization_event': {'cutoff_index': 1, 'summary_message': HumanMessage(content='old summary')},
                                   '_summarization_session_id': 'old-session'})
    second = agent_runs.create_run(career_db, 1, RunCreate(kind='tailoring', jd_id=1, resume_id=1,
                                   session_id=first.session_id, request_id='new-job'))
    runner.run_agent(second.id, agent_runs.claim_run(career_db, second.id))
    with SqliteSaver.from_conn_string(str(state_directory() / 'checkpoints.sqlite')) as saver:
        agent = build_agent(1, saver, run_id=second.id, epoch=1)
        state = agent.get_state(config).values
        assert '/old-job.txt' not in state.get('files', {})
        assert state.get('todos', []) == []
        assert state.get('_summarization_event') is None
        assert state.get('_summarization_session_id') != 'old-session'
    career_db.expire_all()
    assert career_db.get(AgentRun, second.id).status == RunStatus.SUCCEEDED
    assert career_db.query(ResumeVersion).count() == 2


def test_cancel_during_model_timeout_finishes_cancelled(runtime, career_db, monkeypatch):
    import httpx
    from openai import APITimeoutError
    from backend.db.agent_models import AgentSession
    runner, model = runtime
    run_id = new_run(career_db).id
    def cancelled_timeout(*args, **kwargs):
        agent_runs.cancel_run(career_db, 1, run_id)
        raise APITimeoutError(request=httpx.Request('POST', 'https://model.invalid'))
    monkeypatch.setattr(runner, 'build_agent', cancelled_timeout)
    runner.run_agent(run_id, agent_runs.claim_run(career_db, run_id))
    career_db.rollback()  # End the MySQL snapshot opened by cancel_run.refresh().
    run = career_db.get(AgentRun, run_id)
    assert run.status == RunStatus.CANCELLED
    assert career_db.get(AgentSession, run.session_id).active_run_id is None
