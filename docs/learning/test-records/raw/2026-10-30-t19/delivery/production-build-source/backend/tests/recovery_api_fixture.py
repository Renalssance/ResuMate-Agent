"""Test API pauses only after an answer is committed and before Redis publication."""
import os

from sqlalchemy import select

from backend.db.agent_models import AgentAction, AgentRun
from backend.db.database import SessionLocal
from backend.routes import agent_runs
from backend.tests.recovery_worker_fixture import pause_at
from backend.app import app  # noqa: F401

_publish_run = agent_runs.publish_run


def answer_then_pause(run_id):
    if os.getenv('RESUMATE_RECOVERY_POINT') == 'recovery-answer-before-delivery':
        with SessionLocal() as db:
            run = db.get(AgentRun, run_id)
            actions = list(db.scalars(select(AgentAction).where(
                AgentAction.run_id == run_id, AgentAction.status == 'answered')))
            should_pause = run is not None and run.status == 'queued' and bool(actions)
            action_ids = [action.id for action in actions]
        if should_pause:
            pause_at('recovery-answer-before-delivery', run_id=run_id, action_ids=action_ids)
    return _publish_run(run_id)


agent_runs.publish_run = answer_then_pause
