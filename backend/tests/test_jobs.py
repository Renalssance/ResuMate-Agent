"""Jobs API contract against disposable SQLite and MySQL databases."""
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from backend.auth.security import get_current_user
from backend.db.database import Base, ensure_sqlite_schema, get_db
from backend.db.models import AnalysisCandidate, AnalysisJob, JobDescription, MatchResult, Resume, User, UserLlmSettings
from backend.routes.api import router
from backend.schemas.workflow import JobProfile
from backend.tests.career_fixtures import career_db, career_engine


@pytest.fixture
def client(career_db, career_engine, monkeypatch):
    from backend.services import background_tasks, llm_settings
    factory = sessionmaker(bind=career_engine, expire_on_commit=False)
    monkeypatch.setattr(background_tasks, 'SessionLocal', factory)
    monkeypatch.setattr(llm_settings, 'SessionLocal', factory)
    app = FastAPI()
    app.include_router(router)
    def request_db():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = request_db
    current_user = career_db.get(User, 1)
    career_db.expunge(current_user)
    career_db.commit()
    app.dependency_overrides[get_current_user] = lambda: current_user
    with TestClient(app) as client:
        yield client


def capture(client, **changes):
    return client.post('/api/jobs', json={'title': 'API Engineer', 'company': 'Example', 'text': 'Develop Python APIs', **changes})


def test_capture_deduplicates_and_preserves_manual_edits(client, career_db):
    first = capture(client, sourceSite='example', sourceJobId='123', sourceUrl='https://example/jobs/123')
    assert first.status_code == 200
    job = first.json()['job']
    assert first.json()['created'] is True
    assert job['parseStatus'] == 'pending'
    assert datetime.fromisoformat(job['capturedAt'].replace('Z', '+00:00')).tzinfo is not None
    edited = client.patch(f"/api/jobs/{job['id']}", json={'title': 'My title', 'status': 'archived', 'primaryResumeId': 1})
    assert edited.status_code == 200
    again = capture(client, sourceSite='example', sourceJobId='123', text='Changed posting')
    assert again.json()['created'] is False
    assert again.json()['job']['id'] == job['id']
    detail = client.get(f"/api/jobs/{job['id']}").json()
    assert (detail['title'], detail['text'], detail['status']) == ('My title', 'Develop Python APIs', 'archived')
    assert detail['primaryResume'] == {'id': 1, 'filename': 'resume.txt'}
    assert career_db.get(JobDescription, job['id']).structured_data is None


def test_pasted_and_url_only_duplicates_are_scoped_to_current_user(client, career_db):
    one = capture(client, title='  API Engineer  ', text='  Develop Python APIs  ', sourceSite='', sourceJobId='', sourceUrl='').json()
    two = capture(client).json()
    assert two['created'] is False and one['job']['id'] == two['job']['id']
    row = career_db.get(JobDescription, one['job']['id'])
    assert row.source_site is None and row.source_job_id is None and row.source_url is None
    url = capture(client, sourceUrl='https://example/posting').json()
    assert url['created'] is True
    assert capture(client, sourceUrl='https://example/posting').json()['created'] is False
    assert capture(client, sourceUrl='https://example/posting', text='Different text').json()['created'] is True
    career_db.add(JobDescription(user_id=2, title='Other user', raw_text='Private text', source_site='site', source_job_id='1'))
    career_db.commit()
    assert capture(client, text='Private text', sourceSite='site', sourceJobId='1').json()['created'] is True


@pytest.mark.parametrize('payload', [{'title': ' '}, {'text': '\n '}, {'sourceSite': 'site'}, {'sourceJobId': '1'}, {'primaryResumeId': 0}])
def test_capture_rejects_invalid_required_or_source_fields(client, payload):
    assert capture(client, **payload).status_code == 422


def test_job_and_resume_ownership_and_clear_association(client, career_db):
    career_db.add_all([Resume(id=2, user_id=2, filename='private.txt'), JobDescription(id=2, user_id=2, title='Private', raw_text='Secret')])
    career_db.commit()
    assert capture(client, primaryResumeId=2).status_code == 404
    assert client.patch('/api/jobs/1', json={'primaryResumeId': 2}).status_code == 404
    for method, path in [('get', ''), ('patch', ''), ('get', '/matches'), ('post', '/parse')]:
        kwargs = {'json': {'title': 'Stolen'}} if method == 'patch' else {}
        assert getattr(client, method)('/api/jobs/2' + path, **kwargs).status_code == 404
    assert client.patch('/api/jobs/1', json={'primaryResumeId': 1}).json()['primaryResumeId'] == 1
    assert client.patch('/api/jobs/1', json={'primaryResumeId': None}).json()['primaryResume'] is None
    assert client.patch('/api/jobs/1', json={'title': None}).status_code == 422
    assert client.patch('/api/jobs/1', json={'status': None}).status_code == 422
    assert client.patch('/api/jobs/1', json={'status': 'unknown'}).status_code == 422


def test_list_filters_pages_and_uses_capture_time_with_id_tiebreak(client, career_db):
    career_db.get(JobDescription, 1).created_at = datetime(2026, 1, 1)
    career_db.add_all([
        JobDescription(user_id=1, title='Python A', company='Alpha', raw_text='large body', captured_at=datetime(2026, 10, 1)),
        JobDescription(user_id=1, title='Python B', company='Beta', raw_text='large body', captured_at=datetime(2026, 10, 1)),
        JobDescription(user_id=1, title='Python Old', company='Alpha', raw_text='large body', status='archived', captured_at=datetime(2026, 9, 1)),
        JobDescription(user_id=2, title='Python Private', raw_text='private'),
    ])
    career_db.commit()
    first = client.get('/api/jobs?query=Python&status=saved&limit=1').json()
    assert first['hasMore'] is True and first['items'][0]['title'] == 'Python B'
    assert 'text' not in first['items'][0] and 'structuredContent' not in first['items'][0]
    second = client.get('/api/jobs?query=Python&status=saved&limit=1&offset=1').json()
    assert second['hasMore'] is False and second['items'][0]['title'] == 'Python A'
    assert client.get('/api/jobs?query=Beta').json()['items'][0]['title'] == 'Python B'
    assert len(client.get('/api/jobs?status=archived').json()['items']) == 1
    assert client.get('/api/jobs?offset=-1').status_code == 422


def test_matches_are_existing_results_for_owned_job(client, career_db):
    career_db.add_all([AnalysisJob(id=1, user_id=1, jd_id=1, title='Run'), AnalysisJob(id=2, user_id=2, jd_id=1, title='Other')])
    career_db.flush()
    career_db.add_all([AnalysisCandidate(id=1, job_id=1, resume_id=1), AnalysisCandidate(id=2, job_id=2, resume_id=1)])
    career_db.flush()
    career_db.add_all([MatchResult(job_id=1, candidate_id=1, resume_id=1, jd_id=1, overall_score=82.5), MatchResult(job_id=2, candidate_id=2, resume_id=1, jd_id=1, overall_score=12)])
    career_db.commit()
    result = client.get('/api/jobs/1/matches?limit=1').json()
    assert result['hasMore'] is False
    assert len(result['items']) == 1
    assert {k: result['items'][0][k] for k in ('runId', 'candidateId', 'resumeId', 'score')} == {'runId': 1, 'candidateId': 1, 'resumeId': 1, 'score': 82.5}


def test_parse_pasted_text_uses_real_job_profile_and_keeps_saved_text_on_failure(client, career_db, monkeypatch):
    from backend.routes import documents
    from backend.services.progress import progress_hub
    career_db.add(UserLlmSettings(user_id=1, api_key='test-key', base_url='https://example.test/v1', model='test-model'))
    career_db.commit()
    profile = JobProfile(job_title='Parsed Engineer', summary='Python services', criteria=[{'criterion_id': 'python', 'name': 'Python', 'description': 'Build APIs', 'importance': 'must', 'weight': 100, 'evidence_query': 'Python'}])
    def model_result(self, **kwargs):
        if kwargs['variables']['jd_text'] != 'Develop Python APIs':
            raise AssertionError('parser did not receive saved text')
        return profile
    monkeypatch.setattr(documents.AgentHarness, 'run_schema', model_result)
    job_id = capture(client).json()['job']['id']
    task_id = 'parse-' + uuid4().hex
    response = client.post(f'/api/jobs/{job_id}/parse?task_id={task_id}')
    assert response.status_code == 202 and response.json() == {'taskId': task_id}
    career_db.expire_all()
    detail = client.get(f'/api/jobs/{job_id}').json()
    assert detail['parseStatus'] == 'success', [event.message for event in progress_hub._history[task_id]]
    assert detail['structuredContent']['job_title'] == 'Parsed Engineer'
    assert detail['title'] == 'API Engineer'
    assert career_db.get(JobDescription, job_id).file_path == ''
    assert progress_hub._history[task_id][-1].data['document']['id'] == f'jd:{job_id}'
    assert progress_hub._history[task_id][-1].data['document']['vectorized'] is False
    def unavailable(self, **kwargs):
        raise ValueError('model unavailable')
    monkeypatch.setattr(documents.AgentHarness, 'run_schema', unavailable)
    assert client.post(f'/api/jobs/{job_id}/parse').status_code == 202
    career_db.expire_all()
    failed = client.get(f'/api/jobs/{job_id}').json()
    assert failed['text'] == 'Develop Python APIs' and failed['parseStatus'] == 'failed'
    monkeypatch.setattr(documents.AgentHarness, 'run_schema', model_result)
    assert client.post(f'/api/jobs/{job_id}/parse').status_code == 202
    career_db.expire_all()
    assert client.get(f'/api/jobs/{job_id}').json()['parseStatus'] == 'success'


def test_primary_resume_deletion_clears_job_reference(career_db):
    job = career_db.get(JobDescription, 1)
    job.primary_resume_id = 1
    career_db.commit()
    career_db.delete(career_db.get(Resume, 1))
    career_db.commit()
    career_db.expire_all()
    assert career_db.get(JobDescription, 1).primary_resume_id is None


def test_upgrade_adds_nullable_primary_resume_without_losing_saved_jobs(career_engine):
    if career_engine.dialect.name == 'mysql':
        scripts = ['deploy/cloudbase/mysql-schema.sql', 'deploy/schema/001_agent_and_versions.sql']
        with career_engine.begin() as conn:
            for script in scripts:
                for statement in '\n'.join(line for line in Path(script).read_text().splitlines() if not line.lstrip().startswith('--')).split(';'):
                    if statement.strip():
                        conn.execute(text(statement))
    else:
        with career_engine.begin() as conn:
            conn.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT)'))
            conn.execute(text('CREATE TABLE resumes (id INTEGER PRIMARY KEY, user_id INTEGER, filename TEXT)'))
            conn.execute(text('CREATE TABLE job_descriptions (id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT, raw_text TEXT)'))
    with career_engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id,username,password_hash,role,created_at) VALUES (1,'legacy','test','user','2026-10-29')") if career_engine.dialect.name == 'mysql' else text("INSERT INTO users VALUES (1,'legacy','test')"))
        conn.execute(text("INSERT INTO job_descriptions (id,user_id,title,company,raw_text,created_at,updated_at) VALUES (1,1,'Saved','','Original','2026-10-29','2026-10-29')") if career_engine.dialect.name == 'mysql' else text("INSERT INTO job_descriptions VALUES (1,1,'Saved','Original')"))
    if career_engine.dialect.name == 'mysql':
        with career_engine.begin() as conn:
            for statement in '\n'.join(line for line in Path('deploy/schema/002_jobs_primary_resume.sql').read_text().splitlines() if not line.lstrip().startswith('--')).split(';'):
                if statement.strip():
                    conn.execute(text(statement))
    else:
        ensure_sqlite_schema(career_engine)
        ensure_sqlite_schema(career_engine)
    with career_engine.connect() as conn:
        assert conn.execute(text('SELECT title,raw_text,primary_resume_id FROM job_descriptions WHERE id=1')).one() == ('Saved', 'Original', None)


def test_pasted_job_can_reparse_from_existing_document_library(client, monkeypatch):
    from backend.routes import documents
    profile = {'job_title': 'Engineer', 'summary': 'Build APIs', 'criteria': [{'criterion_id': 'api', 'name': 'API', 'description': 'Build APIs', 'importance': 'must', 'weight': 100, 'evidence_query': 'API'}]}
    monkeypatch.setattr(documents, '_parse_profile', lambda *args: profile)
    response = client.post('/api/documents/jd:1/parse')
    assert response.status_code == 200
    assert response.json()['raw_text'] == 'Build APIs'
    assert response.json()['vectorized'] is False
    listed = client.get('/api/documents').json()
    assert next(doc for doc in listed if doc['id'] == 'jd:1')['vectorized'] is False


def test_url_dedup_keeps_distinct_case_sensitive_source_paths(client):
    first = capture(client, sourceUrl='https://example/jobs/Engineer').json()
    second = capture(client, sourceUrl='https://example/jobs/engineer').json()
    assert second['created'] is True
    assert second['job']['id'] != first['job']['id']
