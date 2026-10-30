"""Tests-only HTTP observations. Production routes/dependencies remain intact."""
import asyncio
from contextlib import suppress
import os
from pathlib import Path
import socket
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import event, func, select, text

from backend.agent_runtime import factory
from backend.auth.security import AuthContext, get_current_auth, get_current_user
from backend.db.database import SessionLocal, engine
from backend.db.models import JobDescription, LlmUsageEvent, Resume, User
from backend.db.agent_models import AgentAction, AgentRun, AgentSession, AgentRunEvent, ToolOperation
from backend.db.career_models import InterviewEvent, InterviewSession, ResumeVersion
from backend.infrastructure.redis_client import RedisUnavailable
from backend.middleware.rate_limit import require_chat_capacity, require_run_capacity
from backend.routes import agent_runs
from backend.services.interview_events import read_interview_events
from backend.services.ws_tickets import WsTickets
from backend.tests.agent_fixtures import DraftModel

factory.model_for_user = lambda user_id: DraftModel()
router = APIRouter(prefix='/__redis_test')
counts = {'aggregate': 0, 'recent': 0, 'all': 0}
count_lock = threading.Lock()
barrier = {'enabled': False, 'reached': False, 'runId': None}
release = threading.Event()
consumers = {}


@event.listens_for(engine, 'before_cursor_execute')
def count_sql(_connection, _cursor, statement, _parameters, _context, _many):
    sql = statement.lower()
    with count_lock:
        counts['all'] += 1
        if 'llm_usage_events' in sql and sql.lstrip().startswith('select'):
            counts['recent' if 'limit' in sql else 'aggregate'] += 1


_original_publish = agent_runs.publish_run

def publish_after_barrier(run_id):
    if barrier['enabled']:
        barrier.update(reached=True, runId=run_id)
        if not release.wait(90):
            raise RuntimeError('Test publish barrier not released')
        barrier['enabled'] = False
    return _original_publish(run_id)

agent_runs.publish_run = publish_after_barrier


@router.post('/seed')
def seed():
    with SessionLocal() as db:
        db.add_all([User(id=i, username=f'redis-user-{i}', password_hash='no-login') for i in range(1, 8)])
        db.flush()
        db.add_all([Resume(id=1, user_id=1, filename='synthetic.txt', parse_status='parsed',
                           structured_data={'self_summary': 'API development'}, raw_text='API development'),
                    JobDescription(id=1, user_id=1, title='Engineer', raw_text='Build APIs', parse_status='parsed')])
        for uid in (1, 2):
            db.add(ResumeVersion(id=f'version-{uid}', user_id=uid, status='confirmed', structured_content={}))
        db.flush()
        db.add_all([InterviewSession(id=f'interview-{uid}', user_id=uid, resume_version_id=f'version-{uid}') for uid in (1, 2)])
        db.add_all([LlmUsageEvent(user_id=uid, task='seed', model='deterministic', base_url='', total_tokens=uid * 10,
                                  prompt_tokens=uid * 10, completion_tokens=0, success=True) for uid in (1, 2)])
        for name in ('cancel', 'action'):
            db.add(AgentSession(id=f'session-{name}', user_id=1, purpose='tailoring', active_run_id=f'run-{name}'))
            db.flush()
            db.add(AgentRun(id=f'run-{name}', user_id=1, session_id=f'session-{name}', request_id=f'seed-{name}',
                            kind='tailoring', status='waiting_approval', input_json={}, input_versions={}))
            db.flush()
            db.add(AgentAction(id=f'action-{name}', run_id=f'run-{name}', interrupt_id=f'interrupt-{name}',
                               kind='approval', payload={}))
        db.commit()
    return {'users': 7}


@router.get('/topology')
async def topology(request: Request):
    import redis
    resources = request.app.state.redis
    with SessionLocal() as db:
        sql_version, database = db.execute(text('SELECT VERSION(), DATABASE()')).one()
        users = db.scalars(select(User.id).order_by(User.id)).all()
    info = await resources.commands.info('server')
    config = await resources.commands.config_get('maxmemory*')
    return {'hostname': socket.gethostname(), 'pid': os.getpid(), 'mysql': sql_version,
            'database': database, 'users': users, 'redis': info['redis_version'], 'redisPy': redis.__version__,
            'namespace': resources.namespace, 'config': config, 'agentStateVisible': Path('/app/agent-state').exists()}


@router.post('/rate/run', dependencies=[Depends(require_run_capacity)])
def run_rate():
    return {'allowed': True}


@router.post('/rate/chat', dependencies=[Depends(require_chat_capacity)])
def chat_rate():
    return {'allowed': True}


@router.get('/counts')
def query_counts():
    return dict(counts)


@router.get('/state')
def state():
    with SessionLocal() as db:
        tables = {model.__tablename__: db.scalar(select(func.count()).select_from(model)) for model in
                  (AgentRun, Resume, JobDescription, ResumeVersion, LlmUsageEvent)}
    return {'tables': tables, 'files': sorted(str(p.relative_to('/app/data')) for p in Path('/app/data').rglob('*') if p.is_file())}


@router.post('/tickets/{interview_id}')
async def issue_ticket(interview_id: str, request: Request, auth: AuthContext = Depends(get_current_auth)):
    read_interview_events(SessionLocal, auth.user.id, interview_id, 0)
    resources = request.app.state.redis
    try:
        ticket = await WsTickets(resources.commands, resources.namespace).issue_ws_ticket(auth.user.id, interview_id, auth.auth_expires_at)
        ttl = await resources.commands.pttl(f'{resources.namespace}:ws-ticket:{ticket}')
        return {'ticket': ticket, 'ttlMs': ttl, 'authExpiresAt': auth.auth_expires_at.isoformat()}
    except RedisUnavailable as exc:
        raise HTTPException(503, 'Ticket storage unavailable') from exc


@router.post('/consume')
async def consume_ticket(request: Request):
    body = await request.json()
    resources = request.app.state.redis
    try:
        claims = await WsTickets(resources.commands, resources.namespace).consume_ws_ticket(body['ticket'])
        return None if claims is None else {'userId': claims.user_id, 'interviewId': claims.interview_id,
                                          'authExpiresAt': claims.auth_expires_at.isoformat()}
    except RedisUnavailable as exc:
        raise HTTPException(503, 'Ticket storage unavailable') from exc


@router.post('/usage')
def usage(user: User = Depends(get_current_user)):
    from backend.worker import app as worker
    result = worker.send_task('redis_test.record_usage', args=[user.id], retry=False)
    return {'taskId': result.id}


@router.post('/usage-direct')
def usage_direct(user: User = Depends(get_current_user)):
    from backend.services.llm_settings import record_llm_usage
    record_llm_usage(user_id=user.id, task='redis-down', model='deterministic', base_url='', total_tokens=9)
    return {'committed': True}


@router.post('/consumer/{interview_id}')
async def consume_events(interview_id: str, request: Request, user: User = Depends(get_current_user)):
    body = await request.json()
    cursor = body.get('after', 0)
    target = body.get('count', 1)
    emitted = []
    hints = request.app.state.interview_hints
    started = time.monotonic()
    async with hints.watch(interview_id) as ready:
        consumers[interview_id] = True
        try:
            while time.monotonic() - started < 8 and len(emitted) < target:
                rows = read_interview_events(SessionLocal, user.id, interview_id, cursor)
                if rows:
                    emitted.extend(rows)
                    cursor = rows[-1]['seq']
                    if len(emitted) >= target:
                        break
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(ready.wait(), timeout=2)
                ready.clear()
        finally:
            consumers.pop(interview_id, None)
    return {'events': emitted, 'elapsed': time.monotonic() - started}


@router.get('/consumers')
def watched():
    return list(consumers)


@router.post('/events/{interview_id}/{seq}')
async def write_event(interview_id: str, seq: int, request: Request):
    body = await request.json()
    with SessionLocal() as db:
        db.add(InterviewEvent(interview_id=interview_id, seq=seq, type='test.persisted', payload={'text': 'Synthetic event'}))
        db.commit()
    if body.get('publish', True):
        await request.app.state.interview_hints.publish_interview_hint(interview_id, seq)
    return {'seq': seq}


@router.post('/hint/{interview_id}/{seq}')
async def hint(interview_id: str, seq: int, request: Request):
    await request.app.state.interview_hints.publish_interview_hint(interview_id, seq)
    return {'published': True}


@router.post('/reader/{action}')
async def reader(action: str, request: Request):
    hints = request.app.state.interview_hints
    await (hints.aclose() if action == 'stop' else hints.start())
    return {'reader': action}


@router.post('/barrier/{action}')
def control_barrier(action: str):
    if action == 'arm':
        release.clear()
        barrier.update(enabled=True, reached=False, runId=None)
    elif action == 'release':
        release.set()
    return dict(barrier)


@router.get('/run/{run_id}')
def inspect_run(run_id: str):
    with SessionLocal() as db:
        run = db.get(AgentRun, run_id)
        return {'id': run.id, 'sessionId': run.session_id, 'status': run.status,
                'attempt': run.attempt, 'executionEpoch': run.execution_epoch,
                'versions': db.scalar(select(func.count()).select_from(ResumeVersion).where(ResumeVersion.run_id == run_id)),
                'operations': db.scalar(select(func.count()).select_from(ToolOperation).where(ToolOperation.run_id == run_id)),
                'events': [{'seq': row.seq, 'type': row.type, 'payload': row.payload} for row in db.scalars(
                    select(AgentRunEvent).where(AgentRunEvent.run_id == run_id).order_by(AgentRunEvent.seq))]}


from backend.app import app  # production lifespan and routes; test routes precede static mount
app.router.routes[0:0] = router.routes
