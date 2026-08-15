from sqlalchemy import text

from backend.db.database import build_engine


def test_build_engine_enables_sqlite_safety_pragmas(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'resumate.db'}")
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert connection.execute(text("PRAGMA journal_mode")).scalar_one().lower() == "wal"
        assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 30000


def test_build_engine_creates_parent_directory(tmp_path):
    database = tmp_path / "nested" / "resumate.db"
    engine = build_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE check_table (id INTEGER PRIMARY KEY)"))
    assert database.exists()
