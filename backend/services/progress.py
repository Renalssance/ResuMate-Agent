"""Scoped SQL progress; no process-local ownership, task execution or history."""
from sqlalchemy import select

from backend.db.agent_models import AgentRunEvent
from backend.db.database import SessionLocal
from backend.services.agent_runs import guard_execution
from backend.services.run_events import append_event


def append_progress(db, run_id: str, epoch: int, *, stage: str, progress: int, message: str,
                    status: str = 'running', document_id: str | None = None,
                    filename: str | None = None, stage_progress: int | None = None,
                    current: int | None = None, total: int | None = None,
                    data: dict | None = None) -> AgentRunEvent:
    """Append in the caller's business transaction; caller owns the commit."""
    guard_execution(db, run_id, epoch)
    previous = db.scalar(select(AgentRunEvent).where(
        AgentRunEvent.run_id == run_id, AgentRunEvent.type == 'task.progress',
    ).order_by(AgentRunEvent.seq.desc()).limit(1).with_for_update())
    overall = max(0, min(100, progress), previous.payload['overall_progress'] if previous else 0)
    return append_event(db, run_id, 'task.progress', {
        'stage': stage, 'status': status, 'progress': overall, 'overall_progress': overall,
        'message': message, 'document_id': document_id, 'filename': filename,
        'stage_progress': None if stage_progress is None else max(0, min(100, stage_progress)),
        'current': current, 'total': total, 'data': data or {},
    })


class TaskProgress:
    def __init__(self, run_id: str, epoch: int, session_factory=None):
        self.run_id, self.epoch = run_id, epoch
        self.session_factory = session_factory or SessionLocal

    def publish(self, **event) -> None:
        """Use only outside an active write transaction; only nonterminal events."""
        with self.session_factory() as db:
            append_progress(db, self.run_id, self.epoch, **event)
            db.commit()
