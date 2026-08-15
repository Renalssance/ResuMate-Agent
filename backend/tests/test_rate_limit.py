from backend.middleware.rate_limit import FixedWindowLimiter


def test_fixed_window_limit_and_expiry():
    limiter = FixedWindowLimiter()
    assert limiter.hit("auth:user:alice", limit=2, window_seconds=60, now=100) == 0
    assert limiter.hit("auth:user:alice", limit=2, window_seconds=60, now=101) == 0
    assert limiter.hit("auth:user:alice", limit=2, window_seconds=60, now=102) == 18
    assert limiter.hit("auth:user:alice", limit=2, window_seconds=60, now=121) == 0


def test_fixed_window_isolates_identities():
    limiter = FixedWindowLimiter()
    limiter.hit("auth:user:alice", limit=1, window_seconds=60, now=100)
    assert limiter.hit("auth:user:bob", limit=1, window_seconds=60, now=100) == 0
