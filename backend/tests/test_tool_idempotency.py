"""Tool transaction tests: replay one draft, reject stale/cancelled/foreign writes."""
import pytest
from sqlalchemy.orm import sessionmaker
from backend.db.agent_models import ToolOperation
from backend.db.career_models import ResumeVersion
from backend.schemas.agent_runs import RunStatus
from backend.services import agent_runs
from backend.tests.career_fixtures import career_engine, career_db
from backend.tests.test_worker_delivery import new_run


@pytest.fixture
def draft_context(career_db, career_engine, monkeypatch):
    from backend.agent_runtime import tools
    monkeypatch.setattr(tools, 'SessionLocal', sessionmaker(career_engine, expire_on_commit=False))
    run_id = new_run(career_db).id
    epoch = agent_runs.claim_run(career_db, run_id)
    return tools, run_id, epoch


def test_replay_returns_original_draft_and_one_operation(draft_context, career_db):
    tools, run_id, epoch = draft_context
    first = tools.save_draft(run_id, epoch, {'summary': 'Actual experience'}, [])
    second = tools.save_draft(run_id, epoch, {'summary': 'replayed text'}, [])
    assert first == second
    assert career_db.query(ResumeVersion).count() == 1
    assert career_db.query(ToolOperation).count() == 1
    assert career_db.get(ResumeVersion, first).structured_content == {'summary': 'Actual experience'}


def test_unknown_fact_rolls_back_artifact_and_operation(draft_context, career_db):
    tools, run_id, epoch = draft_context
    with pytest.raises(agent_runs.RunError):
        tools.save_draft(run_id, epoch, {'summary': 'unverified'}, ['missing-fact'])
    assert career_db.query(ResumeVersion).count() == 0
    assert career_db.query(ToolOperation).count() == 0


def test_cancelled_and_stale_workers_cannot_save(draft_context, career_db):
    tools, run_id, epoch = draft_context
    with pytest.raises(agent_runs.RunError):
        tools.save_draft(run_id, epoch + 1, {}, [])
    agent_runs.cancel_run(career_db, 1, run_id)
    with pytest.raises(agent_runs.RunError):
        tools.save_draft(run_id, epoch, {}, [])
    assert career_db.query(ResumeVersion).count() == 0
