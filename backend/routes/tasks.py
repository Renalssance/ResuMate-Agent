from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.db.models import User
from backend.services.progress import progress_hub

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/{task_id}/events")
async def task_events(
    task_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    user_id = current_user.id
    if not progress_hub.is_owned_by(task_id, user_id):
        raise HTTPException(status_code=404, detail="task not found")
    db.close()
    return StreamingResponse(
        progress_hub.stream(task_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
