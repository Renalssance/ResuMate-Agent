"""Redis adapter contract; actual Lua atomicity is tested against Redis separately."""
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ConnectionError, OutOfMemoryError, TimeoutError

from backend.middleware import rate_limit

pytestmark = pytest.mark.real_redis


def service(commands, namespace='resumate:limiter-unit'):
    assert hasattr(rate_limit, 'RedisRateLimiter'), 'production limiter must use injected Redis commands'
    return rate_limit.RedisRateLimiter(commands, namespace)


@pytest.mark.asyncio
@pytest.mark.parametrize(('scope', 'limit', 'subject'), [('auth', 5, 'ip:203.0.113.7'), ('chat', 20, 7), ('run', 10, 7)])
async def test_scope_limit_and_remaining_ttl_use_one_eval(scope, limit, subject):
    commands = AsyncMock()
    commands.eval.side_effect = [[limit, 28001], [limit + 1, 11301]]
    limiter = service(commands)
    assert await limiter.allow_request(subject, scope) == (True, 0)
    assert await limiter.allow_request(subject, scope) == (False, 12)
    assert commands.eval.await_count == 2
    for call in commands.eval.await_args_list:
        script, numkeys, key, seconds = call.args
        assert numkeys == 1
        assert key == f'resumate:limiter-unit:rl:{scope}:{subject}'
        assert seconds == 60
    assert commands.incr.await_count == 0 and commands.expire.await_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('ttl', [0, -1, 1, 1000])
async def test_rejected_response_has_at_least_one_second_retry_after(ttl):
    commands = AsyncMock()
    commands.eval.return_value = [11, ttl]
    assert await service(commands).allow_request(7, 'run') == (False, 1)
    assert commands.eval.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [ConnectionError('down'), TimeoutError('lost reply'), OutOfMemoryError('OOM')])
async def test_redis_failure_is_unavailable_without_retry_or_local_allow(error):
    commands = AsyncMock()
    commands.eval.side_effect = error
    limiter = service(commands)
    from backend.infrastructure.redis_client import RedisUnavailable
    with pytest.raises(RedisUnavailable):
        await limiter.allow_request(7, 'run')
    assert commands.eval.await_count == 1


@pytest.mark.asyncio
async def test_different_users_scopes_and_namespaces_use_distinct_redis_keys():
    commands = AsyncMock()
    commands.eval.return_value = [1, 60000]
    first, second = service(commands), service(commands, 'resumate:another-env')
    for limiter, subject, scope in [(first, 7, 'run'), (first, 8, 'run'), (first, 7, 'chat'), (second, 7, 'run')]:
        assert await limiter.allow_request(subject, scope) == (True, 0)
    assert len({call.args[2] for call in commands.eval.await_args_list}) == 4
