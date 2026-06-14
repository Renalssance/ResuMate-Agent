from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.services.progress import progress_hub

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/{task_id}/events")
async def task_events(task_id: str):
    return StreamingResponse(
        progress_hub.stream(task_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
