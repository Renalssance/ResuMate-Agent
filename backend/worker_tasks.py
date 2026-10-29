"""Single-host worker. Shared local volume locks also exclude overlapping restarts."""
from contextlib import contextmanager
import fcntl
import logging
import os
from pathlib import Path
from threading import Event, Thread

from sqlalchemy import select
from backend.db.database import SessionLocal
from backend.db.agent_models import AgentRun
from backend.schemas.agent_runs import RunStatus
from backend.services import agent_runs
from backend.services.run_delivery import publish_run
from backend.worker import app

logger = logging.getLogger(__name__)


def state_directory() -> Path:
    path = Path(os.getenv('AGENT_STATE_DIR', 'data/agent'))
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def execution_lock():
    # A timeout alone is NOT proof of worker death. OS releases this on process exit.
    with (state_directory() / 'execution.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _heartbeat(run_id, epoch, stopped):
    while not stopped.wait(10):
        try:
            with SessionLocal() as db:
                if not agent_runs.heartbeat_run(db, run_id, epoch):
                    return
        except Exception:
            # Never print model settings, full requests, or SQL bind parameters.
            logger.warning('Heartbeat unavailable for Run %s', run_id)


@app.task(name='resumate.execute_run')
def execute_run(run_id: str) -> None:
    from backend.agent_runtime.runner import run_agent
    with execution_lock() as acquired:
        if not acquired:
            return  # SQL scanner will redispatch queued work.
        with SessionLocal() as db:
            epoch = agent_runs.claim_run(db, run_id)
        if epoch is None:
            return
        stopped = Event()
        heartbeat = Thread(target=_heartbeat, args=(run_id, epoch, stopped), daemon=True)
        heartbeat.start()
        try:
            run_agent(run_id, epoch)
        finally:
            stopped.set()
            heartbeat.join(timeout=5)


@app.task(name='resumate.recover_runs')
def recover_runs() -> int:
    with execution_lock() as acquired:
        if not acquired:
            return 0
        with SessionLocal() as db:
            agent_runs.recover_stale_runs(db)
            queued = list(db.scalars(select(AgentRun.id).where(AgentRun.status == RunStatus.QUEUED)))
    return sum(publish_run(run_id) for run_id in queued)
