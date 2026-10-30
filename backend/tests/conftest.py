import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///data/test-resumate.db"
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import pytest


class ControlledRateLimiter:
    """HTTP business-test injection, deliberately not a Redis/window simulator."""
    def __init__(self):
        self.result = (True, 0)
        self.error = None
        self.calls = []

    async def allow_request(self, subject, scope):
        self.calls.append((subject, scope))
        if self.error is not None:
            raise self.error
        return self.result


def pytest_configure(config):
    config.addinivalue_line('markers', 'real_redis: exercise Redis resources without the controlled limiter')


@pytest.fixture(autouse=True)
def controlled_rate_limiter(request, monkeypatch):
    if request.node.get_closest_marker('real_redis'):
        yield None
        return
    from backend.middleware import rate_limit
    service = ControlledRateLimiter()
    monkeypatch.setattr(rate_limit, 'get_rate_limiter', lambda request: service)
    yield service
