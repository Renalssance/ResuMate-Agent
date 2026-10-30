"""Selected confirmed versions stay frozen through the actual autofill HTTP API."""
from copy import deepcopy
from datetime import datetime

import pytest

from backend.db.career_models import ResumeVersion
from backend.db.models import JobApplication, JobDescription, Resume
from backend.tests.career_fixtures import career_db, career_engine
from backend.tests.test_autofill_routes import client


@pytest.fixture
def versions(career_db):
    frozen = {
        'candidate_name': 'Ada Frozen',
        'contact': {'email': 'frozen@example.com'},
        'summary': 'Older summary',
        'self_summary': 'Reviewed API summary',
        'work_experience': [{'company': 'Frozen Company', 'description': 'Reviewed work',
                             'bullets': [{'raw_text': 'Old work bullet'}]}],
        'projects': [{'name': 'Frozen Project', 'description': 'Reviewed project',
                      'bullets': [{'raw_text': 'Old project bullet'}]}],
    }
    rows = [
        ResumeVersion(id='11111111-1111-4111-8111-111111111111', user_id=1,
                      resume_id=1, jd_id=1, revision=3, status='confirmed',
                      created_at=datetime(2026, 10, 29, 8, 30),
                      structured_content={'resume': frozen, 'changes': []}),
        ResumeVersion(id='22222222-2222-4222-8222-222222222222', user_id=1,
                      resume_id=1, jd_id=1, status='draft',
                      structured_content={'resume': {'candidate_name': 'Unreviewed'}, 'changes': []}),
        ResumeVersion(id='33333333-3333-4333-8333-333333333333', user_id=2,
                      status='confirmed', structured_content={'resume': {'candidate_name': 'Private'}}),
    ]
    career_db.add_all(rows)
    career_db.commit()
    return [row.id for row in rows]


def fields(profile):
    return {field['key']: field['value'] for section in profile['sections'] for field in section['fields']}


def test_profiles_list_only_owned_confirmed_versions_with_selection_metadata(client, versions):
    response = client.get('/api/autofill/profiles')
    assert response.status_code == 200
    profiles = {item['id']: item for item in response.json()}
    assert set(profiles) == {'resume:1', 'version:' + versions[0]}
    original = profiles['resume:1']
    assert original['sourceKind'] == 'resume'
    assert original['resumeVersionId'] is None and original['revision'] is None and original['jdId'] is None
    confirmed = profiles['version:' + versions[0]]
    assert confirmed['sourceKind'] == 'resume_version'
    assert confirmed['resumeVersionId'] == versions[0] and confirmed['revision'] == 3
    assert confirmed['jdId'] == 1 and confirmed['sourceResumeId'] == 'resume:1'
    assert confirmed['name'] == 'Ada Frozen'
    assert confirmed['updatedAt'] == '2026-10-29T08:30:00Z'
    assert confirmed['fieldCount'] > 0


def test_confirmed_profile_reads_frozen_content_after_source_edit_and_deletion(client, versions, career_db):
    url = '/api/autofill/profiles/version:' + versions[0]
    before = client.get(url)
    assert before.status_code == 200, before.text
    assert fields(before.json())['self_summary'] == 'Reviewed API summary'
    assert fields(before.json())['work_experience.0.description'] == 'Reviewed work'
    assert before.json()['revision'] == 3
    resume = career_db.get(Resume, 1)
    resume.structured_data = {'candidate_name': 'Reparsed person', 'self_summary': 'Different current content'}
    career_db.commit()
    assert client.get(url).json() == before.json()
    career_db.delete(resume)
    career_db.delete(career_db.get(JobDescription, 1))
    career_db.commit()
    detached = client.get(url)
    assert detached.status_code == 200, detached.text
    assert detached.json()['sections'] == before.json()['sections']
    assert detached.json()['sourceResumeId'] == '' and detached.json()['jdId'] is None
    assert detached.json()['resumeVersionId'] == versions[0]
    assert client.get('/api/autofill/profiles').json()[0]['id'] == 'version:' + versions[0]
    career_db.rollback()
    assert career_db.query(JobApplication).count() == 0


def test_version_clear_edits_do_not_revive_old_summary_or_bullets(client, versions, career_db):
    version = career_db.get(ResumeVersion, versions[0])
    content = deepcopy(version.structured_content)
    content['resume']['self_summary'] = ''
    content['resume']['work_experience'][0]['description'] = ''
    content['resume']['projects'][0]['description'] = ''
    content['changes'] = [
        {'section': '/self_summary', 'status': 'edited'},
        {'section': '/work_experience/0/description', 'status': 'edited'},
        {'section': '/projects/0/description', 'status': 'accepted'},
    ]
    version.structured_content = content  # Seed the final frozen result of review.
    career_db.commit()
    response = client.get('/api/autofill/profiles/version:' + versions[0])
    assert response.status_code == 200, response.text
    profile = fields(response.json())
    assert profile['self_summary'] == ''
    assert profile['work_experience.0.description'] == ''
    assert profile['projects.0.description'] == ''
    career_db.expire_all()
    assert career_db.get(ResumeVersion, versions[0]).structured_content == content


def test_version_preserves_unchanged_bullet_and_summary_fallbacks(client, versions, career_db):
    version = career_db.get(ResumeVersion, versions[0])
    content = deepcopy(version.structured_content)
    del content['resume']['self_summary']
    content['resume']['work_experience'][0]['description'] = ''
    content['resume']['projects'][0]['description'] = ''
    content['changes'] = [{'section': '/projects/0/description', 'status': 'rejected'}]
    version.structured_content = content
    career_db.commit()
    response = client.get('/api/autofill/profiles/version:' + versions[0])
    assert response.status_code == 200, response.text
    profile = fields(response.json())
    assert profile['self_summary'] == 'Older summary'
    assert profile['work_experience.0.description'] == 'Old work bullet'
    assert profile['projects.0.description'] == 'Old project bullet'


@pytest.mark.parametrize('version_index,status', [(1, 409), (2, 404)])
def test_version_detail_and_match_reject_draft_or_other_owner(client, versions, version_index, status):
    profile_id = 'version:' + versions[version_index]
    assert client.get('/api/autofill/profiles/' + profile_id).status_code == status
    response = client.post('/api/autofill/match', json={
        'profileId': profile_id,
        'elements': [{'index': 0, 'tag': 'textarea', 'labelText': '自我介绍'}],
    })
    assert response.status_code == status


def test_online_match_uses_selected_version_over_supplied_profile(client, versions):
    forged = {
        'id': 'version:' + versions[0], 'name': 'Forged', 'sourceResumeId': 'resume:1',
        'updatedAt': '2026-10-30T00:00:00Z',
        'sections': [{'id': 'summary', 'label': 'Summary', 'fields': [{
            'key': 'self_summary', 'label': 'Self Introduction', 'value': 'Unreviewed supplied content',
            'aliases': ['自我介绍'], 'category': 'summary', 'confidence': 'high',
        }]}],
    }
    response = client.post('/api/autofill/match', json={
        'profileId': 'version:' + versions[0], 'profile': forged,
        'elements': [{'index': 0, 'tag': 'textarea', 'labelText': '自我介绍'}],
    })
    assert response.status_code == 200, response.text
    assert response.json()['matches'][0]['field']['value'] == 'Reviewed API summary'
    for profile_id, status in [('version:' + versions[1], 409), ('version:' + versions[2], 404),
                               ('version:missing', 404), ('resume:999', 404)]:
        rejected = client.post('/api/autofill/match', json={
            'profileId': profile_id, 'profile': forged, 'elements': [],
        })
        assert rejected.status_code == status
