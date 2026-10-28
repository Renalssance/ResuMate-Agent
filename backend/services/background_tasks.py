"""Run accepted HTTP tasks with a database session owned by the worker."""
from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse

from backend.db.database import SessionLocal
from backend.db.models import User
from backend.services.progress import progress_hub


def submit_task(background_tasks: BackgroundTasks, progress_task_id: str, user_id: int, handler, **kwargs):
    background_tasks.add_task(_run_task, progress_task_id, user_id, handler, kwargs)
    return JSONResponse(
        status_code=202,
        content={"taskId": progress_task_id},
        headers={"Preference-Applied": "respond-async"},
    )


def _run_task(task_id: str, user_id: int, handler, kwargs: dict) -> None:
    try:
        with SessionLocal() as db:
            user = db.get(User, user_id)
            if user is None:
                raise ValueError("user not found")
            handler(current_user=user, db=db, **kwargs)
    except Exception as exc:
        message = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
        progress_hub.publish(task_id, stage="failed", status="failed", progress=100, message=message)
