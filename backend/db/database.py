import os
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import make_url
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
    url = make_url(database_url)
    if url.drivername == "mysql":
        url = url.set(drivername="mysql+pymysql")
    if url.get_backend_name() == "mysql" and "charset" not in url.query:
        url = url.update_query_dict({"charset": "utf8mb4"})
    return create_engine(url, pool_pre_ping=True)


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
    from backend.cloudbase import validate_runtime

    validate_runtime(DATABASE_URL)
    if os.getenv("CLOUDBASE_ENV_ID"):
        with engine.connect() as connection:
            connection.execute(text("SELECT id FROM users LIMIT 0"))
        return

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
        application_columns = {row[1] for row in connection.execute(text("PRAGMA table_info(job_applications)"))}
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
                    "CREATE TABLE IF NOT EXISTS job_application_schedules ("
                    "id INTEGER NOT NULL PRIMARY KEY, "
                    "application_id INTEGER NOT NULL, "
                    "status VARCHAR(40) NOT NULL, "
                    "title VARCHAR(255) NOT NULL, "
                    "starts_at DATETIME NOT NULL, "
                    "ends_at DATETIME NOT NULL, "
                    "note TEXT NOT NULL DEFAULT '', "
                    "completed_event_id INTEGER, "
                    "created_at DATETIME NOT NULL, "
                    "updated_at DATETIME NOT NULL, "
                    "FOREIGN KEY(application_id) REFERENCES job_applications (id) ON DELETE CASCADE, "
                    "FOREIGN KEY(completed_event_id) REFERENCES job_application_status_events (id) ON DELETE SET NULL"
                    ")"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_job_application_schedules_application_id "
                    "ON job_application_schedules (application_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_job_application_schedules_status "
                    "ON job_application_schedules (status)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_job_application_schedules_starts_at "
                    "ON job_application_schedules (starts_at)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_job_application_schedules_ends_at "
                    "ON job_application_schedules (ends_at)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_job_application_schedules_completed_event_id "
                    "ON job_application_schedules (completed_event_id)"
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
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS user_llm_settings ("
                "id INTEGER NOT NULL PRIMARY KEY, "
                "user_id INTEGER NOT NULL UNIQUE, "
                "api_key TEXT NOT NULL DEFAULT '', "
                "base_url VARCHAR(1024) NOT NULL DEFAULT '', "
                "model VARCHAR(255) NOT NULL DEFAULT '', "
                "max_tokens INTEGER, "
                "request_timeout_seconds FLOAT, "
                "created_at DATETIME NOT NULL, "
                "updated_at DATETIME NOT NULL, "
                "FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE"
                ")"
            )
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_user_llm_settings_user_id ON user_llm_settings (user_id)"))
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS llm_usage_events ("
                "id INTEGER NOT NULL PRIMARY KEY, "
                "user_id INTEGER NOT NULL, "
                "task VARCHAR(120) NOT NULL DEFAULT '', "
                "model VARCHAR(255) NOT NULL DEFAULT '', "
                "base_url VARCHAR(1024) NOT NULL DEFAULT '', "
                "prompt_tokens INTEGER NOT NULL DEFAULT 0, "
                "completion_tokens INTEGER NOT NULL DEFAULT 0, "
                "total_tokens INTEGER NOT NULL DEFAULT 0, "
                "success BOOLEAN NOT NULL DEFAULT 1, "
                "error_type VARCHAR(120) NOT NULL DEFAULT '', "
                "elapsed_ms INTEGER NOT NULL DEFAULT 0, "
                "called_at DATETIME NOT NULL, "
                "FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE"
                ")"
            )
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_llm_usage_events_user_id ON llm_usage_events (user_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_llm_usage_events_task ON llm_usage_events (task)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_llm_usage_events_success ON llm_usage_events (success)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_llm_usage_events_called_at ON llm_usage_events (called_at)"))
