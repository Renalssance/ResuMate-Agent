from sqlalchemy import text

from backend.db.database import build_engine, ensure_sqlite_schema


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


def test_ensure_sqlite_schema_adds_document_content_hash_to_existing_tables(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'old-resumate.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE resumes (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE job_descriptions (id INTEGER PRIMARY KEY)"))

    ensure_sqlite_schema(engine)

    with engine.connect() as connection:
        resume_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(resumes)"))
        }
        jd_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(job_descriptions)"))
        }
    assert "content_hash" in resume_columns
    assert "content_hash" in jd_columns
