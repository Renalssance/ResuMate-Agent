"""Context boundaries through real SQL, SDK middleware and disk checkpoints."""
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import sessionmaker

from backend.db.agent_models import AgentRun
from backend.db.models import Resume
from backend.db.career_models import ResumeVersion
from backend.schemas.agent_runs import RunStatus
from backend.services import agent_runs
from backend.tests.agent_fixtures import DraftModel
from backend.tests.career_fixtures import career_engine, career_db
from backend.tests.test_worker_delivery import new_run


def test_custom_model_requires_explicit_capacity(monkeypatch):
    from backend.agent_runtime import factory
    settings = SimpleNamespace(api_key='test-key', base_url='https://example.invalid/v1',
        model='gpt-4o', max_tokens=1024, request_timeout_seconds=30, context_window_tokens=None)
    monkeypatch.setattr(factory, 'resolve_effective_llm_settings', lambda _: settings)
    with pytest.raises(agent_runs.RunError) as error:
        factory.model_for_user(1)
    assert error.value.code == 'model_context_not_configured'
    settings.context_window_tokens = 1024
    with pytest.raises(agent_runs.RunError) as error:
        factory.model_for_user(1)
    assert error.value.code == 'context_budget_exceeded'
    settings.context_window_tokens = 20000
    model = factory.model_for_user(1)
    assert model.profile['max_input_tokens'] == 20000
    assert model.max_tokens == 1024


@pytest.fixture
def context_runtime(career_db, career_engine, monkeypatch, tmp_path):
    from backend.agent_runtime import runner, factory, tools
    sessions = sessionmaker(career_engine, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr(runner, 'SessionLocal', sessions)
    monkeypatch.setattr(tools, 'SessionLocal', sessions)
    monkeypatch.setenv('AGENT_STATE_DIR', str(tmp_path))
    model = DraftModel(profile={'max_input_tokens': 3000})
    monkeypatch.setattr(factory, 'model_for_user', lambda _: model)
    return runner, model


def test_irreducible_system_and_tools_fail_before_model_call(context_runtime, career_db, monkeypatch):
    runner, model = context_runtime
    def unexpected(*args, **kwargs):
        pytest.fail('A known oversized system/tool request reached the provider')
    monkeypatch.setattr(type(model), '_generate', unexpected)
    run = new_run(career_db)
    runner.run_agent(run.id, agent_runs.claim_run(career_db, run.id))
    career_db.expire_all()
    assert career_db.get(AgentRun, run.id).error_code == 'context_budget_exceeded'
    assert career_db.get(AgentRun, run.id).status == RunStatus.FAILED
    assert career_db.query(ResumeVersion).count() == 0


def test_bundle_keeps_exact_facts_actions_and_artifact_references(career_db):
    from backend.agent_runtime import context
    from backend.db.agent_models import AgentAction
    from backend.db.career_models import ProfileFact
    from backend.db.models import utcnow
    career_db.add(ProfileFact(id='fact-1', user_id=1, fact_key='api', kind='experience',
        content={'text': '本人已确认：负责数据库设计。'}, source_document_id=1,
        revision=1, confirmed_at=utcnow()))
    career_db.commit()
    run = new_run(career_db)
    career_db.add_all([
        AgentAction(id='pending-1', run_id=run.id, interrupt_id='pause-1', kind='input',
            payload={'question': '请说明规模'}, status='pending'),
        AgentAction(id='answer-1', run_id=run.id, interrupt_id='answer-pause', kind='input',
            payload={'question': '你负责什么'}, status='answered',
            response={'decision': 'submit', 'answers': {'role': '接口设计'}}, answered_at=utcnow()),
        ResumeVersion(id='existing-draft', run_id=run.id, user_id=1, resume_id=1, jd_id=1,
            structured_content={'resume': {'self_summary': 'API development'}}, fact_refs=[]),
    ])
    career_db.commit()
    bundle = context.build_context(career_db, run)
    assert bundle.required['facts'][0] == {
        'id': 'fact-1', 'revision': 1, 'content': {'text': '本人已确认：负责数据库设计。'}}
    assert bundle.required['pendingActions'] == [
        {'actionId': 'pending-1', 'kind': 'input', 'payload': {'question': '请说明规模'}}]
    assert bundle.required['applicantAnswers'][0]['actionId'] == 'answer-1'
    assert bundle.required['outputs'][0]['id'] == 'existing-draft'
    assert bundle.artifacts[0]['id'] == f'run:{run.id}:context:resume'
    assert bundle.context['resume']['structured']['self_summary'] == 'API development'


import json
import re
from copy import deepcopy
from pydantic import Field
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class LongContextModel(DraftModel):
    profile: dict = {'max_input_tokens': 30000}
    step: int = 0
    requests: list = Field(default_factory=list)
    summaries: list = Field(default_factory=list)
    read_results: list = Field(default_factory=list)
    saved_resume: dict = Field(default_factory=dict)
    bound_tools: list = Field(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        super().bind_tools(tools, **kwargs)
        self.bound_tools = tools
        return self

    def _generate(self, messages, **kwargs):
        if messages[0].text.startswith('必保留业务上下文（摘要调用）'):
            self.summaries.append(deepcopy(messages))
            # Deliberately omit all business facts: SQL injection must preserve them.
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content='已阅读资料，需要继续准备并补问。'))])
        self.requests.append(deepcopy(messages))
        required = json.loads(messages[0].text.rsplit('必保留业务上下文\n', 1)[1])
        root = f"/inputs/{required['runId']}"
        for message in messages:
            if isinstance(message, ToolMessage) and message.name == 'read_file':
                self.read_results.append(message.content)
                if '"self_summary"' in message.content:
                    content = re.sub(r'^\s*\d+\s+', '', message.content, flags=re.M)
                    self.saved_resume = json.loads(content[content.index('{'):content.rindex('}') + 1])
        commands = [
            ('get_application_context', {}),
            ('read_file', {'file_path': root + '/resume.json', 'offset': 0, 'limit': 50}),
            ('read_file', {'file_path': root + '/resume-text.json', 'offset': 0, 'limit': 45}),
            ('read_file', {'file_path': root + '/job-text.json', 'offset': 0, 'limit': 45}),
            ('read_file', {'file_path': root + '/match.json', 'offset': 0, 'limit': 45}),
            ('write_file', {'file_path': root + '/resume.json', 'content': '伪造原文'}),
            ('ask_applicant', {'question': '实际负责哪些数据库设计？'}),
            ('get_application_context', {}),
            ('read_file', {'file_path': root + '/resume.json', 'offset': 0, 'limit': 50}),
        ]
        if self.step < len(commands):
            name, args = commands[self.step]
        elif self.step == len(commands):
            resume = self.saved_resume
            args = {'changes': [{'section': '/self_summary',
                'before': resume['structured']['self_summary'],
                'after': '负责接口开发与数据库设计。', 'reason': '来自原简历、本人确认事实及本次回答。',
                'fact_refs': [
                    {'kind': 'resume', 'resumeId': resume['id'], 'inputVersion': resume['inputVersion'],
                     'section': '/self_summary', 'sourceRefs': resume['structured']['source_refs']},
                    {'kind': 'profile_fact', 'factId': required['facts'][0]['id'], 'revision': 1},
                    {'kind': 'applicant_answer', 'actionId': required['applicantAnswers'][0]['actionId']}],
                'requires_input': False}]}
            name = 'create_resume_draft'
        else:
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content='请审阅草稿'))])
        self.step += 1
        return ChatResult(generations=[ChatGeneration(message=AIMessage(
            content='正在核对固定原文、确认事实、岗位要求和可引用的经历。' * 100,
            tool_calls=[{'name': name, 'args': args, 'id': f'long-{self.step}', 'type': 'tool_call'}]))])


def test_long_context_summarizes_and_recovers_real_checkpoint(context_runtime, career_db, monkeypatch, tmp_path):
    from backend.agent_runtime import factory
    from backend.agent_runtime.context import estimate_tokens, json_text, ESTIMATE_METHOD
    from backend.db.agent_models import AgentAction
    from backend.db.career_models import ProfileFact, BusinessMemory
    from backend.db.models import JobDescription, MatchResult, AnalysisJob, AnalysisCandidate, utcnow
    from backend.schemas.agent_runs import ActionResponse
    from langgraph.checkpoint.sqlite import SqliteSaver
    runner, _ = context_runtime
    model = LongContextModel()
    monkeypatch.setattr(factory, 'model_for_user', lambda _: model)
    resume = career_db.get(Resume, 1)
    resume.raw_text = '\n'.join(f'项目{i}：负责接口设计、数据校验、数据库建模与交付核对。' * 12 for i in range(100))
    resume.structured_data = {'self_summary': '负责接口开发。', 'source_refs': ['page:1']}
    job = career_db.get(JobDescription, 1)
    job.raw_text = '\n'.join(f'岗位要求{i}：能够设计接口、核查数据模型并沟通业务边界。' * 12 for i in range(100))
    career_db.add(ProfileFact(id='context-fact', user_id=1, fact_key='db-design', kind='experience',
        content={'text': '本人已确认：负责数据库设计；没有人数和性能指标。'},
        source_document_id=1, revision=1, confirmed_at=utcnow()))
    career_db.add(BusinessMemory(id='context-memory', user_id=1, kind='preference',
        content='偏好后端岗位，避免夸张措辞。', source_ref={'kind': 'manual'}, confirmed_at=utcnow()))
    analysis = AnalysisJob(user_id=1, jd_id=1, title='历史匹配', status='completed')
    career_db.add(analysis)
    career_db.flush()
    candidate = AnalysisCandidate(job_id=analysis.id, resume_id=1)
    career_db.add(candidate)
    career_db.flush()
    career_db.add(MatchResult(job_id=analysis.id, resume_id=1, jd_id=1, candidate_id=candidate.id,
        overall_score=82, recommendation='recommend', reason='已有接口经历',
        report_json={'notes': [f'历史建议{i}：突出实际接口与数据模型工作，不补写未经确认的指标。' * 8 for i in range(80)]}))
    career_db.commit()
    run = new_run(career_db)
    frozen = deepcopy(run.input_json['contextSnapshot'])
    config = {'configurable': {'thread_id': run.session_id}}
    runner.run_agent(run.id, agent_runs.claim_run(career_db, run.id))
    career_db.expire_all()
    assert career_db.get(AgentRun, run.id).status == RunStatus.WAITING_INPUT
    assert model.summaries, 'Long real tool/history input did not trigger SDK summarization'
    with SqliteSaver.from_conn_string(str(tmp_path / 'checkpoints.sqlite')) as saver:
        saved = factory.build_agent(1, saver, run_id=run.id, epoch=1).get_state(config).values
        assert saved['_summarization_event']['file_path'].startswith('/conversation_history/')
        assert json.loads(saved['files'][f'/inputs/{run.id}/resume.json']['content'])['structured']['self_summary'] == '负责接口开发。'
    # run_agent has closed its saver; it creates a new graph and saver on resume.
    action = career_db.query(AgentAction).filter_by(run_id=run.id).one()
    agent_runs.answer_action(career_db, 1, run.id, action.id, ActionResponse(
        decision='submit', answers={'role': '负责数据库表和接口的数据约束设计。'}, expected_revision=1))
    runner.run_agent(run.id, agent_runs.claim_run(career_db, run.id))
    career_db.expire_all()
    assert career_db.get(AgentRun, run.id).status == RunStatus.SUCCEEDED
    version = career_db.query(ResumeVersion).filter_by(run_id=run.id).one()
    assert version.structured_content['changes'][0]['before'] == '负责接口开发。'
    assert version.structured_content['changes'][0]['fact_refs'][-1]['actionId'] == action.id
    assert career_db.get(AgentRun, run.id).input_json['contextSnapshot'] == frozen
    assert any('denied' in str(message.content).lower() for request in model.requests
               for message in request if isinstance(message, ToolMessage) and message.name == 'write_file')
    for request in [*model.requests, *model.summaries]:
        assert '本人已确认：负责数据库设计；没有人数和性能指标。' in request[0].text
        assert '不得自动确认' in request[0].text
        assert '偏好后端岗位，避免夸张措辞。' in request[0].text
        assert run.id in request[0].text
    assert action.id in model.requests[-1][0].text
    assert version.id in model.requests[-1][0].text
    # Compare the same snapshot as an inline tool payload with its manifest view;
    # also retain actual request estimates after the SDK's compaction.
    metrics = {'method': ESTIMATE_METHOD,
        'inlineSnapshotEstimatedTokens': estimate_tokens([HumanMessage(content=json_text(frozen))]),
        'actualMainRequestEstimatedTokens': [estimate_tokens(request, tools=model.bound_tools) for request in model.requests],
        'actualSummaryRequestEstimatedTokens': [estimate_tokens(request) for request in model.summaries],
        'summaryCalls': len(model.summaries), 'draftId': version.id, 'sourceActionId': action.id}
    assert max(metrics['actualMainRequestEstimatedTokens']) <= 27476
    assert max(metrics['actualSummaryRequestEstimatedTokens']) <= 27476
    (tmp_path / 'context-estimates.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2))
    print('CONTEXT_ESTIMATES', json.dumps(metrics, ensure_ascii=False))


def test_single_long_field_is_losslessly_paged(career_db):
    from backend.agent_runtime.context import build_context
    paragraph = '负责接口、数据库和业务规则核验。' * 700
    career_db.get(Resume, 1).raw_text = paragraph
    career_db.get(Resume, 1).structured_data = {'self_summary': paragraph, 'source_refs': ['page:1']}
    career_db.commit()
    bundle = build_context(career_db, new_run(career_db))
    artifact = bundle.artifacts[0]
    encoded = json.loads(bundle.files[artifact['path']])['structured']['self_summary']
    assert ''.join(encoded['textChunks']) == paragraph
    assert max(len(line) for line in bundle.files[artifact['path']].splitlines()) < 2200
    original = json.loads(bundle.files[artifact['textPath']])
    assert ''.join(original['textChunks']) == paragraph
    assert bundle.context['resume']['structured']['self_summary'] == paragraph


def test_summary_retry_rechecks_revocation_before_another_model_request(context_runtime, career_db):
    from backend.agent_runtime.context_middleware import BusinessContextMiddleware
    from backend.db.agent_models import AgentSession
    from backend.db.models import utcnow
    from deepagents.backends import StateBackend
    runner, _ = context_runtime
    run = new_run(career_db)
    epoch = agent_runs.claim_run(career_db, run.id)

    class RevokingSummary(DraftModel):
        attempts: int = 0
        def _generate(self, messages, **kwargs):
            self.attempts += 1
            career_db.get(AgentSession, run.session_id).context_invalidated_at = utcnow()
            career_db.commit()
            raise RuntimeError('Synthetic provider error after business revocation')

    model = RevokingSummary()
    middleware = BusinessContextMiddleware(model=model, backend=StateBackend(), run_id=run.id, epoch=epoch)
    with pytest.raises(agent_runs.RunError) as error:
        middleware._create_summary([HumanMessage(content='之前已阅读业务资料。')])
    assert error.value.code == 'session_context_invalidated'
    assert model.attempts == 1
    assert career_db.query(ResumeVersion).count() == 0


def test_confirmed_facts_are_not_silently_trimmed_to_fit(context_runtime, career_db, monkeypatch):
    from backend.agent_runtime import factory
    from backend.db.career_models import ProfileFact
    from backend.db.models import utcnow
    runner, _ = context_runtime
    model = DraftModel(profile={'max_input_tokens': 30000})
    monkeypatch.setattr(factory, 'model_for_user', lambda _: model)
    career_db.add(ProfileFact(id='large-fact', user_id=1, fact_key='large-confirmed',
        kind='experience', content={'text': '本人已确认的项目职责，必须完整保留。' * 2000},
        source_document_id=1, revision=1, confirmed_at=utcnow()))
    career_db.commit()
    def unexpected(*args, **kwargs):
        pytest.fail('Required facts must fail before either main or summary model call')
    monkeypatch.setattr(type(model), '_generate', unexpected)
    run = new_run(career_db)
    runner.run_agent(run.id, agent_runs.claim_run(career_db, run.id))
    career_db.expire_all()
    assert career_db.get(AgentRun, run.id).error_code == 'context_budget_exceeded'
    assert career_db.query(ResumeVersion).count() == 0
