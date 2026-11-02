"""Real Deep Agents and SQLite checkpoints with a deterministic tool-calling model."""
import json
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from sqlalchemy.orm import sessionmaker
from backend.db.agent_models import AgentRun, ToolOperation
from backend.db.models import Resume, JobApplication
from backend.schemas.agent_runs import RunCreate, RunStatus
from backend.services import agent_runs
from backend.tests.agent_fixtures import DraftModel
from backend.tests.career_fixtures import career_engine, career_db


class ChatModel(DraftModel):
    action: str = 'match'

    def _generate(self, messages, **kwargs):
        if self.action == 'fail':
            raise ValueError('model failed')
        result = self._reply(messages)
        result.generations[0].message.usage_metadata = {
            'input_tokens': 10, 'output_tokens': 5, 'total_tokens': 15}
        return result

    def _reply(self, messages):
        humans = [m for m in messages if isinstance(m, HumanMessage)]
        current = next(i for i in range(len(messages)-1, -1, -1) if isinstance(messages[i], HumanMessage))
        replies = [m for m in messages[current:] if isinstance(m, ToolMessage)]
        if self.action == 'remember':
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content='记得：' + humans[0].content))])
        if not replies:
            name, args = ('list_documents', {})
        elif len(replies) == 1:
            name, args = ('start_task', {'kind': 'match_analysis', 'jd_id': 1, 'resume_id': 1})
            if self.action == 'foreign':
                args['resume_id'] = 2
            if self.action == 'application':
                name, args = 'record_application', {'company': '测试公司', 'position': '工程师', 'applied_date': '2026-10-30'}
        else:
            content = '工具失败' if json.loads(replies[-1].content).get('error') else '已创建，请查看任务卡片。'
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content='', tool_calls=[{
            'name': name, 'args': args, 'id': f'call-{len(humans)}-{len(replies)}', 'type': 'tool_call'}]))])


@pytest.fixture
def runtime(career_db, career_engine, monkeypatch, tmp_path):
    from backend.agent_runtime import chat, chat_tools, factory
    sessions = sessionmaker(career_engine, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr(chat, 'SessionLocal', sessions)
    monkeypatch.setattr('backend.services.llm_settings.SessionLocal', sessions)
    monkeypatch.setattr(chat_tools, 'SessionLocal', sessions)
    monkeypatch.setattr(chat_tools, 'publish_run', lambda rid: True)
    monkeypatch.setenv('AGENT_STATE_DIR', str(tmp_path))
    model = ChatModel()
    monkeypatch.setattr(factory, 'model_for_user', lambda uid: model)
    return chat, model


def new_chat(db, **extra):
    return agent_runs.create_run(db, 1, RunCreate(kind='chat', message='我是 API 工程师', requestId='chat-1', **extra))


def execute(runtime, db, run):
    runtime[0].run_chat(run.id, agent_runs.claim_run(db, run.id))
    db.expire_all()
    return db.get(AgentRun, run.id)


def test_chat_calls_real_tools_creates_durable_match_and_resumes_history(runtime, career_db):
    first = execute(runtime, career_db, new_chat(career_db))
    assert first.status == RunStatus.SUCCEEDED
    child = career_db.query(AgentRun).filter_by(kind='match_analysis').one()
    assert child.status == RunStatus.QUEUED
    assert child.input_json['resumeIds'] == [1]
    assert child.session_id != first.session_id
    assert first.output_refs == [{'type': 'run', 'id': child.id}]
    assert first.result_json['text'] == '已创建，请查看任务卡片。'
    runtime[1].action = 'remember'
    second = agent_runs.create_run(career_db, 1, RunCreate(kind='chat', message='我刚才的职业是什么？',
        requestId='chat-2', sessionId=first.session_id))
    assert 'API 工程师' in execute(runtime, career_db, second).result_json['text']


def test_tools_do_not_expose_or_schedule_foreign_resume(runtime, career_db):
    career_db.add(Resume(id=2, user_id=2, filename='private.pdf'))
    career_db.commit()
    runtime[1].action = 'foreign'
    run = execute(runtime, career_db, new_chat(career_db))
    assert run.result_json['text'] == '工具失败'
    assert career_db.query(AgentRun).filter_by(kind='match_analysis').count() == 0


def test_application_tool_writes_record_and_status_event(runtime, career_db):
    runtime[1].action = 'application'
    run = execute(runtime, career_db, new_chat(career_db))
    assert run.status == RunStatus.SUCCEEDED
    row = career_db.query(JobApplication).one()
    assert row.company == '测试公司' and row.user_id == 1
    assert len(row.status_events) == 1
    assert run.output_refs == [{'type': 'application', 'id': str(row.id)}]


def tool_context(runtime, db):
    from backend.agent_runtime.chat_tools import career_tools
    run = new_chat(db)
    epoch = agent_runs.claim_run(db, run.id)
    return run, {item.name: item.func for item in career_tools(run.id, epoch)}


def test_tool_replay_creates_one_application_and_one_status_event(runtime, career_db):
    from types import SimpleNamespace
    run, tools = tool_context(runtime, career_db)
    args = dict(company='Replay Co', position='Engineer', applied_date='2026-10-30',
                runtime=SimpleNamespace(tool_call_id='save-application'))
    first = tools['record_application'](**args)
    second = tools['record_application'](**args)
    assert first['resultRef'] == second['resultRef']
    career_db.expire_all()
    row = career_db.query(JobApplication).one()
    assert len(row.status_events) == 1
    changed = tools['update_application_status'](row.id, 'offer', SimpleNamespace(tool_call_id='update-status'), note='收到 offer')
    assert changed['status'] == 'offer'
    career_db.expire_all()
    assert career_db.get(JobApplication, row.id).status == 'offer'
    assert len(career_db.get(JobApplication, row.id).status_events) == 2


def test_tool_document_scope_job_capture_and_parse_submission(runtime, career_db):
    from types import SimpleNamespace
    run, tools = tool_context(runtime, career_db)
    career_db.add(Resume(id=2, user_id=2, filename='private.pdf', raw_text='private experience'))
    career_db.commit()
    ctx = SimpleNamespace(tool_call_id='list')
    documents = tools['list_documents'](ctx)['documents']
    assert all(item['documentId'] != 'resume:2' for item in documents)
    assert 'error' in tools['read_document']('resume:2', ctx)
    saved = tools['save_job']('Python 工程师', 'Example', '编写 Python API', SimpleNamespace(tool_call_id='save'))
    assert saved['jdId'] > 1
    parsed = tools['start_task']('document_parse', SimpleNamespace(tool_call_id='parse'), document_id=saved['resultRef'])
    career_db.expire_all()
    child = career_db.get(AgentRun, parsed['runId'])
    assert child.input_json['parseMode'] == 'saved_job'
    assert child.input_json['documentId'] == saved['resultRef']
    assert tools['get_task'](child.id, ctx)['status'] == 'queued'
    drafting = tools['start_task']('tailoring', SimpleNamespace(tool_call_id='draft'), resume_id=1, jd_id=1)
    career_db.expire_all()
    assert career_db.get(AgentRun, drafting['runId']).kind == 'tailoring'


def test_foreign_application_update_and_unconfirmed_export_do_not_write(runtime, career_db):
    from types import SimpleNamespace
    from datetime import date
    run, tools = tool_context(runtime, career_db)
    career_db.add(JobApplication(id=10, user_id=2, company='private', position='engineer', applied_date=date(2026, 10, 30)))
    career_db.commit()
    assert 'error' in tools['update_application_status'](10, 'offer', SimpleNamespace(tool_call_id='foreign'))
    assert 'error' in tools['start_task']('resume_export', SimpleNamespace(tool_call_id='export'), resume_version_id='missing')
    career_db.expire_all()
    assert career_db.get(JobApplication, 10).status == 'applied'
    assert career_db.query(AgentRun).filter_by(kind='resume_export').count() == 0


def test_cancelled_chat_cannot_write_through_tools(runtime, career_db):
    from types import SimpleNamespace
    run, tools = tool_context(runtime, career_db)
    agent_runs.cancel_run(career_db, 1, run.id)
    with pytest.raises(agent_runs.RunError, match='取消'):
        tools['record_application']('Company', 'Engineer', '2026-10-30', SimpleNamespace(tool_call_id='late'))
    assert career_db.query(JobApplication).count() == 0


def test_interview_tools_preserve_actual_answer_and_queue_next_turn(runtime, career_db):
    from types import SimpleNamespace
    from backend.tests.interview_fixtures import seed_application, seed_question
    from backend.db.career_models import InterviewTurn
    seed_application(career_db)
    run, tools = tool_context(runtime, career_db)
    created = tools['start_interview'](1, SimpleNamespace(tool_call_id='start-interview'))
    assert created['status'] == 'queued'
    seed_question(career_db, created)
    snapshot = tools['get_interview'](created['interviewId'], SimpleNamespace(tool_call_id='read-interview'))
    assert snapshot['turns'][0]['question'] == 'How did you build the API?'
    answer = tools['answer_interview'](created['interviewId'], 1, '我用一个 SQL 事务保证一致性',
                                       SimpleNamespace(tool_call_id='answer'))
    assert answer['status'] == 'queued'
    career_db.expire_all()
    assert career_db.query(InterviewTurn).one().answer == '我用一个 SQL 事务保证一致性'
    assert {'type': 'run', 'id': created['runId']} in career_db.get(AgentRun, run.id).output_refs


def test_attachment_content_reaches_answer_and_notice_survives_history(runtime, career_db, career_engine, tmp_path, monkeypatch):
    from backend.services import chat_attachments
    monkeypatch.setattr(chat_attachments, 'SessionLocal', sessionmaker(career_engine, expire_on_commit=False))
    runtime[1].action = 'remember'
    source = tmp_path / 'copy.txt'
    source.write_text('uploaded bytes')
    resume = career_db.get(Resume, 1)
    resume.content_hash = 'same-file'
    resume.raw_text = '我擅长 PostgreSQL 查询优化'
    career_db.commit()
    run = new_chat(career_db)
    run.input_json = {**run.input_json, 'attachment': {'filename': 'copy.txt', 'sourcePath': str(source),
        'contentHash': 'same-file', 'size': 14}}
    career_db.commit()
    completed = execute(runtime, career_db, run)
    assert completed.status == RunStatus.SUCCEEDED
    assert completed.result_json['text'].startswith('资料库中已有文件：resume.txt。')
    assert 'PostgreSQL' in completed.result_json['text']
    assert 'resumeId": 1' in completed.result_json['text']
    assert not source.exists()


def test_chat_usage_reaches_settings_without_recounting_history(runtime, career_db):
    from backend.services.llm_settings import usage_dashboard
    first = execute(runtime, career_db, new_chat(career_db))
    dashboard = usage_dashboard(1, career_db)
    assert dashboard.total_calls == 3
    assert (dashboard.prompt_tokens, dashboard.completion_tokens, dashboard.total_tokens) == (30, 15, 45)
    assert dashboard.by_task[0].task == 'chat'
    assert dashboard.daily[0].total_tokens == 45
    assert all(call.success and call.model for call in dashboard.recent_calls)
    assert usage_dashboard(2, career_db).total_calls == 0
    runtime[1].action = 'remember'
    second = agent_runs.create_run(career_db, 1, RunCreate(kind='chat', message='继续',
        requestId='usage-second', sessionId=first.session_id))
    execute(runtime, career_db, second)
    dashboard = usage_dashboard(1, career_db)
    assert dashboard.total_calls == 4
    assert dashboard.total_tokens == 60


def test_failed_chat_model_call_reaches_settings(runtime, career_db):
    from backend.services.llm_settings import usage_dashboard
    runtime[1].action = 'fail'
    assert execute(runtime, career_db, new_chat(career_db)).status == RunStatus.FAILED
    dashboard = usage_dashboard(1, career_db)
    assert dashboard.failed_calls == 1
    assert dashboard.total_tokens == 0
    assert dashboard.recent_calls[0].error_type == 'ValueError'


def test_application_statistics_stay_inline_instead_of_offloading_full_records(runtime, career_db, monkeypatch):
    from datetime import date
    from collections import Counter
    calls = []

    def reply(self, messages):
        calls.append(1)
        tools = [m for m in messages if isinstance(m, ToolMessage)]
        if not tools:
            message = AIMessage(content='', tool_calls=[{'name': 'list_applications', 'args': {}, 'id': 'applications', 'type': 'tool_call'}])
        else:
            data = json.loads(tools[-1].content)
            assert data['total'] == 124
            assert data['by_company'] == {'公司甲': 80, '公司乙': 44}
            assert data['by_position'] == {'后端工程师': 124}
            assert data['by_status'] == {'applied': 124}
            assert len(data['applications']) == 124
            assert Counter(row['company'] for row in data['applications']) == data['by_company']
            assert all(set(row) == {'id', 'company', 'position', 'applied_date', 'status'} for row in data['applications'])
            message = AIMessage(content='共投递 124 次，以后端工程师为主。')
        return ChatResult(generations=[ChatGeneration(message=message)])

    monkeypatch.setattr(ChatModel, '_reply', reply)
    for index in range(124):
        career_db.add(JobApplication(user_id=1, company='公司甲' if index < 80 else '公司乙',
            position='后端工程师', applied_date=date(2026, 10, 31), status='applied',
            job_url='https://example.com/jobs/' + str(index), notes='投递备注',
            submitted_snapshot={'resume_text': '已确认的简历材料' * 100}))
    career_db.add(JobApplication(user_id=2, company='其他用户的公司', position='其他岗位', applied_date=date(2026, 10, 31)))
    career_db.commit()
    run = execute(runtime, career_db, new_chat(career_db))
    assert run.status == RunStatus.SUCCEEDED
    assert run.result_json['text'] == '共投递 124 次，以后端工程师为主。'
    assert len(calls) == 2


@pytest.mark.parametrize('application_id,expected', [(1, '面试安排'), (2, '工具失败')])
def test_application_detail_keeps_notes_and_checks_ownership(runtime, career_db, monkeypatch, application_id, expected):
    from datetime import date
    for identifier, owner in [(1, 1), (2, 2)]:
        career_db.add(JobApplication(id=identifier, user_id=owner, company='公司', position='工程师',
            applied_date=date(2026, 10, 31), notes='面试安排'))
    career_db.commit()

    def reply(self, messages):
        tools = [m for m in messages if isinstance(m, ToolMessage)]
        if not tools:
            message = AIMessage(content='', tool_calls=[{'name': 'list_applications',
                'args': {'application_id': application_id}, 'id': 'detail', 'type': 'tool_call'}])
        else:
            data = json.loads(tools[-1].content)
            message = AIMessage(content='工具失败' if data.get('error') else data['application']['notes'])
        return ChatResult(generations=[ChatGeneration(message=message)])

    monkeypatch.setattr(ChatModel, '_reply', reply)
    run = execute(runtime, career_db, new_chat(career_db))
    assert run.status == RunStatus.SUCCEEDED
    assert run.result_json['text'] == expected
