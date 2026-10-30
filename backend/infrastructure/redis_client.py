"""Redis clients belong to an API lifecycle or one Celery child process."""
from dataclasses import dataclass
import logging
import os
from os import getpid

from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.asyncio.retry import Retry as AsyncRetry
from redis.backoff import NoBackoff
from redis.retry import Retry
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class RedisUnavailable(RuntimeError):
    """A required Redis operation or its process resources are unavailable."""


def redis_namespace() -> str:
    return f"resumate:{os.getenv('RESUMATE_ENV') or 'local'}"


def _redis_url() -> str:
    return os.getenv('REDIS_URL') or 'redis://127.0.0.1:6379/0'


@dataclass
class AsyncRedisResources:
    commands: AsyncRedis
    notifications: AsyncRedis
    namespace: str

    async def aclose(self) -> None:
        try:
            await self.notifications.aclose()
        finally:
            await self.commands.aclose()


def create_async_redis_resources() -> AsyncRedisResources:
    # from_url creates owned pools without making a network connection. SQL-only
    # requests must remain available when Redis is down at API startup.
    commands = AsyncRedis.from_url(
        _redis_url(), socket_connect_timeout=1, socket_timeout=2,
        retry=AsyncRetry(NoBackoff(), 0), retry_on_error=[],
    )
    notifications = AsyncRedis.from_url(
        _redis_url(), socket_connect_timeout=1, socket_timeout=None,
        retry=AsyncRetry(NoBackoff(), 0), retry_on_error=[],
    )
    return AsyncRedisResources(commands, notifications, redis_namespace())


_sync_client: Redis | None = None
_sync_pid: int | None = None


def init_sync_redis() -> None:
    """Initialize once per process, replacing a client inherited across fork."""
    global _sync_client, _sync_pid
    if _sync_client is not None and _sync_pid == getpid():
        return
    close_sync_redis()
    _sync_client = Redis.from_url(
        _redis_url(), socket_connect_timeout=1, socket_timeout=2,
        retry=Retry(NoBackoff(), 0), retry_on_error=[],
    )
    _sync_pid = getpid()


def get_sync_redis() -> Redis:
    if _sync_client is None or _sync_pid != getpid():
        raise RedisUnavailable('Redis process resources are not initialized')
    return _sync_client


def close_sync_redis() -> None:
    global _sync_client, _sync_pid
    client, _sync_client = _sync_client, None
    _sync_pid = None
    if client is not None:
        client.close()


def warn_redis_capacity() -> None:
    """The existing recovery scan reports capacity without depending on it."""
    try:
        memory = get_sync_redis().info('memory')
    except (RedisError, RedisUnavailable) as exc:
        logger.warning('redis_capacity_unavailable namespace=%s error=%s',
                       redis_namespace(), type(exc).__name__)
        return
    maximum = int(memory.get('maxmemory', 0))
    used = max(0, int(memory['used_memory']) - int(memory.get('mem_not_counted_for_evict', 0)))
    if maximum > 0 and used / maximum >= 0.8:
        logger.warning('redis_capacity_high namespace=%s used_bytes=%d max_bytes=%d ratio=%.3f',
                       redis_namespace(), used, maximum, used / maximum)
