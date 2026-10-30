"""Load-only observers. All measured public routes are the real application routes."""
import os
import resource
import socket
import threading
from time import monotonic_ns

from fastapi import APIRouter, Depends
from sqlalchemy import event
from backend.auth.security import get_current_user
from backend.db.database import engine, SessionLocal
from backend.db.models import User
from backend.services.run_events import append_event

router = APIRouter(prefix='/__load')
lock = threading.Lock()
counters = {'checked_out': 0, 'peak_checked_out': 0, 'sql': 0, 'streams': 0, 'peak_streams': 0}

@event.listens_for(engine, 'checkout')
def checked_out(*_):
    with lock:
        counters['checked_out'] += 1
        counters['peak_checked_out'] = max(counters['peak_checked_out'], counters['checked_out'])

@event.listens_for(engine, 'checkin')
def checked_in(*_):
    with lock:
        counters['checked_out'] -= 1

@event.listens_for(engine, 'before_cursor_execute')
def query(*_):
    with lock:
        counters['sql'] += 1

@router.get('/metrics')
def metrics():
    with lock:
        stats = dict(counters)
    return {**stats, 'hostname': socket.gethostname(), 'pid': os.getpid(),
            'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'rss_kib': int(next(line.split()[1] for line in open('/proc/self/status') if line.startswith('VmRSS:'))),
            'pool': engine.pool.status()}

@router.post('/append')
def append(body: dict, user: User = Depends(get_current_user)):
    from backend.db.agent_models import AgentRun
    commits = []
    for run_id in body['runIds']:
        with SessionLocal() as db:
            run = db.get(AgentRun, run_id)
            if run is None or run.user_id != user.id:
                raise ValueError('Unknown load Run')
            row = append_event(db, run_id, 'assistant.delta', {'text': body.get('text', 'load event')})
            seq = row.seq
            db.commit()
            committed_ns = monotonic_ns()
        commits.append({'run_id': run_id, 'seq': seq, 'committed_ns': committed_ns})
    return commits

class StreamCounts:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        streamed = scope['type'] == 'http' and scope.get('path', '').endswith('/events')
        if streamed:
            with lock:
                counters['streams'] += 1
                counters['peak_streams'] = max(counters['peak_streams'], counters['streams'])
        try:
            await self.app(scope, receive, send)
        finally:
            if streamed:
                with lock:
                    counters['streams'] -= 1

from backend.app import app
app.router.routes[0:0] = router.routes
app.add_middleware(StreamCounts)
