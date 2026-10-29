from __future__ import annotations

import asyncio
from collections import defaultdict
from uuid import uuid4

from fastapi import HTTPException

from backend.schemas.workflow import SseProgressEvent, TaskStatus


TERMINAL_STATUSES: set[TaskStatus] = {"success", "failed"}


class TaskProgressHub:
    def __init__(self) -> None:
        self._history: dict[str, list[SseProgressEvent]] = defaultdict(list)
        self._queues: dict[str, list[tuple[asyncio.AbstractEventLoop, asyncio.Queue[SseProgressEvent]]]] = defaultdict(list)
        self._last_progress: dict[str, int] = defaultdict(int)
        self._owners: dict[str, int] = {}

    def create_task(self, prefix: str = "task", *, user_id: int, task_id: str = "") -> str:
        task_id = task_id or f"{prefix}_{uuid4().hex}"
        owner_id = self._owners.get(task_id)
        if owner_id is not None and owner_id != user_id:
            raise HTTPException(status_code=404, detail="task not found")
        if owner_id is None:
            self._owners[task_id] = user_id
            self._history[task_id] = []
            self._last_progress[task_id] = 0
        return task_id

    def is_owned_by(self, task_id: str, user_id: int) -> bool:
        return self._owners.get(task_id) == user_id

    def publish(
        self,
        task_id: str | None,
        *,
        stage: str,
        status: TaskStatus,
        progress: int,
        message: str,
        document_id: str | None = None,
        filename: str | None = None,
        stage_progress: int | None = None,
        current: int | None = None,
        total: int | None = None,
        data: dict | None = None,
    ) -> None:
        if not task_id:
            return
        clamped_progress = max(0, min(100, progress))
        overall_progress = max(self._last_progress[task_id], clamped_progress)
        self._last_progress[task_id] = overall_progress
        event = SseProgressEvent(
            task_id=task_id,
            document_id=document_id,
            filename=filename,
            stage=stage,
            status=status,
            progress=overall_progress,
            overall_progress=overall_progress,
            stage_progress=None if stage_progress is None else max(0, min(100, stage_progress)),
            current=current,
            total=total,
            message=message,
            data=data or {},
        )
        self._history[task_id].append(event)
        for loop, queue in list(self._queues.get(task_id, [])):
            loop.call_soon_threadsafe(queue.put_nowait, event)

    async def stream(self, task_id: str):
        # 立即发送一个空注释，确保 HTTP 响应头能被 BaseHTTPMiddleware 立即发给客户端
        yield ": heartbeat\n\n"
        queue: asyncio.Queue[SseProgressEvent] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        item = (loop, queue)
        self._queues[task_id].append(item)
        try:
            for event in self._history.get(task_id, []):
                yield self._format(event)
                if event.status in TERMINAL_STATUSES:
                    return
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                yield self._format(event)
                if event.status in TERMINAL_STATUSES:
                    return
        finally:
            queues = self._queues.get(task_id, [])
            if item in queues:
                queues.remove(item)

    @staticmethod
    def _format(event: SseProgressEvent) -> str:
        return f"data: {event.model_dump_json(by_alias=True)}\n\n"


progress_hub = TaskProgressHub()
