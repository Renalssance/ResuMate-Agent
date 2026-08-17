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
