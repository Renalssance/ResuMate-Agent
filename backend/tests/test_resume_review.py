"""Review decisions rebuild frozen resumes and use atomic revision checks."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import event

from backend.db.career_models import ProfileFact, ResumeVersion
from backend.db.models import Resume
from backend.tests.career_fixtures import career_engine, career_db
from backend.tests.test_agent_run_routes import run_client, headers
from backend.tests.test_resume_versions import proposal


@pytest.fixture
def review_draft(proposal, run_client):
    tools, run, epoch, change = proposal
    missing = {**deepcopy(change), 'section': '/projects/0/description',
               'before': 'Designed an API', 'after': None, 'requires_input': True,
               'fact_refs': [], 'reason': '请补充本人负责的工作'}
    version_id = tools.save_draft(run.id, epoch, [change, missing])
    response = run_client.get('/api/resume-versions/' + version_id, headers=headers())
    assert response.status_code == 200, response.text
    return response.json()


def decisions(draft, first='accepted', second='rejected'):
    changes = draft['structuredContent']['changes']
    return [{'id': changes[0]['id'], 'status': first}, {'id': changes[1]['id'], 'status': second}]


def save(client, draft, changes, revision=None):
    return client.patch('/api/resume-versions/' + draft['id'], headers=headers(), json={
        'expectedRevision': draft['revision'] if revision is None else revision, 'changes': changes})


def confirm(client, draft, revision=None):
    return client.post('/api/resume-versions/' + draft['id'] + '/confirm', headers=headers(), json={
        'expectedRevision': draft['revision'] if revision is None else revision})


def test_accept_reject_edit_and_undo_rebuild_original_snapshot(review_draft, career_db, run_client):
    original = deepcopy(career_db.get(Resume, 1).structured_data)
    result = save(run_client, review_draft, decisions(review_draft))
    assert result.status_code == 200, result.text
    accepted = result.json()
    assert accepted['reviewable'] is True
    assert accepted['revision'] == 2 and accepted['status'] == 'draft'
    assert accepted['structuredContent']['resume']['self_summary'] == 'Built reliable APIs'
    assert accepted['structuredContent']['resume']['projects'][0]['description'] == 'Designed an API'
    edited = decisions(accepted, first='edited', second='edited')
    edited[0]['editedText'] = ''  # Explicitly clearing an existing field is a supported edit.
    edited[1]['editedText'] = '本人负责 API 接口设计'
    result = save(run_client, accepted, edited)
    assert result.status_code == 200, result.text
    own = result.json()
    assert own['revision'] == 3
    assert own['structuredContent']['resume']['self_summary'] == ''
    assert own['structuredContent']['resume']['projects'][0]['description'] == '本人负责 API 接口设计'
    for before, after in zip(review_draft['structuredContent']['changes'], own['structuredContent']['changes']):
        assert {key: after[key] for key in before if key != 'status'} == {key: value for key, value in before.items() if key != 'status'}
        assert after['status'] == 'edited' and 'editedText' in after
    assert own['factRefs'] == review_draft['factRefs'] and own['sources'] == review_draft['sources']
    undone_response = save(run_client, own, decisions(own, first='pending', second='rejected'))
    assert undone_response.status_code == 200, undone_response.text
    undone = undone_response.json()
    assert undone['structuredContent']['resume'] == original
    assert all('editedText' not in change for change in undone['structuredContent']['changes'])
    career_db.rollback()
    assert career_db.get(Resume, 1).structured_data == original
    assert career_db.query(ProfileFact).count() == 0


def test_saving_after_original_changes_still_uses_run_snapshot(review_draft, career_db, run_client):
    resume = career_db.get(Resume, 1)
    resume.structured_data = {'self_summary': 'New main resume', 'projects': []}
    resume.updated_at += timedelta(seconds=2)
    career_db.commit()
    response = save(run_client, review_draft, decisions(review_draft))
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved['basedOnOldInput'] is True and saved['changedInputs'] == ['resume']
    assert saved['structuredContent']['resume']['projects'][0]['description'] == 'Designed an API'
    assert saved['structuredContent']['resume']['self_summary'] == 'Built reliable APIs'
    career_db.rollback()
    assert career_db.get(Resume, 1).structured_data == {'self_summary': 'New main resume', 'projects': []}


def test_saving_after_original_deleted_keeps_frozen_resume(review_draft, career_db, run_client):
    career_db.delete(career_db.get(Resume, 1))
    career_db.commit()
    response = save(run_client, review_draft, decisions(review_draft))
    assert response.status_code == 200, response.text
    assert response.json()['structuredContent']['resume']['self_summary'] == 'Built reliable APIs'
    assert response.json()['changedInputs'] == ['resume']


@pytest.mark.parametrize('invalid', ['missing', 'duplicate', 'unknown', 'unreviewed_input', 'edited_missing_text',
                                    'edited_null', 'accepted_with_text', 'pending_with_text', 'unknown_status', 'changed_source'])
def test_invalid_decisions_do_not_write_any_part(review_draft, career_db, run_client, invalid):
    changed = decisions(review_draft)
    if invalid == 'missing':
        changed.pop()
    elif invalid == 'duplicate':
        changed[1] = deepcopy(changed[0])
    elif invalid == 'unknown':
        changed[1]['id'] = 'unknown-change'
    elif invalid == 'unreviewed_input':
        changed[1]['status'] = 'accepted'
    elif invalid == 'edited_missing_text':
        changed[1]['status'] = 'edited'
    elif invalid == 'edited_null':
        changed[1].update(status='edited', editedText=None)
    elif invalid == 'accepted_with_text':
        changed[0]['editedText'] = 'Unmarked own claim'
    elif invalid == 'pending_with_text':
        changed[0].update(status='pending', editedText='Unmarked own claim')
    elif invalid == 'unknown_status':
        changed[0]['status'] = 'confirmed'
    else:
        changed[0]['fact_refs'] = []
    response = save(run_client, review_draft, changed)
    assert response.status_code == 422, response.text
    latest = run_client.get('/api/resume-versions/' + review_draft['id'], headers=headers()).json()
    assert latest == review_draft


def test_whole_resume_and_sources_cannot_bypass_decisions(review_draft, run_client):
    response = run_client.patch('/api/resume-versions/' + review_draft['id'], headers=headers(), json={
        'expectedRevision': 1, 'structured_content': {'self_summary': 'Invented'}, 'fact_refs': []})
    assert response.status_code == 422
    assert run_client.get('/api/resume-versions/' + review_draft['id'], headers=headers()).json() == review_draft


def test_pending_cannot_confirm_and_confirmed_version_is_immutable(review_draft, run_client, career_db):
    pending = confirm(run_client, review_draft)
    assert pending.status_code == 422, pending.text
    saved_response = save(run_client, review_draft, decisions(review_draft))
    assert saved_response.status_code == 200, saved_response.text
    saved = saved_response.json()
    stale = confirm(run_client, saved, revision=1)
    assert stale.status_code == 409
    response = confirm(run_client, saved)
    assert response.status_code == 200, response.text
    frozen = response.json()
    assert frozen['revision'] == 3 and frozen['status'] == 'confirmed'
    assert frozen['structuredContent'] == saved['structuredContent']
    assert confirm(run_client, frozen).json() == frozen
    assert confirm(run_client, frozen, revision=2).status_code == 409
    rejected_edit = save(run_client, frozen, decisions(frozen, first='rejected'))
    assert rejected_edit.status_code == 409
    assert run_client.get('/api/resume-versions/' + frozen['id'], headers=headers()).json() == frozen
    career_db.rollback()
    assert career_db.get(Resume, 1).structured_data['self_summary'] == 'Built APIs'
    assert career_db.query(ProfileFact).count() == 0


def test_empty_suggestions_can_confirm_directly(proposal, run_client):
    tools, run, epoch, _ = proposal
    version_id = tools.save_draft(run.id, epoch, [])
    response = confirm(run_client, {'id': version_id, 'revision': 1})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['revision'] == 2 and result['status'] == 'confirmed'
    assert result['structuredContent']['resume']['self_summary'] == 'Built APIs'


def test_legacy_drafts_are_readable_but_cannot_save_or_confirm(career_db, run_client):
    version_id = str(uuid4())
    career_db.add(ResumeVersion(id=version_id, user_id=1, resume_id=1, jd_id=1,
                               structured_content={'summary': 'Historical draft'}, fact_refs=[]))
    career_db.commit()
    draft = run_client.get('/api/resume-versions/' + version_id, headers=headers()).json()
    assert draft['reviewable'] is False
    for response in [save(run_client, draft, []), confirm(run_client, draft)]:
        assert response.status_code == 409
        assert response.json()['code'] == 'legacy_read_only'
    assert run_client.get('/api/resume-versions/' + version_id, headers=headers()).json() == draft


@pytest.mark.parametrize('method,suffix', [('PATCH', ''), ('POST', '/confirm')])
def test_review_requires_ownership_and_authentication(review_draft, run_client, method, suffix):
    body = {'expectedRevision': 1}
    if method == 'PATCH':
        body['changes'] = decisions(review_draft)
    path = '/api/resume-versions/' + review_draft['id'] + suffix
    assert run_client.request(method, path, json=body, headers=headers('bob')).status_code == 404
    assert run_client.request(method, path, json=body).status_code == 401


@pytest.mark.parametrize('operations', [('save', 'save'), ('save', 'confirm'), ('confirm', 'confirm')])
def test_two_readers_at_same_revision_cannot_both_write(review_draft, career_engine, run_client, operations):
    saved_response = save(run_client, review_draft, decisions(review_draft))
    assert saved_response.status_code == 200, saved_response.text
    draft = saved_response.json()
    barrier = Barrier(2)

    def both_have_read_before_update(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('UPDATE RESUME_VERSIONS'):
            barrier.wait(timeout=10)

    event.listen(career_engine, 'before_cursor_execute', both_have_read_before_update)
    try:
        def write(operation):
            if operation == 'confirm':
                return confirm(run_client, draft)
            return save(run_client, draft, decisions(draft, first='rejected'))
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(write, operations))
    finally:
        event.remove(career_engine, 'before_cursor_execute', both_have_read_before_update)
    assert sorted(result.status_code for result in results) == [200, 409], [r.text for r in results]
    winner = next(result.json() for result in results if result.status_code == 200)
    assert winner['revision'] == 3
    assert run_client.get('/api/resume-versions/' + draft['id'], headers=headers()).json() == winner
