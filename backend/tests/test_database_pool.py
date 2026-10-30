"""Each API process has a finite MySQL connection budget; idle work releases it."""
from contextlib import ExitStack
from time import monotonic

import pytest
from sqlalchemy import text
from sqlalchemy.exc import TimeoutError
from backend.db.database import build_engine
from backend.tests.career_fixtures import career_engine


def test_mysql_rejects_eleventh_checkout_within_five_second_budget(career_engine):
    if career_engine.dialect.name != 'mysql':
        pytest.skip('MySQL connection budget; SQLite behavior covered separately')
    engine = build_engine(career_engine.url.render_as_string(hide_password=False))
    try:
        with ExitStack() as stack:
            for _ in range(10):
                connection = stack.enter_context(engine.connect())
                assert connection.scalar(text('SELECT 1')) == 1
            started = monotonic()
            with pytest.raises(TimeoutError):
                stack.enter_context(engine.connect())
            assert 4.5 <= monotonic() - started < 6
        assert engine.pool.checkedout() == 0
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT 1')) == 1
    finally:
        engine.dispose()
