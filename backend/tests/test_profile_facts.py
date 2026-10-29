"""Confirmed facts are append-only versions; runs freeze the versions they read."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
from sqlalchemy.orm import sessionmaker

from backend.db.career_models import ProfileFact, ResumeVersion
from backend.db.models import Resume
from backend.schemas.agent_runs import RunCreate
from backend.services import agent_runs
from backend.tests.career_fixtures import career_engine, career_db
from backend.tests.test_agent_run_routes import run_client, headers, fail_run


URL = '/api/profile-facts'


def create_fact(client, **extra):
    response = client.post(URL, headers=headers(), json={
        'kind': 'experience', 'content': {'text': 'Built APIs', 'company': 'Actual company'}, **extra,
    })
    assert response.status_code == 200, response.text
    return response.json()


def revise(client, fact, **extra):
    return client.patch(URL + '/' + fact['id'], headers=headers(), json={
        'expectedRevision': fact['revision'], 'content': {'text': 'Led API work'}, **extra,
    })


def test_confirmation_is_explicit_and_revisions_preserve_history(run_client):
    first = create_fact(run_client)
    assert first['confirmedAt'] is None and first['revision'] == 1
    assert first['content']['company'] == 'Actual company'
    second = revise(run_client, first, confirmed=True).json()
    assert second['id'] != first['id'] and second['factKey'] == first['factKey']
    assert second['revision'] == 2 and second['confirmedAt'].endswith('+00:00')
    third = revise(run_client, second).json()
    assert third['revision'] == 3 and third['confirmedAt'] is None
    assert run_client.get(URL, headers=headers()).json()['items'] == [third]
    history = run_client.get(URL + '/' + first['id'] + '/history', headers=headers()).json()['items']
    assert history == [first, second, third]


def test_tombstone_hides_family_without_reviving_older_confirmed_version(run_client):
    first = create_fact(run_client, confirmed=True)
    deleted = run_client.delete(URL + '/' + first['id'] + '?expectedRevision=1', headers=headers())
    assert deleted.status_code == 200
    tombstone = deleted.json()
    assert tombstone['revision'] == 2 and tombstone['deletedAt'].endswith('+00:00')
    assert run_client.get(URL, headers=headers()).json() == {'items': []}
    assert run_client.get(URL + '?includeDeleted=true', headers=headers()).json() == {'items': [tombstone]}
    assert revise(run_client, first).status_code == 409
    assert revise(run_client, tombstone).status_code == 409
    assert run_client.delete(URL + '/' + first['id'] + '?expectedRevision=1', headers=headers()).status_code == 409


def test_scope_includes_global_and_selected_resume_only(run_client, career_db):
    career_db.add_all([Resume(id=2, user_id=1, filename='second.txt'), Resume(id=3, user_id=2, filename='bob.txt')])
    career_db.commit()
    global_fact = create_fact(run_client, kind='preference')
    selected = create_fact(run_client, sourceDocumentId=1)
    other = create_fact(run_client, sourceDocumentId=2)
    items = run_client.get(URL + '?sourceDocumentId=1', headers=headers()).json()['items']
    assert {f['id'] for f in items} == {global_fact['id'], selected['id']}
    assert len(run_client.get(URL, headers=headers()).json()['items']) == 3
    body = {'kind': 'experience', 'content': {'text': 'private'}, 'sourceDocumentId': 3}
    assert run_client.post(URL, headers=headers(), json=body).status_code == 404
    assert run_client.get(URL + '?sourceDocumentId=3', headers=headers()).status_code == 404
    for method, path, body in [('PATCH', '/' + other['id'], {'content': {'text': 'spoof'}, 'expectedRevision': 1}),
                               ('DELETE', '/' + other['id'] + '?expectedRevision=1', None),
                               ('GET', '/' + other['id'] + '/history', None)]:
        assert run_client.request(method, URL + path, headers=headers('bob'), json=body).status_code == 404
    assert run_client.get(URL).status_code == 401


@pytest.mark.parametrize('body', [
    {'kind': 'project', 'content': {'text': 'real'}},
    {'kind': 'experience', 'content': {'text': '  '}},
    {'kind': 'experience', 'content': {'role': 'developer'}},
    {'kind': 'experience', 'content': {'text': 'real'}, 'user_id': 2},
    {'kind': 'experience', 'content': {'text': 'real'}, 'confirmed': 'true'},
])
def test_fact_input_rejects_missing_text_and_spoofed_owner(run_client, body):
    assert run_client.post(URL, headers=headers(), json=body).status_code == 422


def test_concurrent_edit_keeps_one_next_revision_and_returns_conflict(run_client, career_db):
    first = create_fact(run_client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda n: revise(run_client, first, content={'text': f'Edit {n}'}), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    career_db.rollback()
    assert career_db.query(ProfileFact).count() == 2
    assert revise(run_client, first, expectedRevision=9).status_code == 409


@pytest.fixture
def fact_tools(career_engine, monkeypatch):
    from backend.agent_runtime import tools
    monkeypatch.setattr(tools, 'SessionLocal', sessionmaker(career_engine, autoflush=False, expire_on_commit=False))
    return tools


def run(db, request_id='facts-run'):
    return agent_runs.create_run(db, 1, RunCreate(kind='tailoring', jd_id=1, resume_id=1, request_id=request_id))


def test_run_freezes_latest_confirmed_scope_and_old_context_survives_edit(run_client, career_db, fact_tools):
    career_db.add_all([Resume(id=2, user_id=1, filename='second.txt'), Resume(id=3, user_id=2, filename='bob.txt')])
    career_db.commit()
    first = create_fact(run_client, confirmed=True)
    selected = create_fact(run_client, sourceDocumentId=1, confirmed=True)
    create_fact(run_client, sourceDocumentId=2, confirmed=True)
    hidden = create_fact(run_client, confirmed=True)
    revise(run_client, hidden)  # Latest unconfirmed version must suppress the confirmed predecessor.
    career_db.add(ProfileFact(user_id=2, fact_key='foreign', kind='experience', content={'text': 'Bob'}, confirmed_at=datetime.now()))
    career_db.commit()
    old = run(career_db)
    expected = [{'factId': first['id'], 'revision': 1}, {'factId': selected['id'], 'revision': 1}]
    assert sorted(old.input_versions['facts'], key=lambda x: x['factId']) == sorted(expected, key=lambda x: x['factId'])
    updated = revise(run_client, first, confirmed=True).json()
    epoch = agent_runs.claim_run(career_db, old.id)
    context = fact_tools.application_context(old.id, epoch)
    assert {f['id'] for f in context['facts']} == {first['id'], selected['id']}
    assert next(f for f in context['facts'] if f['id'] == first['id'])['content']['text'] == 'Built APIs'
    newer = run(career_db, 'new-facts-run')
    assert {f['factId'] for f in newer.input_versions['facts']} == {updated['id'], selected['id']}
    fail_run(career_db, old.id)
    assert agent_runs.retry_run(career_db, 1, old.id).status == 'queued'


def test_draft_only_cites_frozen_versions_and_rejects_deleted_family(run_client, career_db, fact_tools):
    first = create_fact(run_client, confirmed=True)
    old = run(career_db)
    epoch = agent_runs.claim_run(career_db, old.id)
    another = run(career_db, 'deleted-facts-run')
    updated = revise(run_client, first, confirmed=True).json()
    with pytest.raises(agent_runs.RunError) as outside:
        fact_tools.save_draft(old.id, epoch, {}, [updated['id']])
    assert outside.value.code == 'invalid_fact'
    artifact_id = fact_tools.save_draft(old.id, epoch, {'summary': 'Old fact'}, [first['id']])
    assert run_client.delete(URL + '/' + updated['id'] + '?expectedRevision=2', headers=headers()).status_code == 200
    # Replaying a completed operation preserves the historical artifact.
    assert fact_tools.save_draft(old.id, epoch, {}, [first['id']]) == artifact_id
    other_epoch = agent_runs.claim_run(career_db, another.id)
    with pytest.raises(agent_runs.RunError) as deleted:
        fact_tools.save_draft(another.id, other_epoch, {}, [first['id']])
    assert deleted.value.code == 'invalid_fact'
    career_db.rollback()
    assert career_db.get(ResumeVersion, artifact_id).fact_refs == [{'factId': first['id'], 'revision': 1}]


def test_pre_t08_run_without_fact_snapshot_reads_empty_and_cannot_cite_today(run_client, career_db, fact_tools):
    first = create_fact(run_client, confirmed=True)
    old = run(career_db)
    old.input_versions = {key: value for key, value in old.input_versions.items() if key != 'facts'}
    career_db.commit()
    epoch = agent_runs.claim_run(career_db, old.id)
    assert fact_tools.application_context(old.id, epoch)['facts'] == []
    with pytest.raises(agent_runs.RunError) as error:
        fact_tools.save_draft(old.id, epoch, {}, [first['id']])
    assert error.value.code == 'invalid_fact'


def test_deleting_source_resume_tombstones_facts_before_they_can_become_global(run_client, career_db, monkeypatch):
    from types import SimpleNamespace
    from backend.routes import documents
    # Document deletion also removes external RAG chunks; keep this test on the real SQL transaction.
    monkeypatch.setattr(documents, 'get_rag_store', lambda: SimpleNamespace(delete_document=lambda **kwargs: None))
    career_db.add(Resume(id=2, user_id=1, filename='resume-b.txt'))
    career_db.commit()
    source_v1 = create_fact(run_client, sourceDocumentId=1, confirmed=True)
    assert revise(run_client, source_v1, confirmed=True).status_code == 200
    unconfirmed = create_fact(run_client, sourceDocumentId=1)
    already_deleted = create_fact(run_client, sourceDocumentId=1, confirmed=True)
    assert run_client.delete(URL + '/' + already_deleted['id'] + '?expectedRevision=1', headers=headers()).status_code == 200
    global_fact = create_fact(run_client, confirmed=True)
    other_resume = create_fact(run_client, sourceDocumentId=2, confirmed=True)

    response = run_client.delete('/api/documents/resume:1', headers=headers())
    assert response.status_code == 200
    career_db.rollback()
    newer = agent_runs.create_run(career_db, 1, RunCreate(
        kind='tailoring', jd_id=1, resume_id=2, request_id='after-source-delete'))
    assert {ref['factId'] for ref in newer.input_versions['facts']} == {global_fact['id'], other_resume['id']}
    history = run_client.get(URL + '/' + source_v1['id'] + '/history', headers=headers()).json()['items']
    assert [fact['revision'] for fact in history] == [1, 2, 3]
    assert [fact['content']['text'] for fact in history] == ['Built APIs', 'Led API work', 'Led API work']
    assert history[0]['confirmedAt'] and history[1]['confirmedAt']
    assert history[2]['deletedAt'] and history[2]['sourceDocumentId'] is None
    assert {fact['id'] for fact in run_client.get(URL, headers=headers()).json()['items']} == {global_fact['id'], other_resume['id']}
    unconfirmed_history = run_client.get(URL + '/' + unconfirmed['id'] + '/history', headers=headers()).json()['items']
    assert [fact['revision'] for fact in unconfirmed_history] == [1, 2]
    assert unconfirmed_history[-1]['deletedAt']
    deleted_history = run_client.get(URL + '/' + already_deleted['id'] + '/history', headers=headers()).json()['items']
    assert [fact['revision'] for fact in deleted_history] == [1, 2]
