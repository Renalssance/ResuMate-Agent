"""SQL remains authoritative; only aggregate usage may be cached for 30 seconds."""
import json
from datetime import datetime

import pytest
from redis.exceptions import ConnectionError
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker

from backend.db.models import LlmUsageEvent
from backend.tests.career_fixtures import career_db, career_engine


class CacheBoundary:
    def __init__(self):
        self.values = {}
        self.writes = []
        self.fail_get = False
        self.fail_set = False

    async def get(self, key):
        if self.fail_get:
            raise ConnectionError('test disconnected')
        return self.values.get(key)

    async def set(self, key, value, *, ex):
        if self.fail_set:
            raise ConnectionError('test disconnected')
        self.values[key] = value
        self.writes.append((key, ex))


def insert_usage(db, user_id=1, task='tailoring', tokens=100, success=True):
    row = LlmUsageEvent(user_id=user_id, task=task, model='synthetic-model',
                       base_url='https://synthetic.invalid/v1', prompt_tokens=tokens - 10,
                       completion_tokens=10, total_tokens=tokens, success=success,
                       called_at=datetime(2026, 10, 30, 8, 0))
    db.add(row)
    db.commit()
    return row


@pytest.mark.asyncio
async def test_cached_summary_excludes_details_and_recent_calls_stay_current(career_db):
    from backend.services.dashboard_cache import DashboardCache
    insert_usage(career_db)
    cache = CacheBoundary()
    service = DashboardCache(cache, 'resumate:test')
    factory = sessionmaker(bind=career_db.get_bind())
    first = await service.usage_dashboard(1, factory)
    assert first.total_calls == 1
    encoded = json.loads(cache.values['resumate:test:stats:1'])
    assert 'recent_calls' not in encoded
    assert 'synthetic-model' not in json.dumps(encoded)
    assert cache.writes == [('resumate:test:stats:1', 30)]

    insert_usage(career_db, tokens=200, success=False)
    insert_usage(career_db, user_id=2, task='chat', tokens=300)
    second = await service.usage_dashboard(1, factory)
    assert second.total_calls == 1  # no invalidation in this direct SQL fixture
    assert [row.total_tokens for row in second.recent_calls] == [200, 100]
    other = await service.usage_dashboard(2, factory)
    assert other.total_calls == 1 and other.total_tokens == 300
    assert len(other.recent_calls) == 1


@pytest.mark.asyncio
async def test_twenty_reads_only_aggregate_once_but_read_recent_each_time(career_db):
    from backend.services.dashboard_cache import DashboardCache
    for i in range(15):
        insert_usage(career_db, tokens=100+i, success=i % 2 == 0)
    sql = []
    engine = career_db.get_bind()
    def observe(_conn, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith('SELECT'):
            sql.append(statement.lower())
    event.listen(engine, 'before_cursor_execute', observe)
    try:
        service = DashboardCache(CacheBoundary(), 'resumate:test')
        factory = sessionmaker(bind=engine)
        for _ in range(20):
            result = await service.usage_dashboard(1, factory)
            assert result.total_calls == 15
            assert result.successful_calls == 8 and result.failed_calls == 7
            assert result.total_tokens == sum(range(100, 115))
            assert len(result.recent_calls) == 12
        assert sum('count(' in statement for statement in sql) == 3
        assert sum('limit' in statement for statement in sql) == 20
    finally:
        event.remove(engine, 'before_cursor_execute', observe)


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['get', 'set', 'missing'])
async def test_cache_outage_returns_real_sql_dashboard(career_db, failure):
    from backend.services.dashboard_cache import DashboardCache
    insert_usage(career_db, tokens=200, success=False)
    boundary = CacheBoundary()
    boundary.fail_get = failure == 'get'
    boundary.fail_set = failure == 'set'
    result = await DashboardCache(None if failure == 'missing' else boundary, 'resumate:test').usage_dashboard(
        1, sessionmaker(bind=career_db.get_bind()))
    assert result.total_calls == 1 and result.failed_calls == 1
    assert result.recent_calls[0].total_tokens == 200


def test_record_commits_before_best_effort_invalidation(career_db, monkeypatch):
    from backend.services import dashboard_cache, llm_settings
    deleted = []
    class SyncCache:
        def delete(self, key):
            with sessionmaker(bind=career_db.get_bind())() as verify:
                assert verify.query(LlmUsageEvent).count() == 1
            deleted.append(key)
            raise ConnectionError('simulated cache outage after commit')
    monkeypatch.setattr(dashboard_cache, 'get_sync_redis', lambda: SyncCache())
    monkeypatch.setattr(dashboard_cache, 'redis_namespace', lambda: 'resumate:test')
    llm_settings.record_llm_usage(user_id=1, task='chat', model='test', base_url='',
                                  prompt_tokens=2, completion_tokens=1, db=career_db)
    assert deleted == ['resumate:test:stats:1']
    assert career_db.query(LlmUsageEvent).one().total_tokens == 3


@pytest.mark.asyncio
async def test_empty_user_summary_and_expired_computation_not_cached(career_db, monkeypatch):
    from backend.services import dashboard_cache
    ticks = iter([0, 31])
    monkeypatch.setattr(dashboard_cache, 'monotonic', lambda: next(ticks))
    boundary = CacheBoundary()
    result = await dashboard_cache.DashboardCache(boundary, 'resumate:test').usage_dashboard(
        2, sessionmaker(bind=career_db.get_bind()))
    assert result.total_calls == 0 and result.success_rate == 0
    assert result.last_called_at is None and result.daily == [] and result.by_task == []
    assert result.recent_calls == [] and boundary.writes == []


@pytest.mark.asyncio
async def test_usage_route_releases_auth_session_before_waiting_on_redis(career_db):
    from types import SimpleNamespace
    from backend.db.models import User
    from backend.routes.settings import get_llm_usage
    user = career_db.query(User).filter(User.id == 1).one()
    assert career_db.in_transaction()
    class ObservedCache(CacheBoundary):
        async def get(self, key):
            assert not career_db.in_transaction(), 'Auth SQL connection held during Redis wait'
            return await super().get(key)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        redis=SimpleNamespace(commands=ObservedCache(), namespace='resumate:test'))))
    result = await get_llm_usage(request, user, career_db)
    assert result.total_calls == 0
