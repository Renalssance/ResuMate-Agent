"""Field proposals preserve fixed inputs and bind every source to the applicant."""
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import sessionmaker

from backend.db.agent_models import AgentAction, AgentRunEvent, ToolOperation
from backend.db.career_models import ResumeVersion
from backend.db.models import Resume
from backend.schemas.agent_runs import RunCreate
from backend.services import agent_runs
from backend.tests.career_fixtures import career_engine, career_db
from backend.tests.test_agent_run_routes import run_client, headers


@pytest.fixture
def proposal(career_db, career_engine, monkeypatch):
    from backend.agent_runtime import tools
    resume = career_db.get(Resume, 1)
    resume.structured_data = {'self_summary': 'Built APIs', 'work_experience': [
        {'company': 'Actual company', 'description': 'Built reliable APIs', 'source_refs': [{'page_number': 0, 'section': 'work_experience', 'text': 'Built reliable APIs', 'chunk_id': 'resume:1:0'}]}],
        'projects': [{'name': 'Actual project', 'description': 'Designed an API', 'source_refs': []}]}
    career_db.commit()
    monkeypatch.setattr(tools, 'SessionLocal', sessionmaker(career_engine, expire_on_commit=False))
    run = agent_runs.create_run(career_db, 1, RunCreate(
        kind='tailoring', jd_id=1, resume_id=1, request_id='proposals'))
    epoch = agent_runs.claim_run(career_db, run.id)
    ref = {'kind': 'resume', 'resumeId': 1, 'inputVersion': run.input_versions['resume'],
           'section': '/work_experience/0/description', 'sourceRefs': [{'page_number': 0, 'section': 'work_experience', 'text': 'Built reliable APIs', 'chunk_id': 'resume:1:0'}]}
    change = {'section': '/self_summary', 'before': 'Built APIs', 'after': 'Built reliable APIs',
              'reason': '突出已有 API 开发经历', 'fact_refs': [ref], 'requires_input': False}
    return tools, run, epoch, change


def test_draft_preserves_base_and_api_resolves_fixed_sources(proposal, career_db, run_client):
    tools, run, epoch, change = proposal
    version_id = tools.save_draft(run.id, epoch, [change])
    response = run_client.get('/api/resume-versions/' + version_id, headers=headers())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['structuredContent']['resume']['self_summary'] == 'Built APIs'
    saved = result['structuredContent']['changes'][0]
    assert saved['id'] and saved['status'] == 'pending'
    assert {k: saved[k] for k in change} == change
    assert result['factRefs'] == change['fact_refs']
    assert result['sources'][0]['content'] == 'Built reliable APIs'
    assert result['basedOnOldInput'] is False and result['changedInputs'] == []
    assert result['reviewable'] is True
    assert run_client.get('/api/resume-versions/' + version_id, headers=headers('bob')).status_code == 404
    assert run_client.get('/api/resume-versions/' + version_id).status_code == 401
    artifacts = run_client.get('/api/agent/runs/' + run.id + '/artifacts', headers=headers()).json()
    assert artifacts == [result]


@pytest.mark.parametrize('patch', [
    {'section': '/work_experience/99/description'},
    {'section': '/candidate_name'},
    {'section': '/summary'},
    {'before': 'Wrong original'},
    {'after': None},
    {'fact_refs': []},
    {'requires_input': True},
    {'requires_input': 'true'},
    {'reason': ' '},
    {'after': {'arbitrary': 'object'}},
])
def test_invalid_proposal_does_not_write_any_artifact(proposal, career_db, patch):
    tools, run, epoch, change = proposal
    with pytest.raises(agent_runs.RunError) as error:
        tools.save_draft(run.id, epoch, [{**change, **patch}])
    assert error.value.status == 422
    assert career_db.query(ResumeVersion).count() == 0
    assert career_db.query(ToolOperation).count() == 0
    assert career_db.query(AgentRunEvent).filter_by(type='artifact.created').count() == 0


def test_duplicate_field_rejected_and_missing_input_has_no_invented_after(proposal, career_db):
    tools, run, epoch, change = proposal
    with pytest.raises(agent_runs.RunError):
        tools.save_draft(run.id, epoch, [change, change])
    pending = {**change, 'after': None, 'requires_input': True, 'fact_refs': [], 'reason': '请补充真实指标'}
    version_id = tools.save_draft(run.id, epoch, [pending])
    career_db.rollback()  # End the MySQL reader snapshot before observing another transaction.
    version = career_db.get(ResumeVersion, version_id)
    assert version.structured_content['changes'][0]['after'] is None
    assert version.fact_refs == []


@pytest.mark.parametrize('patch', [
    {'kind': 'job'}, {'resumeId': 2}, {'inputVersion': 'new-version'},
    {'section': '/missing'}, {'sourceRefs': [9]},
])
def test_resume_sources_must_match_fixed_applicant_input(proposal, career_db, patch):
    tools, run, epoch, change = proposal
    change['fact_refs'] = [{**change['fact_refs'][0], **patch}]
    with pytest.raises(agent_runs.RunError):
        tools.save_draft(run.id, epoch, [change])
    assert career_db.query(ResumeVersion).count() == 0


def test_answer_source_only_accepts_answered_input_from_same_run(proposal, career_db):
    tools, run, epoch, change = proposal
    action = AgentAction(id=str(uuid4()), run_id=run.id, interrupt_id='ask-1', kind='input',
                         payload={'question': '做了什么？'}, status='pending')
    career_db.add(action)
    career_db.commit()
    change['fact_refs'] = [{'kind': 'applicant_answer', 'actionId': action.id}]
    with pytest.raises(agent_runs.RunError):
        tools.save_draft(run.id, epoch, [change])
    action.status = 'answered'
    action.response = {'answers': {'text': 'Built APIs'}, 'decision': 'submit'}
    career_db.commit()
    version_id = tools.save_draft(run.id, epoch, [change])
    career_db.rollback()
    from backend.services.resume_versions import serialize_version
    result = serialize_version(career_db, 1, career_db.get(ResumeVersion, version_id))
    assert result['sources'][0]['content'] == {'question': '做了什么？', 'answers': {'text': 'Built APIs'}}


def test_foreign_answer_rejected(proposal, career_db):
    tools, run, epoch, change = proposal
    other = agent_runs.create_run(career_db, 1, RunCreate(kind='tailoring', jd_id=1, resume_id=1, request_id='another'))
    action = AgentAction(id=str(uuid4()), run_id=other.id, interrupt_id='ask-2', kind='input',
                         payload={'question': 'Other'}, status='answered', response={'answers': {'text': 'Other'}, 'decision': 'submit'})
    career_db.add(action)
    career_db.commit()
    change['fact_refs'] = [{'kind': 'applicant_answer', 'actionId': action.id}]
    with pytest.raises(agent_runs.RunError):
        tools.save_draft(run.id, epoch, [change])


def test_edited_then_deleted_inputs_leave_historical_sources_readable(proposal, career_db, run_client):
    tools, run, epoch, change = proposal
    version_id = tools.save_draft(run.id, epoch, [change])
    resume = career_db.get(Resume, 1)
    resume.structured_data = {'self_summary': 'New description'}
    resume.updated_at += timedelta(seconds=2)
    career_db.commit()
    edited = run_client.get('/api/resume-versions/' + version_id, headers=headers()).json()
    assert edited['changedInputs'] == ['resume'] and edited['basedOnOldInput'] is True
    assert edited['sources'][0]['content'] == 'Built reliable APIs'
    career_db.delete(resume)
    career_db.commit()
    deleted = run_client.get('/api/resume-versions/' + version_id, headers=headers()).json()
    assert deleted['changedInputs'] == ['resume']
    assert deleted['sources'] == edited['sources']


def test_shared_source_union_is_unique_and_empty_changes_keep_base(proposal, career_db):
    tools, run, epoch, change = proposal
    second = {**deepcopy(change), 'section': '/projects/0/description',
              'before': 'Designed an API', 'after': 'Designed a reliable API'}
    version_id = tools.save_draft(run.id, epoch, [change, second])
    career_db.rollback()
    assert career_db.get(ResumeVersion, version_id).fact_refs == change['fact_refs']
    assert tools.save_draft(run.id, epoch, []) == version_id
    other = agent_runs.create_run(career_db, 1, RunCreate(kind='tailoring', jd_id=1, resume_id=1, request_id='unchanged'))
    other_epoch = agent_runs.claim_run(career_db, other.id)
    empty_id = tools.save_draft(other.id, other_epoch, [])
    career_db.rollback()
    assert career_db.get(ResumeVersion, empty_id).structured_content['changes'] == []


def test_legacy_draft_reports_changed_input_without_inventing_sources(career_db, run_client):
    run = agent_runs.create_run(career_db, 1, RunCreate(
        kind='tailoring', jd_id=1, resume_id=1, request_id='legacy-draft'))
    # T08 Runs kept input_versions but had no fixed context or field-proposal content.
    run.input_json = {'jdId': 1, 'resumeId': 1}
    version_id = str(uuid4())
    career_db.add(ResumeVersion(id=version_id, user_id=1, run_id=run.id,
        resume_id=1, jd_id=1, structured_content={'summary': 'Historical draft'}, fact_refs=[]))
    career_db.commit()
    original = run_client.get('/api/resume-versions/' + version_id, headers=headers()).json()
    assert original['sources'] == [] and original['changedInputs'] == []
    assert original['reviewable'] is False
    resume = career_db.get(Resume, 1)
    resume.structured_data = {'self_summary': 'Changed after the historical draft'}
    resume.updated_at += timedelta(seconds=2)
    career_db.commit()
    detail = run_client.get('/api/resume-versions/' + version_id, headers=headers()).json()
    assert detail['basedOnOldInput'] is True
    assert detail['changedInputs'] == ['resume']
    assert detail['sources'] == []
    assert detail['structuredContent'] == {'summary': 'Historical draft'}
    assert run_client.get('/api/agent/runs/' + run.id + '/artifacts', headers=headers()).json() == [detail]
