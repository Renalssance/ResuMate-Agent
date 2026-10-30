"""Fixed task input survives edits, while deletion still stops new generation."""
from copy import deepcopy
from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete

from backend.db.agent_models import AgentAction, AgentRun, AgentSession
from backend.db.career_models import ProfileFact
from backend.db.models import AnalysisCandidate, AnalysisJob, JobDescription, MatchResult, Resume
from backend.schemas.agent_runs import RunCreate
from backend.services.agent_runs import RunError, create_run, list_runs, retry_run, run_snapshot
from backend.tests.career_fixtures import career_engine, career_db


def make_run(db, request_id='snapshot-1'):
    return create_run(db, 1, RunCreate(kind='tailoring', jdId=1, resumeId=1, requestId=request_id))


def seed_input(db):
    resume, jd = db.get(Resume, 1), db.get(JobDescription, 1)
    resume.raw_text = 'Built the API'
    resume.structured_data = {'self_summary': 'API developer', 'projects': [{'description': 'Built APIs', 'source_refs': ['page:1']} ]}
    jd.structured_data = {'title': 'Backend engineer'}
    db.add_all([
        ProfileFact(id='fact-old', user_id=1, fact_key='fact-family', kind='experience', content={'text':'Implemented APIs'}, revision=1, confirmed_at=datetime(2026, 10, 29), source_document_id=1),
        ProfileFact(id='fact-unconfirmed', user_id=1, fact_key='unconfirmed', kind='experience', content={'text':'Not confirmed'}, revision=1),
        ProfileFact(id='fact-other', user_id=2, fact_key='foreign', kind='experience', content={'text':'Private'}, revision=1, confirmed_at=datetime(2026, 10, 29)),
    ])
    db.commit()


def fail(db, run):
    run.status = 'failed'
    db.get(AgentSession, run.session_id).active_run_id = None
    db.commit()


def test_creation_freezes_resume_job_and_confirmed_fact_text(career_db):
    seed_input(career_db)
    run = make_run(career_db)
    snapshot = run.input_json.get('contextSnapshot')
    assert snapshot is not None
    assert snapshot['resume'] == {'id':1, 'text':'Built the API', 'structured':career_db.get(Resume,1).structured_data, 'inputVersion':run.input_versions['resume']}
    assert snapshot['job'] == {'id':1, 'title':'Engineer', 'text':'Build APIs', 'structured':{'title':'Backend engineer'}, 'inputVersion':run.input_versions['jd']}
    assert snapshot['facts'] == [{'id':'fact-old','revision':1,'content':{'text':'Implemented APIs'}}]
    assert snapshot['match'] is None


def test_creation_freezes_latest_owned_matching_report(career_db):
    for number, owner in [(1,1), (2,1), (3,2)]:
        career_db.add(AnalysisJob(id=number,user_id=owner,jd_id=1,title='Match'))
        career_db.flush()
        career_db.add(AnalysisCandidate(id=number,job_id=number,resume_id=1))
        career_db.flush()
        career_db.add(MatchResult(id=number,job_id=number,candidate_id=number,resume_id=1,jd_id=1,
            overall_score=70 + number, report_json={'reason':f'report-{number}'}, created_at=datetime(2026,10,29,number)))
    career_db.commit()
    run = make_run(career_db)
    snapshot = run.input_json.get('contextSnapshot')
    assert snapshot is not None
    match = snapshot['match']
    assert (match['id'],match['runId'],match['candidateId'],match['overallScore']) == (2,2,2,72)
    assert match['report'] == {'reason':'report-2'}
    career_db.get(MatchResult,2).report_json = {'reason':'edited'}
    career_db.commit()
    from backend.agent_runtime.context import read_context
    assert read_context(career_db,run)['match']['report'] == {'reason':'report-2'}


def test_snapshot_dedup_uses_business_ids_and_public_reads_do_not_include_content(career_db):
    seed_input(career_db)
    run = make_run(career_db)
    assert 'contextSnapshot' in run.input_json
    assert make_run(career_db).id == run.id
    for public_input in [list_runs(career_db,1)['items'][0]['input'], run_snapshot(career_db,1,run.id)['input']]:
        assert public_input == {'jdId':1,'resumeId':1}
    with pytest.raises(RunError, match='requestId'):
        create_run(career_db,1,RunCreate(kind='tailoring',jdId=2,resumeId=1,requestId='snapshot-1'))


def test_context_keeps_original_content_after_edits_and_returns_independent_copy(career_db):
    seed_input(career_db)
    run = make_run(career_db)
    from backend.agent_runtime.context import read_context, changed_inputs
    before = read_context(career_db,run)
    career_db.get(Resume,1).structured_data = {'self_summary':'Edited summary'}
    career_db.get(Resume,1).updated_at += timedelta(seconds=1)
    career_db.get(JobDescription,1).raw_text = 'New requirements'
    career_db.get(JobDescription,1).updated_at += timedelta(seconds=1)
    career_db.add(ProfileFact(id='fact-new',user_id=1,fact_key='fact-family',kind='experience',content={'text':'Updated fact'},revision=2,confirmed_at=datetime(2026,10,30),source_document_id=1))
    career_db.commit()
    after = read_context(career_db,run)
    assert after == before
    assert changed_inputs(career_db,run) == ['resume','jd','facts']
    after['resume']['structured']['self_summary'] = 'mutated'
    after['facts'][0]['content']['text'] = 'mutated'
    assert read_context(career_db,run) == before


def test_retry_with_fixed_snapshot_keeps_original_documents(career_db):
    seed_input(career_db)
    run = make_run(career_db)
    original = deepcopy(run.input_json)
    fail(career_db,run)
    career_db.get(Resume,1).updated_at += timedelta(seconds=1)
    career_db.get(Resume,1).structured_data = {'self_summary':'Edited'}
    career_db.commit()
    retry_run(career_db,1,run.id)
    assert run.status == 'queued' and run.attempt == 2
    assert run.input_json == original


@pytest.mark.parametrize('model,key',[(Resume,'resume'),(JobDescription,'jd')])
def test_deleted_source_blocks_new_context_and_retry_but_preserves_history(career_db,model,key):
    run = make_run(career_db)
    original = deepcopy(run.input_json)
    fail(career_db,run)
    career_db.execute(delete(model).where(model.id == 1))
    career_db.commit()
    from backend.agent_runtime.context import read_context, changed_inputs
    for operation in [lambda:read_context(career_db,run), lambda:retry_run(career_db,1,run.id)]:
        with pytest.raises(RunError) as caught:
            operation()
        assert caught.value.code == 'input_changed'
    assert key in changed_inputs(career_db,run)
    assert run.input_json == original
    assert run_snapshot(career_db,1,run.id)['input'] == {'jdId':1,'resumeId':1}


def test_legacy_context_only_backfills_unchanged_inputs_and_missing_facts_stay_empty(career_db):
    seed_input(career_db)
    run = make_run(career_db)
    run.input_json = {'jdId':1,'resumeId':1}
    run.input_versions = {key:value for key,value in run.input_versions.items() if key != 'facts'}
    career_db.commit()
    from backend.agent_runtime.context import read_context
    assert read_context(career_db,run)['facts'] == []
    career_db.commit()
    career_db.refresh(run)
    assert run.input_json['contextSnapshot']['facts'] == []


def test_changed_legacy_context_is_not_reconstructed(career_db):
    run = make_run(career_db)
    run.input_json = {'jdId':1,'resumeId':1}
    fail(career_db,run)
    career_db.get(Resume,1).updated_at += timedelta(seconds=1)
    career_db.commit()
    from backend.agent_runtime.context import read_context
    for operation in [lambda:read_context(career_db,run),lambda:retry_run(career_db,1,run.id)]:
        with pytest.raises(RunError) as caught:
            operation()
        assert caught.value.code == 'input_changed'
    assert 'contextSnapshot' not in run.input_json


def test_context_contains_only_submitted_answers_from_this_run(career_db):
    run, other = make_run(career_db), make_run(career_db,'other-run')
    for action_id, run_id, kind, status, decision in [
        ('submitted',run.id,'input','answered','submit'), ('pending',run.id,'input','pending',None),
        ('approval',run.id,'approval','answered','approve'), ('foreign',other.id,'input','answered','submit'),
    ]:
        career_db.add(AgentAction(id=action_id,run_id=run_id,interrupt_id=action_id,kind=kind,status=status,
            payload={'question':'What was your role?'},response={'decision':decision,'answers':{'role':'Backend'}} if decision else None,
            answered_at=datetime(2026,10,30) if decision else None))
    career_db.commit()
    from backend.agent_runtime.context import read_context
    context = read_context(career_db,run)
    assert context['applicantAnswers'] == [{'actionId':'submitted','question':'What was your role?','answers':{'role':'Backend'}}]
    assert context['inputVersions'] == run.input_versions


def test_capture_checks_ownership_and_context_stops_after_source_owner_changes(career_db):
    run = make_run(career_db)
    from backend.agent_runtime.context import capture_context, read_context
    with pytest.raises(RunError) as caught:
        capture_context(career_db,2,1,1,run.input_versions)
    assert caught.value.status == 404
    career_db.get(Resume,1).user_id = 2
    career_db.commit()
    with pytest.raises(RunError) as caught:
        read_context(career_db,run)
    assert caught.value.code == 'input_changed'
