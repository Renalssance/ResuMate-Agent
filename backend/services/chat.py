"""Conversation projections over durable Runs; no second chat database."""
from collections import defaultdict
from datetime import timezone
from uuid import uuid4

from sqlalchemy import func, select

from backend.db.agent_models import AgentRun, AgentRunEvent, AgentSession
from backend.services.agent_runs import RunError


def owned_session(db, user_id: int, session_id: str):
    session = db.scalar(select(AgentSession).where(AgentSession.id == session_id,
        AgentSession.user_id == user_id, AgentSession.purpose == 'chat'))
    if session is None:
        raise RunError(404, 'not_found', '会话不存在')
    return session


def _iso(value):
    return value.replace(tzinfo=timezone.utc).isoformat()


def _summary(session, first=None, updated=None):
    return {'sessionId': session.id, 'title': (first or '新的求职对话')[:48],
            'createdAt': _iso(session.created_at), 'updatedAt': _iso(updated or session.created_at),
            'activeRunId': session.active_run_id}


def create_session(db, user_id: int):
    session = AgentSession(id=str(uuid4()), user_id=user_id, purpose='chat')
    db.add(session)
    db.commit()
    return _summary(session)


def list_sessions(db, user_id: int):
    first_message = select(AgentRun.input_json).where(AgentRun.session_id == AgentSession.id).order_by(
        AgentRun.created_at, AgentRun.id).limit(1).correlate(AgentSession).scalar_subquery()
    updated = select(func.max(AgentRun.updated_at)).where(AgentRun.session_id == AgentSession.id).correlate(
        AgentSession).scalar_subquery()
    rows = db.execute(select(AgentSession, first_message, updated).where(
        AgentSession.user_id == user_id, AgentSession.purpose == 'chat').order_by(
        func.coalesce(updated, AgentSession.created_at).desc(), AgentSession.id.desc())).all()
    return [_summary(session, (inputs or {}).get('message'), timestamp) for session, inputs, timestamp in rows]


def session_detail(db, user_id: int, session_id: str):
    session = owned_session(db, user_id, session_id)
    runs = list(db.scalars(select(AgentRun).where(AgentRun.session_id == session_id,
        AgentRun.user_id == user_id).order_by(AgentRun.created_at, AgentRun.id)))
    events = defaultdict(list)
    for event in db.scalars(select(AgentRunEvent).join(AgentRun, AgentRun.id == AgentRunEvent.run_id).where(
            AgentRun.session_id == session_id, AgentRun.user_id == user_id).order_by(AgentRunEvent.seq)):
        events[event.run_id].append(event)
    turns = []
    for run in runs:
        text, tools, last_seq = '', {}, 0
        reasoning, reasoning_active = '', False
        attachment_progress = []
        for event in events[run.id]:
            last_seq = event.seq
            payload = event.payload
            if event.type == 'task.progress' and payload.get('data', {}).get('scope') == 'attachment':
                if payload['data'].get('reset'):
                    attachment_progress = []
                attachment_progress.append({**payload, 'createdAt': _iso(event.created_at), 'seq': event.seq})
            if event.type == 'assistant.delta':
                text += payload['text']
            elif event.type == 'assistant.reasoning':
                reasoning += ('\n\n' if reasoning and not reasoning_active else '') + payload['text']
                reasoning_active = True
            elif event.type == 'assistant.reasoning.done':
                reasoning_active = False
            elif event.type.startswith('tool.'):
                key = payload['operation_key']
                tools[key] = {'name': payload['tool_name'], 'operationKey': key,
                    'status': {'tool.started': 'running', 'tool.completed': 'succeeded', 'tool.failed': 'failed'}[event.type],
                    'resultRef': payload.get('result_ref')}
        if run.result_json is not None:
            text = run.result_json.get('text', text)
        turns.append({'runId': run.id, 'message': run.input_json['message'], 'status': run.status,
            'text': text, 'attachmentProgress': attachment_progress, 'reasoning': reasoning, 'reasoningActive': reasoning_active and run.status in ('queued', 'running'), 'lastSeq': last_seq, 'tools': list(tools.values()), 'outputRefs': run.output_refs,
            'result': run.result_json, 'errorCode': run.error_code, 'input': {**{key: run.input_json.get(key) for key in ('resumeId', 'jdId')},
                **({'attachment': {'filename': run.input_json['attachment']['filename']}}
                   if run.input_json.get('attachment') else {})}})
    return {**_summary(session, runs[0].input_json['message'] if runs else None,
                       max((run.updated_at for run in runs), default=session.created_at)), 'turns': turns}
