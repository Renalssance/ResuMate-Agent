"""Confirmed business memory; deletion revokes graph sessions without erasing artifacts."""
from datetime import timezone
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend.db.agent_models import AgentRun, AgentSession
from backend.db.career_models import BusinessMemory
from backend.db.models import utcnow
from backend.schemas.agent_runs import RunStatus
from backend.schemas.memory import MemoryCreate
from backend.services.agent_runs import RunError
from backend.services.run_events import append_event


def serialize(memory: BusinessMemory) -> dict:
    return {'id': memory.id, 'kind': memory.kind, 'content': memory.content,
            'sourceRef': memory.source_ref,
            'confirmedAt': memory.confirmed_at.replace(tzinfo=timezone.utc).isoformat(),
            'createdAt': memory.created_at.replace(tzinfo=timezone.utc).isoformat()}


def _active(user_id: int):
    return select(BusinessMemory).where(BusinessMemory.user_id == user_id,
        BusinessMemory.deleted_at.is_(None), BusinessMemory.confirmed_at.is_not(None))


def _lock_memory_rows(db: Session, user_id: int) -> None:
    # Both capture and deletion start here, before graph/session writes. The
    # no-op UPDATE takes MySQL row locks and starts SQLite's writer transaction.
    db.execute(update(BusinessMemory).where(BusinessMemory.user_id == user_id)
               .values(deleted_at=BusinessMemory.deleted_at))


def capture_memory_ids(db: Session, user_id: int) -> list[dict]:
    _lock_memory_rows(db, user_id)
    return [{'memoryId': item.id} for item in db.scalars(
        _active(user_id).order_by(BusinessMemory.created_at, BusinessMemory.id).with_for_update())]


def memories_for_run(db: Session, run: AgentRun) -> list[dict]:
    ids = [ref['memoryId'] for ref in run.input_versions.get('memories', [])]
    if not ids or run.kind not in ('tailoring', 'interview_generation'):
        return []
    rows = {item.id: item for item in db.scalars(_active(run.user_id).where(BusinessMemory.id.in_(ids)))}
    return [serialize(rows[memory_id]) for memory_id in ids if memory_id in rows]


def create_memory(db: Session, user_id: int, request: MemoryCreate) -> dict:
    item = BusinessMemory(id=str(uuid4()), user_id=user_id, kind=request.kind,
        content=request.content, source_ref={'kind': 'manual'}, confirmed_at=utcnow())
    db.add(item)
    db.commit()
    db.refresh(item)
    return serialize(item)


def _affected_runs(runs: list[AgentRun], memory_id: str) -> list[AgentRun]:
    sessions = {run.session_id for run in runs
                if any(ref['memoryId'] == memory_id for ref in run.input_versions.get('memories', []))}
    # Every graph Run sharing an affected thread must stop, even if its own selection changed.
    return [run for run in runs if run.session_id in sessions]


def _deletion_status(db: Session, memory_id: str, runs: list[AgentRun]) -> dict:
    session_ids = {run.session_id for run in runs}
    pending = bool(session_ids) and db.scalar(select(AgentSession.id).where(
        AgentSession.id.in_(session_ids), AgentSession.context_invalidated_at.is_not(None),
        AgentSession.checkpoint_deleted_at.is_(None)).limit(1)) is not None
    return {'memoryId': memory_id, 'cleanupStatus': 'pending' if pending else 'complete',
            'affectedRunIds': sorted(run.id for run in runs), 'newSessionRequired': bool(session_ids)}


def list_memories(db: Session, user_id: int) -> dict:
    items = list(db.scalars(select(BusinessMemory).where(BusinessMemory.user_id == user_id)
                           .order_by(BusinessMemory.created_at, BusinessMemory.id)))
    runs = list(db.scalars(select(AgentRun).where(AgentRun.user_id == user_id, AgentRun.kind.in_(('tailoring', 'interview_generation')))))
    pending = []
    for item in items:
        if item.deleted_at:
            status = _deletion_status(db, item.id, _affected_runs(runs, item.id))
            if status['cleanupStatus'] == 'pending':
                pending.append({key: status[key] for key in ('memoryId', 'affectedRunIds', 'cleanupStatus')})
    return {'items': [serialize(item) for item in items if item.deleted_at is None and item.confirmed_at],
            'pendingDeletions': pending}


def delete_memory(db: Session, user_id: int, memory_id: str) -> dict:
    _lock_memory_rows(db, user_id)
    item = db.scalar(select(BusinessMemory).where(
        BusinessMemory.id == memory_id, BusinessMemory.user_id == user_id).with_for_update())
    if item is None:
        raise RunError(404, 'not_found', '记忆不存在')
    db.execute(update(BusinessMemory).where(BusinessMemory.id == memory_id).values(
        content='', source_ref={}, deleted_at=func.coalesce(BusinessMemory.deleted_at, utcnow())))
    runs = list(db.scalars(select(AgentRun).where(
        AgentRun.user_id == user_id, AgentRun.kind.in_(('tailoring', 'interview_generation'))).with_for_update()))
    affected = _affected_runs(runs, memory_id)
    session_ids = {run.session_id for run in affected}
    if session_ids:
        db.execute(update(AgentSession).where(AgentSession.id.in_(session_ids)).values(
            context_invalidated_at=func.coalesce(AgentSession.context_invalidated_at, utcnow())))
    terminal = (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED)
    for run in affected:
        if run.status in terminal:
            continue
        run.cancel_requested_at = run.cancel_requested_at or utcnow()
        run.error_code = 'session_context_invalidated'
        if run.status != RunStatus.RUNNING:
            run.status = RunStatus.CANCELLED
            db.execute(update(AgentSession).where(
                AgentSession.id == run.session_id, AgentSession.active_run_id == run.id).values(active_run_id=None))
        append_event(db, run.id, 'run.status', {'status': run.status, 'error_code': run.error_code})
    db.commit()
    return _deletion_status(db, memory_id, affected)
