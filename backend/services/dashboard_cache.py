"""Cache usage aggregates only; SQL details are read on every request."""
import logging
import math
from time import monotonic

from anyio import to_thread
from redis.exceptions import RedisError

from backend.infrastructure.redis_client import RedisUnavailable, get_sync_redis, redis_namespace
from backend.schemas.settings import LlmUsageDashboard, LlmUsageCall, LlmUsageSummary
from backend.services.llm_settings import load_recent_usage, load_usage_summary

logger = logging.getLogger(__name__)
SUMMARY_TTL = 30


def invalidate_usage_summary(user_id: int) -> None:
    try:
        get_sync_redis().delete(f'{redis_namespace()}:stats:{user_id}')
    except (RedisError, RedisUnavailable) as exc:
        # SQL has already committed: losing a cache deletion cannot undo a usage record.
        logger.warning('Usage cache invalidation unavailable user_id=%s error=%s',
                       user_id, type(exc).__name__)


class DashboardCache:
    def __init__(self, commands, namespace: str):
        self.commands = commands
        self.namespace = namespace

    async def usage_dashboard(self, user_id: int, session_factory) -> LlmUsageDashboard:
        key = f'{self.namespace}:stats:{user_id}'
        cached = None
        if self.commands is not None:
            try:
                cached = await self.commands.get(key)
            except RedisError as exc:
                logger.warning('Usage cache read unavailable error=%s', type(exc).__name__)
        summary = LlmUsageSummary.model_validate_json(cached) if cached else None
        if summary is None:
            started = monotonic()
            def read_summary():
                with session_factory() as db:
                    return load_usage_summary(db, user_id)
            summary = await to_thread.run_sync(read_summary)
            ttl = math.ceil(SUMMARY_TTL - (monotonic() - started))
            if self.commands is not None and ttl > 0:
                try:
                    await self.commands.set(key, summary.model_dump_json(), ex=ttl)
                except RedisError as exc:
                    logger.warning('Usage cache write unavailable error=%s', type(exc).__name__)

        def read_recent():
            with session_factory() as db:
                return [LlmUsageCall.model_validate(row) for row in load_recent_usage(db, user_id)]
        recent = await to_thread.run_sync(read_recent)
        return LlmUsageDashboard(**summary.model_dump(), recent_calls=recent)
