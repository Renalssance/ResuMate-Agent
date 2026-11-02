"""Chat uses the same durable admission and SQL ownership as business tasks."""
import pytest
from backend.db.agent_models import AgentRun, AgentSession
from backend.db.models import Resume
from backend.schemas.agent_runs import RunCreate, RunStatus
from backend.services import agent_runs
from backend.tests.career_fixtures import career_engine, career_db
from backend.tests.test_agent_run_routes import run_client, headers


def session(client):
    response = client.post('/api/chat/sessions', json={}, headers=headers())
    assert response.status_code == 201
    return response.json()['sessionId']


def send(client, sid, request='turn-1', **extra):
    return client.post(f'/api/chat/sessions/{sid}/messages', headers=headers(), json={
        'message': '帮我匹配这个岗位', 'requestId': request, **extra})


def test_persistent_chat_admission_replay_and_busy_session(run_client, career_db, monkeypatch):
    sid = session(run_client)
    first = send(run_client, sid)
    assert first.status_code == 202
    assert send(run_client, sid).json() == first.json()
    assert send(run_client, sid, 'turn-2').status_code == 409
    detail = run_client.get(f'/api/chat/sessions/{sid}', headers=headers()).json()
    assert detail['activeRunId'] == first.json()['runId']
    assert detail['turns'][0]['message'] == '帮我匹配这个岗位'
    assert detail['turns'][0]['status'] == 'queued'
    assert detail['title'] == '帮我匹配这个岗位'
    assert run_client.get('/api/chat/sessions', headers=headers('bob')).json() == []
    assert run_client.get(f'/api/chat/sessions/{sid}', headers=headers('bob')).status_code == 404
    assert run_client.post(f'/api/chat/sessions/{sid}/messages', headers=headers('bob'),
        json={'message': 'show history', 'requestId': 'bob'}).status_code == 404


def test_chat_rejects_foreign_context_and_cross_purpose_session(run_client, career_db):
    career_db.add(Resume(id=2, user_id=2, filename='private.pdf'))
    career_db.commit()
    sid = session(run_client)
    assert send(run_client, sid, resumeId=2).status_code == 404
    assert send(run_client, sid, message='  ').status_code == 422
    other = agent_runs.create_run(career_db, 1, RunCreate(kind='tailoring', resumeId=1, jdId=1, requestId='tailor'))
    assert send(run_client, other.session_id).status_code == 404
    result = run_client.post('/api/agent/runs', headers=headers(), json={
        'kind': 'tailoring', 'sessionId': sid, 'resumeId': 1, 'jdId': 1, 'requestId': 'mix'})
    assert result.status_code == 409


def test_chat_history_uses_final_text_and_task_references(run_client, career_db):
    from backend.services.run_events import append_event
    sid = session(run_client)
    rid = send(run_client, sid).json()['runId']
    epoch = agent_runs.claim_run(career_db, rid)
    append_event(career_db, rid, 'assistant.delta', {'text': 'partial'})
    append_event(career_db, rid, 'assistant.reasoning', {'text': '先核对材料'})
    append_event(career_db, rid, 'assistant.reasoning.done', {})
    append_event(career_db, rid, 'tool.started', {'tool_name': 'start_task', 'operation_key': 'call-1'})
    append_event(career_db, rid, 'tool.completed', {'tool_name': 'start_task', 'operation_key': 'call-1', 'result_ref': 'run:child'})
    agent_runs.finish_run(career_db, rid, epoch, RunStatus.SUCCEEDED, result_json={'text': '匹配任务已创建'})
    detail = run_client.get(f'/api/chat/sessions/{sid}', headers=headers()).json()
    assert detail['activeRunId'] is None
    assert detail['turns'][0]['text'] == '匹配任务已创建'
    assert detail['turns'][0]['reasoning'] == '先核对材料'
    assert detail['turns'][0]['reasoningActive'] is False
    assert detail['turns'][0]['tools'] == [{'name': 'start_task', 'operationKey': 'call-1', 'status': 'succeeded', 'resultRef': 'run:child'}]
    assert send(run_client, sid, 'turn-2').status_code == 202


def test_chat_turns_do_not_appear_as_resume_tasks(run_client, career_db):
    sid = session(run_client)
    send(run_client, sid)
    task = agent_runs.create_run(career_db, 1, RunCreate(kind='tailoring', resumeId=1, jdId=1, requestId='material'))
    listed = run_client.get('/api/agent/runs', headers=headers()).json()
    assert [item['runId'] for item in listed['items']] == [task.id]
    assert len(run_client.get(f'/api/chat/sessions/{sid}', headers=headers()).json()['turns']) == 1


def test_chat_attachment_is_queued_with_question_and_safe_history(run_client, career_db, monkeypatch, tmp_path):
    monkeypatch.setenv('DOCUMENT_STORAGE_ROOT', str(tmp_path / 'uploads'))
    sid = session(run_client)
    url = f'/api/chat/sessions/{sid}/messages/upload'
    def upload():
        return run_client.post(url, headers=headers(), data={'message': '总结附件', 'requestId': 'upload-1'},
            files={'file': ('notes.txt', b'meeting notes', 'text/plain')})
    response = upload()
    assert response.status_code == 202
    assert upload().json() == response.json()
    career_db.expire_all()
    run = career_db.get(AgentRun, response.json()['runId'])
    assert run.input_json['attachment']['filename'] == 'notes.txt'
    assert len(list((tmp_path / "uploads").iterdir())) == 1
    detail = run_client.get(f'/api/chat/sessions/{sid}', headers=headers()).json()
    assert detail['turns'][0]['input']['attachment'] == {'filename': 'notes.txt'}
    assert 'sourcePath' not in str(detail)
    assert career_db.query(Resume).count() == 1
