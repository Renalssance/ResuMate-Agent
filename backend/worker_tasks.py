"""Single-host worker. Shared local volume locks also exclude overlapping restarts."""
from contextlib import contextmanager
import fcntl
import logging
import os
from pathlib import Path
from threading import Event, Thread

from sqlalchemy import select
from backend.db.database import SessionLocal
from backend.db.agent_models import AgentRun, AgentSession
from backend.db.models import utcnow
from backend.schemas.agent_runs import RunStatus
from backend.services import agent_runs
from backend.services.run_delivery import publish_run
from backend.worker import app
from backend.infrastructure.redis_client import warn_redis_capacity

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


def cleanup_invalidated_sessions() -> None:
    """Caller holds execution_lock: no graph can recreate a deleted thread."""
    from langgraph.checkpoint.sqlite import SqliteSaver
    with SessionLocal() as db:
        sessions = list(db.scalars(select(AgentSession).where(
            AgentSession.context_invalidated_at.is_not(None),
            AgentSession.checkpoint_deleted_at.is_(None))))
        if not sessions:
            return
        try:
            with SqliteSaver.from_conn_string(str(state_directory() / 'checkpoints.sqlite')) as saver:
                for session in sessions:
                    try:
                        # Holding the OS lock proves any old executor has stopped,
                        # including a restart before the stale-heartbeat timeout.
                        running = list(db.scalars(select(AgentRun).where(
                            AgentRun.session_id == session.id, AgentRun.kind.in_(['tailoring', 'interview_generation', 'chat']),
                            AgentRun.status == RunStatus.RUNNING)))
                        for run in running:
                            agent_runs.finish_run(db, run.id, run.execution_epoch, RunStatus.CANCELLED)
                        saver.delete_thread(session.id)
                        session.checkpoint_deleted_at = utcnow()
                        db.commit()
                    except Exception:
                        db.rollback()
                        logger.warning('Checkpoint cleanup pending for session %s', session.id)
        except Exception:
            db.rollback()
            logger.warning('Checkpoint cleanup unavailable; pending sessions will retry')


@app.task(name='resumate.execute_run')
def execute_run(run_id: str) -> None:
    with execution_lock() as acquired:
        if not acquired:
            return  # SQL scanner will redispatch queued work.
        try:
            with SessionLocal() as db:
                epoch = agent_runs.claim_run(db, run_id)
                kind = db.scalar(select(AgentRun.kind).where(AgentRun.id == run_id)) if epoch is not None else None
            if epoch is None:
                return
            stopped = Event()
            heartbeat = Thread(target=_heartbeat, args=(run_id, epoch, stopped), daemon=True)
            heartbeat.start()
            try:
                if kind == 'chat':
                    from backend.agent_runtime.chat import run_chat
                    run_chat(run_id, epoch)
                elif kind == 'tailoring':
                    from backend.agent_runtime.runner import run_agent
                    run_agent(run_id, epoch)
                elif kind == 'interview_generation':
                    from backend.agent_runtime.interviews import run_interview_generation
                    run_interview_generation(run_id, epoch)
                elif kind == 'resume_export':
                    from backend.services.resume_export import run_resume_export
                    run_resume_export(run_id, epoch)
                elif kind == 'document_parse':
                    from backend.services.document_process import run_document_parse_process
                    run_document_parse_process(run_id, epoch)
                elif kind == 'document_import':
                    from backend.services.document_process import run_document_import_process
                    run_document_import_process(run_id, epoch)
                elif kind == 'match_analysis':
                    from backend.services.analysis_tasks import run_match_analysis
                    run_match_analysis(run_id, epoch)
                elif kind == 'question_generation':
                    from backend.services.analysis_tasks import run_question_generation
                    run_question_generation(run_id, epoch)
                elif kind == 'answer_followup':
                    from backend.services.analysis_tasks import run_answer_followup
                    run_answer_followup(run_id, epoch)
                else:
                    with SessionLocal() as db:
                        agent_runs.finish_run(db, run_id, epoch, RunStatus.FAILED,
                                              error_code='unsupported_run_kind')
            finally:
                stopped.set()
                heartbeat.join(timeout=5)
        finally:
            cleanup_invalidated_sessions()


@app.task(name='resumate.recover_runs')
def recover_runs() -> int:
    warn_redis_capacity()
    with execution_lock() as acquired:
        if not acquired:
            return 0
        with SessionLocal() as db:
            agent_runs.recover_stale_runs(db)
        cleanup_invalidated_sessions()
        with SessionLocal() as db:
            queued = list(db.scalars(select(AgentRun.id).where(AgentRun.status == RunStatus.QUEUED)))
    return sum(publish_run(run_id) for run_id in queued)
