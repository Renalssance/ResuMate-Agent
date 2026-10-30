"""Redis broadcasts are wake-up hints; durable interview events live in SQL."""
import asyncio
from contextlib import asynccontextmanager, suppress
import json
import logging

from redis.exceptions import RedisError

from backend.infrastructure.redis_client import (
    RedisUnavailable, get_sync_redis, redis_namespace,
)

logger = logging.getLogger(__name__)


def _payload(interview_id: str, last_seq: int) -> str:
    return json.dumps({'interviewId': interview_id, 'lastSeq': last_seq})


class InterviewHints:
    def __init__(self, commands, notifications, namespace: str):
        self.commands = commands
        self.notifications = notifications
        self.channel = f'{namespace}:interview-hints'
        self._watchers: dict[str, set[asyncio.Event]] = {}
        self._reader: asyncio.Task | None = None

    async def start(self) -> None:
        # Redis availability must not block API startup or ordinary SQL reads.
        self._reader = asyncio.create_task(self._read(), name='interview-hints')

    async def aclose(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
            with suppress(asyncio.CancelledError):
                await self._reader
            self._reader = None

    @asynccontextmanager
    async def watch(self, interview_id: str):
        event = asyncio.Event()
        watchers = self._watchers.setdefault(interview_id, set())
        watchers.add(event)
        try:
            yield event
        finally:
            watchers.remove(event)
            if not watchers:
                del self._watchers[interview_id]

    async def publish_interview_hint(self, interview_id: str, last_seq: int) -> None:
        try:
            await self.commands.publish(self.channel, _payload(interview_id, last_seq))
        except RedisError as exc:
            raise RedisUnavailable('Interview notification unavailable') from exc

    async def _read(self) -> None:
        while True:
            try:
                async with self.notifications.pubsub() as subscription:
                    await subscription.subscribe(self.channel)
                    while True:
                        message = await subscription.get_message(
                            ignore_subscribe_messages=True, timeout=1)
                        if message is not None:
                            hint = json.loads(message['data'])
                            for event in self._watchers.get(hint['interviewId'], ()):
                                event.set()
            except RedisError as exc:
                logger.warning('interview_hint_disconnected channel=%s error=%s',
                               self.channel, type(exc).__name__)
                await asyncio.sleep(1)


def publish_interview_hint_sync(interview_id: str, last_seq: int) -> None:
    try:
        get_sync_redis().publish(f'{redis_namespace()}:interview-hints',
                                 _payload(interview_id, last_seq))
    except RedisError as exc:
        raise RedisUnavailable('Interview notification unavailable') from exc
