"""SQL event log; callers commit business state and its events together."""
import asyncio
import json
from datetime import timezone
from time import monotonic

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select, true, update
from sqlalchemy.orm import Session

from backend.db.agent_models import AgentRun, AgentRunEvent
from backend.db.models import utcnow
from backend.schemas.agent_runs import RUN_EVENT_ADAPTER, RunStatus

TERMINAL_STATUSES = {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}


def append_event(db: Session, run_id: str, event_type: str, payload: dict) -> AgentRunEvent:
    # Flush caller's state first: production sessions use autoflush=False.
    db.flush()
    locked = db.execute(update(AgentRun).where(AgentRun.id == run_id).values(
        updated_at=AgentRun.updated_at))
    if locked.rowcount != 1:
        raise ValueError('Cannot append to a missing Run')
    # A locking read is a current read on MySQL even if this transaction already
    # opened a REPEATABLE READ snapshot. MAX() alone could allocate an old seq.
    last_seq = db.scalar(select(AgentRunEvent.seq).where(AgentRunEvent.run_id == run_id)
                         .order_by(AgentRunEvent.seq.desc()).limit(1).with_for_update()) or 0
    envelope = RUN_EVENT_ADAPTER.validate_python({
        'runId': run_id, 'seq': last_seq + 1, 'createdAt': utcnow(),
        'type': event_type, 'payload': payload,
    })
    event = AgentRunEvent(run_id=run_id, seq=envelope.seq, type=event_type,
                          payload=envelope.payload.model_dump(mode='json'), created_at=envelope.created_at)
    db.add(event)
    db.flush()
    return event


def event_envelope(event: AgentRunEvent) -> dict:
    created = event.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return {'runId': event.run_id, 'seq': event.seq, 'createdAt': created.isoformat(),
            'type': event.type, 'payload': event.payload}


def read_page(db: Session, user_id: int, run_id: str, after: int) -> tuple[list[dict], bool]:
    from backend.services.agent_runs import RunError
    bounds = select(func.min(AgentRunEvent.seq).label('first'), func.max(AgentRunEvent.seq).label('last')).where(
        AgentRunEvent.run_id == run_id).subquery()
    row = db.execute(select(AgentRun.status, bounds.c.first, bounds.c.last).join(bounds, true()).where(
        AgentRun.id == run_id, AgentRun.user_id == user_id)).first()
    if row is None:
        raise RunError(404, 'not_found', '任务不存在')
    status, first, last = row
    last = last or 0
    if after > last or (first is not None and after < first - 1):
        raise RunError(409, 'cursor_reset', '事件游标已失效，请重新读取任务快照')
    events = list(db.scalars(select(AgentRunEvent).where(
        AgentRunEvent.run_id == run_id, AgentRunEvent.seq > after, AgentRunEvent.seq <= last,
    ).order_by(AgentRunEvent.seq).limit(100)))
    consumed = events[-1].seq if events else after
    return [event_envelope(event) for event in events], status in TERMINAL_STATUSES and consumed >= last


def _read_with_session(session_factory, user_id, run_id, after):
    with session_factory() as db:
        return read_page(db, user_id, run_id, after)


async def stream_events(session_factory, user_id: int, run_id: str, after: int):
    """Each poll releases SQL resources; disconnect only closes this iterator."""
    from backend.services.agent_runs import RunError
    last_sent = monotonic()
    yield ': connected\n\n'
    while True:
        try:
            events, done = await run_in_threadpool(_read_with_session, session_factory, user_id, run_id, after)
        except RunError as error:
            if error.code == 'cursor_reset':
                yield 'event: reset\ndata: {"code":"cursor_reset"}\n\n'
            return
        for event in events:
            yield f'id: {event["seq"]}\nevent: run.event\ndata: {json.dumps(event, ensure_ascii=False)}\n\n'
            after = event['seq']
            last_sent = monotonic()
        if done:
            return
        if len(events) == 100:
            continue
        if monotonic() - last_sent >= 15:
            yield ': heartbeat\n\n'
            last_sent = monotonic()
        await asyncio.sleep(0.5)
