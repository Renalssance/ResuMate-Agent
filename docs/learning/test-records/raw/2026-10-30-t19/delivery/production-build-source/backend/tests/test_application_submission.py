"""A submitted application keeps the exact reviewed version chosen by its owner."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest

from backend.db.career_models import ResumeVersion
from backend.db.models import JobApplication, JobDescription, Resume
from backend.tests.career_fixtures import career_engine, career_db
from backend.tests.test_agent_run_routes import run_client, headers


@pytest.fixture
def submission_material(career_db):
    career_db.add_all([
        JobDescription(id=2, user_id=1, title='Another role', raw_text='Other requirements'),
        JobDescription(id=3, user_id=2, title='Private role', raw_text='Private requirements'),
        Resume(id=2, user_id=1, filename='another-resume.txt', structured_data={}),
    ])
    career_db.flush()
    content = {'resume': {'candidate_name': '林同学', 'self_summary': '已确认的 API 项目经历'},
               'changes': [], 'inputVersions': {'resume': 'fixed-source'}}
    references = [{'kind': 'resume', 'resumeId': 1, 'inputVersion': 'fixed-source',
                   'section': '/self_summary', 'sourceRefs': []}]
    career_db.add_all([
        ResumeVersion(id='confirmed-a', user_id=1, resume_id=1, jd_id=1, revision=3,
                      status='confirmed', structured_content=content, fact_refs=references),
        ResumeVersion(id='confirmed-b', user_id=1, resume_id=1, jd_id=1, revision=4,
                      status='confirmed', structured_content={'resume': {'self_summary': '另一版材料'}},
                      fact_refs=[]),
        ResumeVersion(id='draft', user_id=1, resume_id=1, jd_id=1, status='draft',
                      structured_content=content, fact_refs=references),
        ResumeVersion(id='foreign', user_id=2, jd_id=3, status='confirmed',
                      structured_content={'resume': {'self_summary': 'Private content'}}, fact_refs=[]),
    ])
    career_db.commit()
    return content, references


def _create_application(client, **extra):
    response = client.post('/api/applications', headers=headers(), json={
        'company': '示例公司', 'position': '后端开发', 'applied_date': '2026-10-30', **extra,
    })
    assert response.status_code == 200, response.text
    return response.json()


def _attach(client, application_id, *, user='alice', **extra):
    return client.put(f'/api/applications/{application_id}/submission', headers=headers(user), json={
        'jd_id': 1, 'resume_version_id': 'confirmed-a', **extra,
    })


def test_submission_freezes_version_and_duplicate_returns_original(submission_material, run_client):
    content, references = submission_material
    application = _create_application(run_client)
    first = _attach(run_client, application['id'])
    assert first.status_code == 200, first.text
    record = first.json()
    snapshot = record['submitted_snapshot']
    assert record['jd_id'] == 1
    assert record['resume_version_id'] == 'confirmed-a'
    assert record['resume_id'] == 1
    assert record['resume_filename'] == 'resume.txt'
    assert snapshot == {'resumeVersionId': 'confirmed-a', 'revision': 3, 'jdId': 1,
                        'structuredContent': content, 'factRefs': references,
                        'submittedAt': snapshot['submittedAt']}
    assert datetime.fromisoformat(snapshot['submittedAt'].replace('Z', '+00:00')).utcoffset().total_seconds() == 0
    repeated = _attach(run_client, application['id'])
    assert repeated.status_code == 200
    assert repeated.json() == record
    listed = run_client.get('/api/applications', headers=headers()).json()
    assert listed[0]['submitted_snapshot'] == snapshot


def test_submission_replaces_old_original_link_once(submission_material, run_client):
    application = _create_application(run_client, resume_id=2)
    assert application['resume_filename'] == 'another-resume.txt'
    attached = _attach(run_client, application['id'])
    assert attached.status_code == 200, attached.text
    assert attached.json()['resume_id'] == 1
    assert attached.json()['resume_filename'] == 'resume.txt'


def test_submission_rejects_replacement_version(submission_material, run_client):
    application = _create_application(run_client)
    first = _attach(run_client, application['id'])
    assert first.status_code == 200, first.text
    replacement = _attach(run_client, application['id'], resume_version_id='confirmed-b')
    assert replacement.status_code == 409
    assert run_client.get('/api/applications', headers=headers()).json()[0] == first.json()


@pytest.mark.parametrize(('extra', 'status'), [
    ({'resume_version_id': 'draft'}, 409),
    ({'jd_id': 2}, 409),
    ({'jd_id': 3}, 404),
    ({'resume_version_id': 'foreign'}, 404),
    ({'resume_version_id': 'missing'}, 404),
    ({'jd_id': 999}, 404),
    ({'user': 'bob'}, 404),
])
def test_submission_checks_owned_confirmed_matching_material(submission_material, run_client, career_db, extra, status):
    application = _create_application(run_client)
    response = _attach(run_client, application['id'], **extra)
    assert response.status_code == status, response.text
    career_db.rollback()
    stored = career_db.get(JobApplication, application['id'])
    assert stored.jd_id is None
    assert stored.resume_version_id is None
    assert stored.submitted_snapshot is None


def test_concurrent_submissions_keep_only_one_material(submission_material, run_client):
    application = _create_application(run_client)
    with ThreadPoolExecutor(max_workers=2) as workers:
        responses = list(workers.map(
            lambda version: _attach(run_client, application['id'], resume_version_id=version),
            ['confirmed-a', 'confirmed-b'],
        ))
    assert sorted(response.status_code for response in responses) == [200, 409]
    winner = next(response.json() for response in responses if response.status_code == 200)
    stored = run_client.get('/api/applications', headers=headers()).json()[0]
    assert stored['resume_version_id'] == winner['resume_version_id']
    assert stored['submitted_snapshot'] == winner['submitted_snapshot']


def test_create_application_with_submission_is_one_saved_record(submission_material, run_client, career_db):
    record = _create_application(run_client, jd_id=1, resume_version_id='confirmed-a')
    assert record['submitted_snapshot'] is not None
    assert record['jd_id'] == 1
    assert record['resume_version_id'] == 'confirmed-a'
    assert record['resume_id'] == 1
    assert record['submitted_snapshot']['revision'] == 3
    assert len(record['status_events']) == 1
    career_db.rollback()
    assert career_db.query(JobApplication).count() == 1


@pytest.mark.parametrize('extra', [
    {'jd_id': 1}, {'resume_version_id': 'confirmed-a'},
    {'jd_id': None, 'resume_version_id': 'confirmed-a'},
    {'jd_id': 1, 'resume_version_id': None},
])
def test_create_requires_paired_submission_identifiers(submission_material, run_client, career_db, extra):
    response = run_client.post('/api/applications', headers=headers(), json={
        'company': 'Invalid submission', 'position': 'Engineer', 'applied_date': '2026-10-30', **extra,
    })
    assert response.status_code == 422, response.text
    career_db.rollback()
    assert career_db.query(JobApplication).count() == 0


@pytest.mark.parametrize(('extra', 'status'), [
    ({'resume_version_id': 'draft'}, 409),
    ({'jd_id': 2}, 409),
    ({'jd_id': 3, 'resume_version_id': 'foreign'}, 404),
])
def test_create_rolls_back_when_submission_is_rejected(submission_material, run_client, career_db, extra, status):
    from backend.db.models import JobApplicationStatusEvent
    response = run_client.post('/api/applications', headers=headers(), json={
        'company': 'Invalid submission', 'position': 'Engineer', 'applied_date': '2026-10-30',
        'jd_id': 1, 'resume_version_id': 'confirmed-a', **extra,
    })
    assert response.status_code == status, response.text
    career_db.rollback()
    assert career_db.query(JobApplication).count() == 0
    assert career_db.query(JobApplicationStatusEvent).count() == 0


@pytest.mark.parametrize('resume_id', [2, None])
def test_patch_cannot_change_submitted_original_resume(submission_material, run_client, resume_id):
    application = _create_application(run_client)
    first = _attach(run_client, application['id']).json()
    changed = run_client.patch(f"/api/applications/{application['id']}", headers=headers(), json={
        'resume_id': resume_id, 'notes': 'This entire edit must fail',
    })
    assert changed.status_code == 409, changed.text
    assert run_client.get('/api/applications', headers=headers()).json()[0] == first


def test_submitted_record_remains_editable_without_replacing_snapshot(submission_material, run_client):
    application = _create_application(run_client)
    first = _attach(run_client, application['id']).json()
    edited = run_client.patch(f"/api/applications/{application['id']}", headers=headers(), json={
        'resume_id': 1, 'company': 'Updated company', 'position': 'Updated role',
        'applied_date': '2026-10-29', 'status': 'interviewing', 'notes': 'Interview planned',
        'jd_id': 2, 'resume_version_id': 'confirmed-b', 'submitted_snapshot': {'arbitrary': 'client value'},
    })
    assert edited.status_code == 200, edited.text
    record = edited.json()
    assert record['company'] == 'Updated company'
    assert record['position'] == 'Updated role'
    assert record['applied_date'] == '2026-10-29'
    assert record['notes'] == 'Interview planned'
    assert record['status'] == 'interviewing'
    assert record['jd_id'] == 1 and record['resume_version_id'] == 'confirmed-a'
    assert record['submitted_snapshot'] == first['submitted_snapshot']
    schedule = run_client.post(f"/api/applications/{application['id']}/schedules", headers=headers(), json={
        'status': 'first_interview', 'title': '面试',
        'starts_at': '2099-10-30T10:00:00Z', 'ends_at': '2099-10-30T11:00:00Z',
    })
    assert schedule.status_code == 200
    assert schedule.json()['submitted_snapshot'] == first['submitted_snapshot']
    assert schedule.json()['schedules'][0]['title'] == '面试'


def test_main_resume_edits_and_deletion_leave_submission_unchanged(submission_material, run_client, career_db):
    application = _create_application(run_client)
    original = _attach(run_client, application['id']).json()['submitted_snapshot']
    resume = career_db.get(Resume, 1)
    resume.structured_data = {'self_summary': 'Changed after submission'}
    career_db.commit()
    edited = run_client.get('/api/applications', headers=headers()).json()[0]
    assert edited['submitted_snapshot'] == original
    career_db.delete(resume)
    career_db.commit()
    deleted = run_client.get('/api/applications', headers=headers()).json()[0]
    assert deleted['resume_id'] is None
    assert deleted['resume_filename'] == ''
    assert deleted['submitted_snapshot'] == original
    repeated = _attach(run_client, application['id'])
    assert repeated.status_code == 200
    assert repeated.json()['submitted_snapshot'] == original
    patched = run_client.patch(f"/api/applications/{application['id']}", headers=headers(), json={
        'resume_id': None, 'notes': 'The source document was deleted',
    })
    assert patched.status_code == 200
    assert patched.json()['submitted_snapshot'] == original
