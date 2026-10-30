from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.tests.career_fixtures import career_engine, career_db
from backend.db.database import Base, ensure_sqlite_schema
from backend.db.models import JobApplication, JobDescription, User
from backend.db.career_models import ProfileFact, ResumeVersion


def test_fact_revisions_and_version_references_roundtrip(career_db):
    career_db.add_all([
        ProfileFact(id='fact-v1', user_id=1, fact_key='project-role', revision=1, kind='project', content={'role': 'developer'}, source_document_id=1),
        ProfileFact(id='fact-v2', user_id=1, fact_key='project-role', revision=2, kind='project', content={'role': 'backend lead'}, source_document_id=1),
        ResumeVersion(id='version-1', user_id=1, resume_id=1, jd_id=1, structured_content={'summary': 'Developer'}, fact_refs=['fact-v1']),
    ])
    career_db.commit()
    career_db.expire_all()
    version = career_db.get(ResumeVersion, 'version-1')
    assert version.fact_refs == ['fact-v1']
    assert career_db.get(ProfileFact, version.fact_refs[0]).content == {'role': 'developer'}
    assert career_db.get(ProfileFact, 'fact-v2').content == {'role': 'backend lead'}


def test_same_source_job_is_unique_within_user(career_db):
    def job(owner):
        return JobDescription(user_id=owner, title='Engineer', raw_text='API', source_site='example', source_job_id='123')
    career_db.add_all([job(1), job(2)])
    career_db.commit()
    career_db.add(job(1))
    with pytest.raises(IntegrityError):
        career_db.commit()
    career_db.rollback()
    career_db.add_all([JobDescription(user_id=1, title='Pasted', raw_text='A'), JobDescription(user_id=1, title='Pasted', raw_text='B')])
    career_db.commit()


def test_old_application_survives_incremental_schema_upgrade(career_engine):
    # Create old models from the committed pre-T02 CloudBase schema for MySQL.
    if career_engine.dialect.name == 'mysql':
        script = Path('deploy/cloudbase/mysql-schema.sql').read_text()
        with career_engine.begin() as conn:
            for statement in '\n'.join(line for line in script.splitlines() if not line.lstrip().startswith('--')).split(';'):
                if statement.strip():
                    conn.execute(text(statement))
    else:
        with career_engine.begin() as conn:
            conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(100) NOT NULL, password_hash VARCHAR(255) NOT NULL, role VARCHAR(20) NOT NULL, created_at DATETIME NOT NULL)"))
            conn.execute(text("CREATE TABLE job_applications (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), resume_id INTEGER, company VARCHAR(255) NOT NULL, position VARCHAR(255) NOT NULL, applied_date DATE NOT NULL, status VARCHAR(40) NOT NULL, job_url VARCHAR(1024) NOT NULL DEFAULT '', source VARCHAR(120) NOT NULL DEFAULT '', notes TEXT NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"))
    with career_engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id,username,password_hash,role,created_at) VALUES (1,'legacy','test','user','2026-10-29')"))
        conn.execute(text("INSERT INTO job_applications (id,user_id,company,position,applied_date,status,notes,created_at,updated_at) VALUES (1,1,'Existing Co','Engineer','2026-10-29','applied','original','2026-10-29','2026-10-29')"))
    if career_engine.dialect.name == 'mysql':
        script = Path('deploy/schema/001_agent_and_versions.sql').read_text()
        with career_engine.begin() as conn:
            for statement in '\n'.join(line for line in script.splitlines() if not line.lstrip().startswith('--')).split(';'):
                if statement.strip():
                    conn.execute(text(statement))
    else:
        Base.metadata.create_all(career_engine)
        ensure_sqlite_schema(career_engine)
        ensure_sqlite_schema(career_engine)  # Startup runs repeatedly; no duplicate history.
    with Session(career_engine) as db:
        app = db.get(JobApplication, 1)
        assert (app.company, app.notes, app.applied_date) == ('Existing Co', 'original', date(2026,10,29))
        assert app.jd_id is None and app.resume_version_id is None
        assert app.submitted_snapshot is None


def test_fact_revision_cannot_be_overwritten_by_duplicate_insert(career_db):
    career_db.add(ProfileFact(user_id=1, fact_key='role', revision=1, kind='project', content={'role': 'developer'}))
    career_db.commit()
    career_db.add(ProfileFact(user_id=1, fact_key='role', revision=1, kind='project', content={'role': 'lead'}))
    with pytest.raises(IntegrityError):
        career_db.commit()
    career_db.rollback()
    assert career_db.query(ProfileFact).one().content == {'role': 'developer'}


def test_application_snapshot_survives_draft_edit(career_db):
    version = ResumeVersion(id='version-1', user_id=1, resume_id=1, jd_id=1,
                            structured_content={'summary': 'Submitted wording'}, fact_refs=[])
    career_db.add(version)
    career_db.flush()
    app = JobApplication(user_id=1, company='Example', position='Engineer',
                         applied_date=date(2026, 10, 29), jd_id=1, resume_version_id=version.id,
                         submitted_snapshot={'summary': 'Submitted wording'})
    career_db.add(app)
    career_db.commit()
    version.structured_content = {'summary': 'Later wording'}
    career_db.commit()
    career_db.expire_all()
    assert career_db.get(JobApplication, app.id).submitted_snapshot == {'summary': 'Submitted wording'}
