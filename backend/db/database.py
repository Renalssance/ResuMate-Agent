import os
from collections.abc import Iterable

from sqlalchemy import Column, Engine, Index, create_engine, inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.schema import CreateColumn, CreateIndex

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/langchain_app",
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()

ADDITIVE_SCHEMA_COLUMNS = {
    "resumes": ("document_size", "parse_status"),
    "job_descriptions": ("filename", "file_path", "document_size", "parse_status"),
    "match_results": ("report_json",),
}
ADDITIVE_SCHEMA_INDEXES = {
    "resumes": ("ix_resumes_parse_status",),
    "job_descriptions": ("ix_job_descriptions_parse_status",),
}


def _missing_additive_columns(bind: Engine) -> Iterable[tuple[str, Column]]:
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for table_name, column_names in ADDITIVE_SCHEMA_COLUMNS.items():
        if table_name not in existing_tables:
            continue
        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        table = Base.metadata.tables[table_name]
        for column_name in column_names:
            if column_name not in existing_columns:
                yield table_name, table.columns[column_name]


def _missing_additive_indexes(bind: Engine) -> Iterable[Index]:
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for table_name, index_names in ADDITIVE_SCHEMA_INDEXES.items():
        if table_name not in existing_tables:
            continue
        existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
        table_indexes = {index.name: index for index in Base.metadata.tables[table_name].indexes}
        for index_name in index_names:
            if index_name not in existing_indexes:
                yield table_indexes[index_name]


def _is_duplicate_schema_error(error: Exception, dialect_name: str, object_kind: str) -> bool:
    original = getattr(error, "orig", error)
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    if dialect_name == "postgresql":
        expected_sqlstate = "42701" if object_kind == "column" else "42P07"
        return sqlstate == expected_sqlstate
    if dialect_name == "sqlite":
        message = str(original).lower()
        if object_kind == "column":
            return "duplicate column name:" in message
        return "index " in message and " already exists" in message
    return False


def _execute_additive_ddl(
    bind: Engine, ddl: str, *, object_kind: str, object_exists
) -> None:
    try:
        with bind.begin() as connection:
            connection.execute(text(ddl))
    except (OperationalError, ProgrammingError) as error:
        if not _is_duplicate_schema_error(error, bind.dialect.name, object_kind):
            raise
        if not object_exists():
            raise


def _column_exists(bind: Engine, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspect(bind).get_columns(table_name)}


def _index_exists(bind: Engine, table_name: str, index_name: str) -> bool:
    return index_name in {index["name"] for index in inspect(bind).get_indexes(table_name)}


def initialize_additive_schema(bind: Engine) -> None:
    """Add newly introduced local columns without replacing existing tables."""
    missing_columns = list(_missing_additive_columns(bind))
    for table_name, column in missing_columns:
        quoted_table = bind.dialect.identifier_preparer.quote(table_name)
        column_ddl = CreateColumn(column).compile(dialect=bind.dialect)
        _execute_additive_ddl(
            bind,
            f"ALTER TABLE {quoted_table} ADD COLUMN {column_ddl}",
            object_kind="column",
            object_exists=lambda table_name=table_name, column=column: _column_exists(
                bind, table_name, column.name
            ),
        )

    missing_indexes = list(_missing_additive_indexes(bind))
    for index in missing_indexes:
        index_ddl = str(CreateIndex(index).compile(dialect=bind.dialect))
        _execute_additive_ddl(
            bind,
            index_ddl,
            object_kind="index",
            object_exists=lambda index=index: _index_exists(
                bind, index.table.name, index.name
            ),
        )


def get_db():
    """FastAPI 依赖：获取数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    # Delayed import to avoid circular dependency.
    from backend.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    initialize_additive_schema(engine)
