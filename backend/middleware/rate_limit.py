"""Shared admission limits; Redis failures never fall back to local counters."""
import logging
import math

from fastapi import Depends, HTTPException, Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from backend.auth.security import get_current_user
from backend.db.models import User
from backend.infrastructure.redis_client import RedisUnavailable


logger = logging.getLogger(__name__)
LIMITS = {'auth': 5, 'chat': 20, 'run': 10}
WINDOW_SECONDS = 60
INCREMENT_WINDOW = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
local ttl = redis.call('PTTL', KEYS[1])
return {count, ttl}
"""


class RedisRateLimiter:
    def __init__(self, commands: Redis, namespace: str):
        self.commands = commands
        self.namespace = namespace

    async def allow_request(self, subject: int | str, scope: str) -> tuple[bool, int]:
        limit = LIMITS[scope]
        key = f'{self.namespace}:rl:{scope}:{subject}'
        try:
            count, ttl = await self.commands.eval(INCREMENT_WINDOW, 1, key, WINDOW_SECONDS)
        except RedisError as exc:
            raise RedisUnavailable('限流服务暂不可用') from exc
        if count <= limit:
            return True, 0
        return False, max(1, math.ceil(ttl / 1000))


def get_rate_limiter(request: Request) -> RedisRateLimiter:
    try:
        return request.app.state.rate_limiter
    except AttributeError as exc:
        raise RedisUnavailable('限流服务未初始化') from exc


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return 'unknown'


async def _enforce_limit(request: Request, subject: int | str, scope: str) -> None:
    try:
        allowed, retry_after = await get_rate_limiter(request).allow_request(subject, scope)
    except RedisUnavailable as exc:
        raise HTTPException(status_code=503, detail='限流服务暂不可用') from exc
    if not allowed:
        logger.warning('Rate limit hit: scope=%s subject=%s path=%s', scope, subject, request.url.path)
        raise HTTPException(status_code=429, detail='请求过于频繁', headers={'Retry-After': str(retry_after)})


async def require_auth_capacity(request: Request) -> None:
    await _enforce_limit(request, f'ip:{get_client_ip(request)}', 'auth')


async def require_chat_capacity(request: Request, user: User = Depends(get_current_user)) -> None:
    await _enforce_limit(request, user.id, 'chat')


async def require_run_capacity(request: Request, user: User = Depends(get_current_user)) -> None:
    await _enforce_limit(request, user.id, 'run')
