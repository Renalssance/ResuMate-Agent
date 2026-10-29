from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, sessionmaker

from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.db.models import User
from backend.services import agent_runs, run_events

router = APIRouter(prefix='/api/tasks', tags=['tasks'])


@router.get('/{task_id}/events')
def task_events(task_id: str, after: int = Query(default=0, ge=0),
                last_event_id: int | None = Header(default=None, ge=0),
                current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = current_user.id
    cursor = max(after, last_event_id or 0)
    try:
        run_events.read_page(db, user_id, task_id, cursor)
    except agent_runs.RunError as error:
        raise HTTPException(status_code=error.status, detail=error.message) from error
    session_factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    db.close()
    return StreamingResponse(
        run_events.stream_task_events(session_factory, user_id, task_id, cursor),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )
