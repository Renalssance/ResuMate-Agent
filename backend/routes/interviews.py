"""HTTP transport for durable interview commands; admission waits hold no SQL session."""
import logging

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session, sessionmaker

from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.db.models import User
from backend.infrastructure.redis_client import RedisUnavailable
from backend.middleware.rate_limit import require_run_capacity
from backend.routes.agent_runs import RunRoute
from backend.schemas.interviews import ConfirmInterviewMemory, InterviewCommand, InterviewCreate
from backend.services import interviews, interview_commands
from backend.services.interview_events import read_interview_events
from backend.services.realtime_bus import publish_interview_hint_sync
from backend.services.run_delivery import publish_run

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/interviews', tags=['interviews'], route_class=RunRoute)


def _factory_and_close(db):
    factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    db.close()
    return factory


def _notify(interview_id, last_seq):
    try:
        publish_interview_hint_sync(interview_id, last_seq)
    except RedisUnavailable:
        logger.warning('Interview %s committed; notification unavailable', interview_id)


@router.post('', status_code=202)
async def create(body: InterviewCreate, request: Request,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = user.id
    replay = interviews.find_create_replay(db, user_id, body)
    factory = _factory_and_close(db)
    if replay is not None:
        return replay
    await require_run_capacity(request, user)
    def accept():
        with factory() as fresh:
            result = interviews.create_interview(fresh, user_id, body)
        publish_run(result['runId'])
        return result
    return await run_in_threadpool(accept)


@router.get('/{interview_id}')
def snapshot(interview_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return interviews.interview_snapshot(db, user.id, interview_id)


@router.post('/{interview_id}/commands', status_code=202)
async def command(interview_id: str, body: InterviewCommand, request: Request,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = user.id
    replay = interview_commands.find_command_replay(db, user_id, interview_id, body)
    factory = _factory_and_close(db)
    if replay is not None:
        return replay
    if body.type in ('answer.submit', 'generation.retry'):
        await require_run_capacity(request, user)
    def accept():
        with factory() as fresh:
            result = interview_commands.handle_command(fresh, user_id, interview_id, body)
        if body.type in ('answer.submit', 'generation.retry'):
            publish_run(result['resultRef'])
        _notify(interview_id, result['acceptedSeq'])
        return result
    return await run_in_threadpool(accept)


@router.get('/{interview_id}/events')
def events(interview_id: str, after: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=100),
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = user.id
    factory = _factory_and_close(db)
    return read_interview_events(factory, user_id, interview_id, after, limit)


@router.post('/{interview_id}/turns/{turn_index}/memory')
def confirm_memory(interview_id: str, turn_index: int, body: ConfirmInterviewMemory,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return interviews.confirm_feedback_memory(db, user.id, interview_id, turn_index, confirmed=body.confirmed)
