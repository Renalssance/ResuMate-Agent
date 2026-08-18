import os
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker


DEFAULT_DATABASE_URL = "sqlite:///data/resumate.db"
DATABASE_URL = os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL


def build_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite:///"):
        database_path = Path(database_url.removeprefix("sqlite:///"))
        database_path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False, "timeout": 30},
        )

        @event.listens_for(engine, "connect")
        def _configure_sqlite(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

        return engine
    return create_engine(database_url, pool_pre_ping=True)


engine = build_engine(DATABASE_URL)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from backend.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_sqlite_schema(engine)


def ensure_sqlite_schema(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        for table_name in ("resumes", "job_descriptions"):
            columns = {
                row[1]
                for row in connection.execute(text(f"PRAGMA table_info({table_name})"))
            }
            if columns and "content_hash" not in columns:
                connection.execute(
                    text(
                        f"ALTER TABLE {table_name} "
                        "ADD COLUMN content_hash VARCHAR(64) NOT NULL DEFAULT ''"
                    )
                )
        application_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(job_applications)"))
        }
        if application_columns and "resume_id" not in application_columns:
            connection.execute(text("ALTER TABLE job_applications ADD COLUMN resume_id INTEGER"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_job_applications_resume_id ON job_applications (resume_id)"))
        if application_columns:
            connection.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS job_application_status_events ("
                    "id INTEGER NOT NULL PRIMARY KEY, "
                    "application_id INTEGER NOT NULL, "
                    "status VARCHAR(40) NOT NULL, "
                    "changed_at DATETIME NOT NULL, "
                    "note TEXT NOT NULL DEFAULT '', "
                    "created_at DATETIME NOT NULL, "
                    "FOREIGN KEY(application_id) REFERENCES job_applications (id) ON DELETE CASCADE"
                    ")"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_job_application_status_events_application_id "
                    "ON job_application_status_events (application_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_job_application_status_events_status "
                    "ON job_application_status_events (status)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_job_application_status_events_changed_at "
                    "ON job_application_status_events (changed_at)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO job_application_status_events "
                    "(application_id, status, changed_at, note, created_at) "
                    "SELECT app.id, app.status, app.updated_at, '', app.updated_at "
                    "FROM job_applications app "
                    "WHERE NOT EXISTS ("
                    "SELECT 1 FROM job_application_status_events event "
                    "WHERE event.application_id = app.id"
                    ")"
                )
            )
