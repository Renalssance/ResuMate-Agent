"""Isolated, disposable noeviction Redis; never targets the main broker."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
import os

os.environ['REDIS_URL'] = 'redis://redis-oom:6379/0'
logging.basicConfig(level=logging.WARNING)

from redis.exceptions import OutOfMemoryError
from backend.db.database import SessionLocal
from backend.infrastructure.redis_client import (
    RedisUnavailable, close_sync_redis, create_async_redis_resources,
    init_sync_redis, warn_redis_capacity,
)
from backend.middleware.rate_limit import RedisRateLimiter
from backend.services.dashboard_cache import DashboardCache
from backend.services.ws_tickets import WsTickets


async def main():
    init_sync_redis()
    resources = create_async_redis_resources()
    client = resources.commands
    try:
        await client.set('queue-marker', 'must-survive')
        for index in range(200):
            try:
                await client.set(f'fill:{index}', b'x' * 65536)
            except OutOfMemoryError:
                break
        else:
            raise AssertionError('Did not reach configured memory ceiling')
        # Make every growing write fail deterministically despite minor freed buffers.
        await client.config_set('maxmemory', 1)
        info = await client.info('memory')
        warn_redis_capacity()
        result = {'markerPresent': await client.get('queue-marker') == b'must-survive',
                  'policy': (await client.config_get('maxmemory-policy'))['maxmemory-policy'],
                  'usedMemory': info['used_memory'], 'maxmemory': info['maxmemory'],
                  'limiterUnavailable': False, 'ticketUnavailable': False}
        try:
            await RedisRateLimiter(client, resources.namespace).allow_request(1, 'run')
        except RedisUnavailable:
            result['limiterUnavailable'] = True
        try:
            await WsTickets(client, resources.namespace).issue_ws_ticket(1, 'interview-1', datetime.now(timezone.utc) + timedelta(seconds=60))
        except RedisUnavailable:
            result['ticketUnavailable'] = True
        dashboard = await DashboardCache(client, resources.namespace).usage_dashboard(1, SessionLocal)
        result['cacheCalls'] = dashboard.total_calls
        print(json.dumps(result))
    finally:
        await resources.aclose()
        close_sync_redis()


asyncio.run(main())
