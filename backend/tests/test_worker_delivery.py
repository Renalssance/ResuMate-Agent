"""Catch duplicate claims, stale writers and unbounded recovery in real SQL."""
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy.orm import Session

from backend.db.agent_models import AgentRun, AgentSession
from backend.db.models import utcnow
from backend.schemas.agent_runs import RunCreate, RunStatus
from backend.services import agent_runs
from backend.tests.career_fixtures import career_engine, career_db


def new_run(db):
    return agent_runs.create_run(db, 1, RunCreate(kind='tailoring', jd_id=1, resume_id=1, request_id='delivery-1'))


def test_only_one_delivery_claims_run(career_db, career_engine):
    run_id = new_run(career_db).id
    def claim():
        with Session(career_engine) as db:
            return agent_runs.claim_run(db, run_id)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: claim(), range(3)))
    assert sorted(r for r in results if r is not None) == [1]


def test_stale_epoch_cannot_write_after_recovery(career_db):
    run_id = new_run(career_db).id
    first = agent_runs.claim_run(career_db, run_id)
    agent_runs.recover_stale_runs(career_db, utcnow() + timedelta(seconds=91))
    second = agent_runs.claim_run(career_db, run_id)
    assert (first, second) == (1, 2)
    with pytest.raises(agent_runs.RunError, match='运行权'):
        agent_runs.guard_execution(career_db, run_id, first)
    career_db.rollback()
    agent_runs.guard_execution(career_db, run_id, second)
    career_db.rollback()


def test_third_lost_attempt_fails_and_releases_session(career_db):
    run_id = new_run(career_db).id
    for _ in range(3):
        assert agent_runs.claim_run(career_db, run_id)
        agent_runs.recover_stale_runs(career_db, utcnow() + timedelta(seconds=91))
    career_db.expire_all()
    run = career_db.get(AgentRun, run_id)
    assert (run.status, run.attempt, run.error_code) == (RunStatus.FAILED, 3, 'worker_lost')
    assert career_db.get(AgentSession, run.session_id).active_run_id is None


def test_live_heartbeat_is_not_recovered_and_cancel_fences_tools(career_db):
    run_id = new_run(career_db).id
    epoch = agent_runs.claim_run(career_db, run_id)
    assert agent_runs.recover_stale_runs(career_db, utcnow()) == 0
    agent_runs.cancel_run(career_db, 1, run_id)
    with pytest.raises(agent_runs.RunError):
        agent_runs.guard_execution(career_db, run_id, epoch)
    career_db.rollback()
    agent_runs.finish_run(career_db, run_id, epoch, RunStatus.SUCCEEDED)
    career_db.expire_all()
    assert career_db.get(AgentRun, run_id).status == RunStatus.CANCELLED


def test_broker_failure_does_not_erase_accepted_run(career_db, monkeypatch):
    from backend.services import run_delivery
    monkeypatch.setenv('REDIS_URL', 'redis://127.0.0.1:1/0')
    monkeypatch.setattr(run_delivery.app.conf, 'broker_url', 'redis://127.0.0.1:1/0')
    run_id = new_run(career_db).id
    assert run_delivery.publish_run(run_id) is False
    career_db.expire_all()
    assert career_db.get(AgentRun, run_id).status == RunStatus.QUEUED


def test_execution_lock_prevents_takeover(tmp_path, monkeypatch):
    from backend import worker_tasks
    monkeypatch.setenv('AGENT_STATE_DIR', str(tmp_path))
    with worker_tasks.execution_lock() as first:
        assert first
        with worker_tasks.execution_lock() as duplicate:
            assert not duplicate
    with worker_tasks.execution_lock() as after_release:
        assert after_release
