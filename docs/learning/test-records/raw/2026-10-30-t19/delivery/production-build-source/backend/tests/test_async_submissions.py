"""Legacy HTTP routes accept durable tasks without invoking model work in the API."""
import pytest

from backend.db.agent_models import AgentRun
from backend.db.models import AnalysisCandidate, AnalysisJob, MatchResult
from backend.schemas.workflow import CandidateReport, JobProfile, ResumeProfile
from backend.tests.career_fixtures import career_db, career_engine
from backend.tests.test_document_tasks import parse_app


def seed_report(factory):
    with factory() as db:
        job = AnalysisJob(user_id=1, jd_id=1, title='Engineer')
        db.add(job)
        db.flush()
        candidate = AnalysisCandidate(job_id=job.id, resume_id=1)
        db.add(candidate)
        db.flush()
        report = CandidateReport(run_id=job.id, candidate_id=candidate.id, candidate_name='Ada', filename='resume.txt',
            job_profile=JobProfile(job_title='Engineer', summary='APIs', criteria=[dict(criterion_id='api', name='API', description='Build APIs', importance='must', weight=100, evidence_query='API')]), resume_profile=ResumeProfile(candidate_name='Ada'),
            evaluations=[], total_score=0, recommendation='hold', summary='Insufficient evidence')
        db.add(MatchResult(job_id=job.id, candidate_id=candidate.id, resume_id=1, jd_id=1,
            report_json=report.model_dump(mode='json')))
        db.commit()
        return job.id, candidate.id


@pytest.mark.parametrize('operation,kind', [('match', 'match_analysis'), ('questions', 'question_generation'),
    ('reparse', 'document_parse'), ('saved_job', 'document_parse'), ('followup', 'answer_followup')])
def test_long_routes_persist_accepted_input_without_running_models(parse_app, monkeypatch, operation, kind):
    from backend.routes import runs, jobs
    from backend.agents.harness import AgentHarness
    client, factory, originals = parse_app
    client.app.include_router(runs.router)
    client.app.include_router(jobs.router)
    def forbidden(*args, **kwargs):
        raise AssertionError('API acceptance must not call a model')
    monkeypatch.setattr(AgentHarness, 'run_schema', forbidden)
    if operation == 'match':
        path, payload = '/api/runs', {'jd_document_id': 'jd:1', 'resume_document_ids': ['resume:1'], 'taskId': 'request-key'}
    elif operation == 'questions':
        job_id, candidate_id = seed_report(factory)
        path, payload = f'/api/runs/{job_id}/candidates/{candidate_id}/questions?task_id=request-key&question_count=3', None
    elif operation == 'reparse':
        path, payload = '/api/documents/jd:1/parse?task_id=request-key', None
    elif operation == 'saved_job':
        path, payload = '/api/jobs/1/parse?task_id=request-key', None
    else:
        path, payload = '/api/followups/analyze?task_id=request-key', {'question': 'What did you build?', 'answer': 'An API'}
    response = client.post(path, json=payload, headers={'Prefer': 'respond-async'})
    assert response.status_code == 202, response.text
    assert set(response.json()) == {'taskId'}
    run_id = response.json()['taskId']
    assert run_id != 'request-key'
    with factory() as db:
        run = db.get(AgentRun, run_id)
        assert run.kind == kind and run.status == 'queued'
        assert run.request_id == 'request-key' and run.result_json is None
        if operation == 'match':
            assert len(run.input_json['candidateIds']) == 1
        if operation == 'questions':
            assert run.input_json['questionCount'] == 3 and run.input_json['reportSnapshot']['candidate_name'] == 'Ada'
    again = client.post(path, json=payload, headers={'Prefer': 'respond-async'})
    assert again.json() == response.json()


def test_upload_request_key_conflict_is_rejected_before_new_file(parse_app):
    from backend.tests.test_document_tasks import upload
    client, factory, originals = parse_app
    first = upload(client, 'used-key')
    assert first.status_code == 202
    conflicting = client.post('/api/documents', data={'document_type': 'jd', 'task_id': 'used-key'},
        files={'files': ('job.txt', b'API engineer posting with enough original text.')}, headers={'Prefer': 'respond-async'})
    assert conflicting.status_code == 409
    assert len(list(originals.iterdir())) == 1
