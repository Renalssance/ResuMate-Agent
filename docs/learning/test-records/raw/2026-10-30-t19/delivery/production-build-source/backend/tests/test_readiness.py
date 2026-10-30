"""Readiness checks real SQL and the Redis boundary; liveness never needs either."""
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from backend.tests.career_fixtures import career_engine


@pytest.mark.parametrize('dependency', ['ready', 'sql_down', 'redis_down'])
def test_readiness_requires_sql_and_redis_without_exposing_credentials(career_engine, monkeypatch, dependency):
    from backend import app as app_module
    secret = 'synthetic-connection-password'
    class Redis:
        async def ping(self):
            if dependency == 'redis_down': raise RuntimeError(secret)
            return True
    class BrokenEngine:
        def connect(self): raise RuntimeError(secret)
    monkeypatch.setattr(app_module, 'engine', BrokenEngine() if dependency == 'sql_down' else career_engine, raising=False)
    application = app_module.create_app()
    application.state.redis = SimpleNamespace(commands=Redis())
    client = TestClient(application)
    try:
        response = client.get('/readyz')
        assert response.status_code == (200 if dependency == 'ready' else 503)
        assert response.json() == {'status': 'ready' if dependency == 'ready' else 'not_ready'}
        assert secret not in response.text
        assert client.get('/healthz').status_code == 200
    finally:
        client.close()
