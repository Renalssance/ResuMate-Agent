import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateColumn

from backend.db.database import (
    ADDITIVE_SCHEMA_COLUMNS,
    ADDITIVE_SCHEMA_INDEXES,
    Base,
    _execute_additive_ddl,
    initialize_additive_schema,
)
from backend.db.models import (
    AnalysisCandidate,
    AnalysisJob,
    JobDescription,
    MatchResult,
    Resume,
    User,
)


def test_document_metadata_and_workflow_report_commit_and_read(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'persistent-models.db'}")
    Base.metadata.create_all(bind=engine)

    workflow_report = {
        "run_id": "run-real-001",
        "candidate_id": "candidate-real-001",
        "candidate_name": "Real Candidate",
        "filename": "candidate.pdf",
        "job_profile": {
            "job_title": "Backend Engineer",
            "criteria": [
                {
                    "criterion_id": "python",
                    "name": "Python",
                    "weight": 100,
                    "evidence_query": "Python API experience",
                }
            ],
        },
        "evaluations": [
            {
                "criterion_id": "python",
                "score": 4,
                "evidence": [
                    {
                        "chunk_id": "resume-1-page-1",
                        "filename": "candidate.pdf",
                        "page_number": 1,
                        "section": "Experience",
                        "text": "Built production FastAPI services.",
                        "score": 0.93,
                    }
                ],
            }
        ],
        "formal_questions": [{"question": "Describe the API design."}],
    }

    with Session(engine) as session:
        user = User(username="persistent-user", password_hash="hash")
        session.add(user)
        session.flush()

        resume = Resume(
            user_id=user.id,
            filename="candidate.pdf",
            file_path="data/documents/candidate.pdf",
            document_size=123,
            parse_status="success",
            raw_text="Real uploaded resume text",
            structured_data={"candidate_name": "Real Candidate"},
        )
        jd = JobDescription(
            user_id=user.id,
            title="Backend Engineer",
            company="Example",
            filename="backend-engineer.pdf",
            file_path="data/documents/backend-engineer.pdf",
            document_size=456,
            parse_status="success",
            raw_text="Real uploaded JD text",
            structured_data={"job_title": "Backend Engineer"},
        )
        session.add_all([resume, jd])
        session.flush()

        job = AnalysisJob(user_id=user.id, jd_id=jd.id, title=jd.title, status="completed")
        session.add(job)
        session.flush()
        candidate = AnalysisCandidate(job_id=job.id, resume_id=resume.id, status="completed")
        session.add(candidate)
        session.flush()
        result = MatchResult(
            job_id=job.id,
            candidate_id=candidate.id,
            resume_id=resume.id,
            jd_id=jd.id,
            overall_score=82,
            recommendation="strong_recommend",
            report_json=workflow_report,
        )
        session.add(result)
        session.commit()
        resume_id = resume.id
        jd_id = jd.id
        result_id = result.id

    with Session(engine) as session:
        stored_resume = session.get(Resume, resume_id)
        stored_jd = session.get(JobDescription, jd_id)
        stored_result = session.get(MatchResult, result_id)

        assert stored_resume.document_size == 123
        assert stored_resume.parse_status == "success"
        assert stored_jd.filename == "backend-engineer.pdf"
        assert stored_jd.file_path == "data/documents/backend-engineer.pdf"
        assert stored_jd.document_size == 456
        assert stored_jd.parse_status == "success"
        assert stored_result.report_json == workflow_report


def test_additive_schema_initialization_preserves_existing_rows_and_is_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE resumes (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE job_descriptions (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE match_results (id INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO resumes (id) VALUES (1)"))
        connection.execute(text("INSERT INTO job_descriptions (id) VALUES (2)"))
        connection.execute(text("INSERT INTO match_results (id) VALUES (3)"))

    initialize_additive_schema(engine)
    initialize_additive_schema(engine)

    inspector = inspect(engine)
    resume_columns = {column["name"] for column in inspector.get_columns("resumes")}
    jd_columns = {column["name"] for column in inspector.get_columns("job_descriptions")}
    result_columns = {column["name"] for column in inspector.get_columns("match_results")}
    resume_indexes = {index["name"] for index in inspector.get_indexes("resumes")}
    jd_indexes = {index["name"] for index in inspector.get_indexes("job_descriptions")}

    assert {"document_size", "parse_status"} <= resume_columns
    assert {"filename", "file_path", "document_size", "parse_status"} <= jd_columns
    assert {"report_json"} <= result_columns
    assert "ix_resumes_parse_status" in resume_indexes
    assert "ix_job_descriptions_parse_status" in jd_indexes

    with engine.connect() as connection:
        resume_row = connection.execute(
            text("SELECT id, document_size, parse_status FROM resumes WHERE id = 1")
        ).one()
        jd_row = connection.execute(
            text(
                "SELECT id, filename, file_path, document_size, parse_status "
                "FROM job_descriptions WHERE id = 2"
            )
        ).one()
        result_row = connection.execute(
            text("SELECT id, report_json FROM match_results WHERE id = 3")
        ).one()

    assert resume_row == (1, 0, "pending")
    assert jd_row == (2, "", "", 0, "pending")
    assert result_row.id == 3
    assert result_row.report_json == "{}"


@pytest.mark.parametrize(
    ("table_name", "column_name", "expected_definition"),
    [
        ("resumes", "document_size", "document_size INTEGER DEFAULT '0' NOT NULL"),
        ("resumes", "parse_status", "parse_status VARCHAR(40) DEFAULT 'pending' NOT NULL"),
        ("job_descriptions", "filename", "filename VARCHAR(255) DEFAULT '' NOT NULL"),
        ("job_descriptions", "file_path", "file_path VARCHAR(1024) DEFAULT '' NOT NULL"),
        ("job_descriptions", "document_size", "document_size INTEGER DEFAULT '0' NOT NULL"),
        (
            "job_descriptions",
            "parse_status",
            "parse_status VARCHAR(40) DEFAULT 'pending' NOT NULL",
        ),
        ("match_results", "report_json", "report_json JSON DEFAULT '{}' NOT NULL"),
    ],
)
def test_every_additive_column_compiles_to_expected_postgresql_ddl(
    table_name, column_name, expected_definition
):
    assert column_name in ADDITIVE_SCHEMA_COLUMNS[table_name]

    column = Base.metadata.tables[table_name].columns[column_name]
    column_definition = str(CreateColumn(column).compile(dialect=postgresql.dialect()))
    ddl = f'ALTER TABLE "{table_name}" ADD COLUMN {column_definition}'

    assert ddl == f'ALTER TABLE "{table_name}" ADD COLUMN {expected_definition}'


class _OriginalDatabaseError(Exception):
    def __init__(self, message, *, sqlstate=None):
        super().__init__(message)
        self.sqlstate = sqlstate
        self.pgcode = sqlstate


class _RaisingConnection:
    def __init__(self, error):
        self.error = error

    def execute(self, _statement):
        raise self.error


class _BeginContext:
    def __init__(self, error):
        self.connection = _RaisingConnection(error)

    def __enter__(self):
        return self.connection

    def __exit__(self, *_args):
        return False


class _RaisingBind:
    def __init__(self, dialect_name, error):
        self.dialect = type("Dialect", (), {"name": dialect_name})()
        self.error = error

    def begin(self):
        return _BeginContext(self.error)


@pytest.mark.parametrize(
    ("dialect_name", "error"),
    [
        (
            "postgresql",
            ProgrammingError(
                "ALTER TABLE resumes ADD COLUMN parse_status VARCHAR(40)",
                {},
                _OriginalDatabaseError("column already exists", sqlstate="42701"),
            ),
        ),
        (
            "sqlite",
            OperationalError(
                "ALTER TABLE resumes ADD COLUMN parse_status VARCHAR(40)",
                {},
                _OriginalDatabaseError("duplicate column name: parse_status"),
            ),
        ),
    ],
)
def test_execute_additive_ddl_ignores_only_confirmed_duplicate_column(dialect_name, error):
    bind = _RaisingBind(dialect_name, error)

    _execute_additive_ddl(
        bind,
        "ALTER TABLE resumes ADD COLUMN parse_status VARCHAR(40)",
        object_kind="column",
        object_exists=lambda: True,
    )


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("ALTER TABLE broken", {}, _OriginalDatabaseError("disk I/O error")),
        ProgrammingError(
            "ALTER TABLE broken",
            {},
            _OriginalDatabaseError("syntax error", sqlstate="42601"),
        ),
    ],
)
def test_execute_additive_ddl_reraises_non_duplicate_database_errors(error):
    bind = _RaisingBind("postgresql", error)

    with pytest.raises(type(error)):
        _execute_additive_ddl(
            bind,
            "ALTER TABLE broken",
            object_kind="column",
            object_exists=lambda: True,
        )


def test_execute_additive_ddl_reraises_unconfirmed_duplicate_column():
    error = ProgrammingError(
        "ALTER TABLE resumes ADD COLUMN parse_status VARCHAR(40)",
        {},
        _OriginalDatabaseError("column already exists", sqlstate="42701"),
    )
    bind = _RaisingBind("postgresql", error)

    with pytest.raises(ProgrammingError):
        _execute_additive_ddl(
            bind,
            "ALTER TABLE resumes ADD COLUMN parse_status VARCHAR(40)",
            object_kind="column",
            object_exists=lambda: False,
        )


@pytest.mark.parametrize(
    ("dialect_name", "error"),
    [
        (
            "postgresql",
            ProgrammingError(
                "CREATE INDEX ix_resumes_parse_status",
                {},
                _OriginalDatabaseError("relation already exists", sqlstate="42P07"),
            ),
        ),
        (
            "sqlite",
            OperationalError(
                "CREATE INDEX ix_resumes_parse_status",
                {},
                _OriginalDatabaseError("index ix_resumes_parse_status already exists"),
            ),
        ),
    ],
)
def test_execute_additive_ddl_ignores_confirmed_duplicate_index(dialect_name, error):
    bind = _RaisingBind(dialect_name, error)

    _execute_additive_ddl(
        bind,
        "CREATE INDEX ix_resumes_parse_status ON resumes (parse_status)",
        object_kind="index",
        object_exists=lambda: True,
    )


def test_additive_index_whitelist_matches_parse_status_model_indexes():
    assert ADDITIVE_SCHEMA_INDEXES == {
        "resumes": ("ix_resumes_parse_status",),
        "job_descriptions": ("ix_job_descriptions_parse_status",),
    }
