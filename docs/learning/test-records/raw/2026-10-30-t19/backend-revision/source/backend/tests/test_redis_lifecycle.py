"""Process-owned Redis resources; these tests never need a listening Redis."""
from unittest.mock import AsyncMock, Mock

import pytest


def test_async_resources_keep_commands_and_subscriptions_on_separate_pools(monkeypatch):
    from backend.infrastructure import redis_client
    monkeypatch.setenv('REDIS_URL', 'redis://127.0.0.1:1/4')
    monkeypatch.setenv('RESUMATE_ENV', 'lifecycle-test')
    resources = redis_client.create_async_redis_resources()
    assert resources.namespace == 'resumate:lifecycle-test'
    assert redis_client.redis_namespace() == resources.namespace
    assert resources.commands.connection_pool is not resources.notifications.connection_pool
    command = resources.commands.connection_pool.connection_kwargs
    notifications = resources.notifications.connection_pool.connection_kwargs
    assert (command['socket_connect_timeout'], command['socket_timeout']) == (1, 2)
    assert command['retry'].get_retries() == 0
    assert command['db'] == 4
    assert notifications['socket_connect_timeout'] == 1
    assert notifications['socket_timeout'] is None
    assert notifications['retry'].get_retries() == 0


@pytest.mark.asyncio
async def test_async_resources_close_both_owned_pools_even_if_one_close_fails():
    from backend.infrastructure.redis_client import AsyncRedisResources
    commands = Mock(aclose=AsyncMock())
    notifications = Mock(aclose=AsyncMock(side_effect=RuntimeError('close failed')))
    resources = AsyncRedisResources(commands, notifications, 'resumate:test')
    with pytest.raises(RuntimeError, match='close failed'):
        await resources.aclose()
    notifications.aclose.assert_awaited_once()
    commands.aclose.assert_awaited_once()


def test_sync_resources_require_lifecycle_and_reuse_one_pool(monkeypatch):
    from backend.infrastructure import redis_client
    monkeypatch.setenv('REDIS_URL', 'redis://127.0.0.1:1/4')
    redis_client.close_sync_redis()
    with pytest.raises(redis_client.RedisUnavailable):
        redis_client.get_sync_redis()
    try:
        redis_client.init_sync_redis()
        first = redis_client.get_sync_redis()
        redis_client.init_sync_redis()
        assert redis_client.get_sync_redis() is first
        config = first.connection_pool.connection_kwargs
        assert (config['socket_connect_timeout'], config['socket_timeout']) == (1, 2)
        assert config['retry'].get_retries() == 0
        disconnect = Mock(wraps=first.connection_pool.disconnect)
        monkeypatch.setattr(first.connection_pool, 'disconnect', disconnect)
        redis_client.close_sync_redis()
        disconnect.assert_called_once()
        with pytest.raises(redis_client.RedisUnavailable):
            redis_client.get_sync_redis()
    finally:
        redis_client.close_sync_redis()


def test_sync_client_cannot_be_reused_by_a_forked_process(monkeypatch):
    from backend.infrastructure import redis_client
    redis_client.close_sync_redis()
    try:
        redis_client.init_sync_redis()
        parent = redis_client.get_sync_redis()
        parent_pid = redis_client.getpid()
        monkeypatch.setattr(redis_client, 'getpid', lambda: parent_pid + 1)
        with pytest.raises(redis_client.RedisUnavailable):
            redis_client.get_sync_redis()
        redis_client.init_sync_redis()
        assert redis_client.get_sync_redis() is not parent
    finally:
        redis_client.close_sync_redis()


@pytest.fixture
def tracked_api_resources(monkeypatch):
    from backend.infrastructure import redis_client
    from backend import app as app_module
    monkeypatch.setattr(app_module, 'init_db', lambda: None)
    monkeypatch.setenv('REDIS_URL', 'redis://127.0.0.1:1/0')
    redis_client.close_sync_redis()
    created = []
    original = redis_client.create_async_redis_resources
    def tracked_factory():
        resources = original()
        resources.commands.aclose = AsyncMock(wraps=resources.commands.aclose)
        resources.notifications.aclose = AsyncMock(wraps=resources.notifications.aclose)
        created.append(resources)
        return resources
    monkeypatch.setattr(redis_client, 'create_async_redis_resources', tracked_factory)
    yield app_module, created
    redis_client.close_sync_redis()


def test_api_lifespans_have_fresh_resources_and_close_them(tracked_api_resources):
    from fastapi.testclient import TestClient
    from backend.infrastructure import redis_client
    app_module, created = tracked_api_resources
    sync_clients = []
    for _ in range(2):
        application = app_module.create_app()
        with TestClient(application) as client:
            resources = application.state.redis
            assert resources is created[-1]
            assert type(application.state.rate_limiter).__name__ == 'RedisRateLimiter'
            sync_clients.append(redis_client.get_sync_redis())
            assert client.get('/healthz').status_code == 200
        resources.commands.aclose.assert_awaited_once()
        resources.notifications.aclose.assert_awaited_once()
        with pytest.raises(redis_client.RedisUnavailable):
            redis_client.get_sync_redis()
    assert created[0] is not created[1]
    assert sync_clients[0] is not sync_clients[1]


@pytest.mark.asyncio
async def test_api_lifespan_closes_resources_when_application_body_raises(tracked_api_resources):
    from backend.infrastructure import redis_client
    app_module, created = tracked_api_resources
    application = app_module.create_app()
    with pytest.raises(RuntimeError, match='application failed'):
        async with application.router.lifespan_context(application):
            assert application.state.redis is created[-1]
            raise RuntimeError('application failed')
    created[-1].commands.aclose.assert_awaited_once()
    created[-1].notifications.aclose.assert_awaited_once()
    with pytest.raises(redis_client.RedisUnavailable):
        redis_client.get_sync_redis()


def test_celery_child_lifecycle_resets_sql_and_owns_redis(monkeypatch):
    from celery.signals import worker_process_shutdown
    from backend import worker
    from backend.db.database import engine
    from backend.infrastructure import redis_client
    redis_client.close_sync_redis()
    dispose = Mock()
    monkeypatch.setattr(engine, 'dispose', dispose)
    try:
        worker.reset_connection_pool()
        dispose.assert_called_once_with(close=False)
        assert redis_client.get_sync_redis() is not None
        worker_process_shutdown.send(sender=None, pid=redis_client.getpid(), exitcode=0)
        with pytest.raises(redis_client.RedisUnavailable):
            redis_client.get_sync_redis()
    finally:
        redis_client.close_sync_redis()


def test_api_stops_interview_reader_before_closing_redis_pools(monkeypatch):
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from backend import app as app_module
    from backend.infrastructure import redis_client
    from backend.services import realtime_bus
    order = []
    async def started():
        order.append('reader.started')
    async def stopped():
        order.append('reader.stopped')
    async def closed():
        order.append('pools.closed')
    resources = SimpleNamespace(commands=object(), notifications=object(),
                                namespace='resumate:lifecycle', aclose=closed)
    hints = SimpleNamespace(start=started, aclose=stopped)
    constructor = Mock(return_value=hints)
    monkeypatch.setattr(app_module, 'init_db', lambda: None)
    monkeypatch.setattr(redis_client, 'create_async_redis_resources', lambda: resources)
    monkeypatch.setattr(realtime_bus, 'InterviewHints', constructor)
    application = app_module.create_app()
    with TestClient(application):
        assert application.state.interview_hints is hints
        assert order == ['reader.started']
    constructor.assert_called_once_with(resources.commands, resources.notifications, resources.namespace)
    assert order == ['reader.started', 'reader.stopped', 'pools.closed']


@pytest.mark.parametrize(('used', 'buffer', 'maximum', 'warned'), [
    (79, 0, 100, False), (80, 0, 100, True), (95, 20, 100, False), (95, 0, 0, False),
])
def test_capacity_warning_observes_dataset_threshold(monkeypatch, caplog, used, buffer, maximum, warned):
    from backend.infrastructure import redis_client
    client = Mock()
    client.info.return_value = {'used_memory': used, 'mem_not_counted_for_evict': buffer, 'maxmemory': maximum}
    monkeypatch.setattr(redis_client, 'get_sync_redis', lambda: client)
    monkeypatch.setenv('RESUMATE_ENV', 'capacity-test')
    redis_client.warn_redis_capacity()
    client.info.assert_called_once_with('memory')
    assert ('redis_capacity_high' in caplog.text) is warned
    if warned:
        assert 'resumate:capacity-test' in caplog.text
        assert 'used_bytes=80 max_bytes=100' in caplog.text


@pytest.mark.parametrize('failure', ['uninitialized', 'disconnected'])
def test_capacity_failure_is_reported_without_stopping_recovery(monkeypatch, caplog, failure):
    from redis.exceptions import ConnectionError
    from backend.infrastructure import redis_client
    error = redis_client.RedisUnavailable('not initialized') if failure == 'uninitialized' else ConnectionError('private connection details')
    monkeypatch.setattr(redis_client, 'get_sync_redis', Mock(side_effect=error))
    redis_client.warn_redis_capacity()
    assert 'redis_capacity_unavailable' in caplog.text
    assert 'private connection details' not in caplog.text
