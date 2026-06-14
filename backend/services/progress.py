from __future__ import annotations

import asyncio
from collections import defaultdict
from uuid import uuid4

from backend.schemas.workflow import SseProgressEvent, TaskStatus


TERMINAL_STATUSES: set[TaskStatus] = {"success", "failed"}


class TaskProgressHub:
    def __init__(self) -> None:
        self._history: dict[str, list[SseProgressEvent]] = defaultdict(list)
        self._queues: dict[str, list[asyncio.Queue[SseProgressEvent]]] = defaultdict(list)

    def create_task(self, prefix: str = "task") -> str:
        task_id = f"{prefix}_{uuid4().hex}"
        self._history[task_id] = []
        return task_id

    def publish(
        self,
        task_id: str | None,
        *,
        stage: str,
        status: TaskStatus,
        progress: int,
        message: str,
        data: dict | None = None,
    ) -> None:
        if not task_id:
            return
        event = SseProgressEvent(
            task_id=task_id,
            stage=stage,
            status=status,
            progress=max(0, min(100, progress)),
            message=message,
            data=data or {},
        )
        self._history[task_id].append(event)
        for queue in list(self._queues.get(task_id, [])):
            queue.put_nowait(event)

    async def stream(self, task_id: str):
        queue: asyncio.Queue[SseProgressEvent] = asyncio.Queue()
        self._queues[task_id].append(queue)
        try:
            for event in self._history.get(task_id, []):
                yield self._format(event)
                if event.status in TERMINAL_STATUSES:
                    return
            while True:
                event = await queue.get()
                yield self._format(event)
                if event.status in TERMINAL_STATUSES:
                    return
        finally:
            queues = self._queues.get(task_id, [])
            if queue in queues:
                queues.remove(queue)

    @staticmethod
    def _format(event: SseProgressEvent) -> str:
        return f"data: {event.model_dump_json(by_alias=True)}\n\n"


progress_hub = TaskProgressHub()
