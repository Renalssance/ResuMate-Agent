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


def _task_projection(event: dict, run: AgentRun, latest_status_seq: int) -> dict | None:
    """Project only progress and the current terminal lifecycle into the old API."""
    from backend.schemas.workflow import SseProgressEvent
    if event['type'] == 'task.progress':
        return SseProgressEvent(task_id=run.id, **event['payload']).model_dump(mode='json', by_alias=True)
    if (event['type'] != 'run.status' or event['seq'] != latest_status_seq
            or run.status not in TERMINAL_STATUSES or event['payload']['status'] != run.status):
        return None
    succeeded = run.status == RunStatus.SUCCEEDED
    cancelled = run.status == RunStatus.CANCELLED
    data = run.result_json or {}
    if succeeded and run.kind == 'document_parse':
        data = {'documents': data['documents']} if run.input_json['parseMode'] == 'upload' else {'document': data}
    if not succeeded:
        data = {'code': 'cancelled' if cancelled else run.error_code or 'task_failed'}
    return SseProgressEvent(
        task_id=run.id, stage='completed' if succeeded else 'cancelled' if cancelled else 'failed',
        status='success' if succeeded else 'failed', progress=100, overall_progress=100,
        message='任务已完成' if succeeded else '任务已取消' if cancelled else run.error_code or '任务执行失败',
        document_id=run.input_json.get('documentId'), data=data,
    ).model_dump(mode='json', by_alias=True)


def _read_task_page(session_factory, user_id: int, run_id: str, after: int):
    from backend.services.agent_runs import get_run
    with session_factory() as db:
        events, done = read_page(db, user_id, run_id, after)
        run = get_run(db, user_id, run_id)
        latest_status_seq = db.scalar(select(func.max(AgentRunEvent.seq)).where(
            AgentRunEvent.run_id == run_id, AgentRunEvent.type == 'run.status')) or 0
        frames = [(event['seq'], _task_projection(event, run, latest_status_seq)) for event in events]
        return frames, done


async def stream_task_events(session_factory, user_id: int, run_id: str, after: int):
    """Legacy data frames retain SQL event IDs, including intentional filtered gaps."""
    from backend.services.agent_runs import RunError
    yield ': connected\n\n'
    last_sent = monotonic()
    while True:
        try:
            frames, done = await run_in_threadpool(_read_task_page, session_factory, user_id, run_id, after)
        except RunError as error:
            if error.code == 'cursor_reset':
                yield 'event: reset\ndata: {"code":"cursor_reset"}\n\n'
            return
        for seq, payload in frames:
            after = seq  # Advance even when a full page has no legacy-visible event.
            if payload is not None:
                yield f'id: {seq}\ndata: {json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}\n\n'
                last_sent = monotonic()
        if done:
            return
        if len(frames) == 100:
            continue
        if monotonic() - last_sent >= 15:
            yield ': heartbeat\n\n'
            last_sent = monotonic()
        await asyncio.sleep(0.5)
