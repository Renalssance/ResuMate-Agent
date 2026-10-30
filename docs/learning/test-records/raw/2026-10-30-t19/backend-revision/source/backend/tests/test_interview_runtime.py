"""Real DeepAgents checkpoints and SQL results; only model responses are synthetic."""
from copy import deepcopy
import importlib
import importlib.util

import pytest

from backend.services.agent_runs import RunError


def context_module():
    assert importlib.util.find_spec('backend.agent_runtime.interview_context'), 'Interview frozen context/output validation is required'
    return importlib.import_module('backend.agent_runtime.interview_context')


def fixed_context(turn=0):
    return {'interviewId': 'interview-1', 'expectedTurn': turn,
        'source': {'applicationId': 1, 'resumeVersionId': 'version-frozen', 'revision': 3,
                   'submittedAt': '2026-10-29T12:00:00Z',
                   'structuredContent': {'resume': {'self_summary': 'API development', 'skills': ['SQL']}},
                   'factRefs': [], 'job': {'jdId': 1, 'title': 'Engineer', 'company': 'Synthetic',
                   'rawText': 'Design reliable APIs', 'structuredData': {}, 'capturedAt': '2026-10-30T01:00:00Z'}},
        'turns': [] if not turn else [{'id': 11, 'turnIndex': turn, 'question': '如何保证一致性？',
                    'questionContext': {}, 'answer': '使用单个数据库事务', 'feedback': None}], 'memories': []}


def step_payload(turn=0, *, mode='follow_up'):
    ref = {'kind': 'resume', 'section': '/self_summary', 'quote': 'API development'} if not turn else {
        'kind': 'answer', 'turnIndex': turn, 'quote': '使用单个数据库事务'}
    return {'feedback': None if not turn else {
        'summary': '回答说明了事务边界。', 'strengths': [{'text': '说明了原子事务。', 'refs': [ref]}],
        'improvements': [{'text': '可以补充回滚触发条件。', 'refs': [ref]}],
        'practiceFocus': '练习描述失败后如何回滚，不补造项目规模。'},
        'question': None if turn == 8 else {'text': '请说明你的 API 经验。' if not turn else '失败后如何回滚？',
            'mode': 'opening' if not turn else mode, 'refs': [ref]}}


def test_quotes_bind_only_server_frozen_version_job_and_answer_ids():
    module = context_module()
    opening = module.validate_step(step_payload(), fixed_context())
    assert opening['question']['refs'] == [{'kind': 'resume', 'section': '/self_summary', 'quote': 'API development',
                                          'resumeVersionId': 'version-frozen', 'revision': 3}]
    payload = step_payload(1)
    payload['question']['refs'].append({'kind': 'job', 'quote': 'reliable APIs'})
    bound = module.validate_step(payload, fixed_context(1))
    assert bound['question']['refs'] == [
        {'kind': 'answer', 'turnIndex': 1, 'turnId': 11, 'quote': '使用单个数据库事务'},
        {'kind': 'job', 'quote': 'reliable APIs', 'jdId': 1, 'capturedAt': '2026-10-30T01:00:00Z'}]


@pytest.mark.parametrize('reference', [
    {'kind': 'resume', 'section': '/missing', 'quote': 'API development'},
    {'kind': 'resume', 'section': '/self_summary', 'quote': 'invented experience'},
    {'kind': 'job', 'quote': 'unmentioned skill'},
    {'kind': 'answer', 'turnIndex': 2, 'quote': '使用单个数据库事务'},
    {'kind': 'answer', 'turnIndex': 1, 'quote': 'never answered'},
    {'kind': 'resume', 'section': '/self_summary', 'quote': 'API development', 'resumeVersionId': 'injected'},
])
def test_invalid_or_model_owned_reference_does_not_become_a_result(reference):
    module = context_module()
    payload = step_payload(1)
    payload['question']['refs'] = [reference]
    with pytest.raises(RunError):
        module.validate_step(payload, fixed_context(1))


def test_follow_up_requires_the_previous_accepted_answer_and_eighth_has_no_question():
    module = context_module()
    payload = step_payload(1)
    payload['question']['refs'] = [{'kind': 'job', 'quote': 'reliable APIs'}]
    with pytest.raises(RunError):
        module.validate_step(payload, fixed_context(1))
    final = module.validate_step(step_payload(8), fixed_context(8))
    assert final['question'] is None and final['feedback']['summary'] == '回答说明了事务边界。'
    ninth = step_payload(8)
    ninth['question'] = {'text': '非法第九题', 'mode': 'new_topic', 'refs': [{'kind': 'job', 'quote': 'reliable APIs'}]}
    with pytest.raises(RunError):
        module.validate_step(ninth, fixed_context(8))


@pytest.mark.parametrize('change', ['empty_refs', 'no_feedback', 'opening_after_answer', 'feedback_before_answer'])
def test_wrong_step_shape_cannot_silently_drop_unsupported_feedback(change):
    module = context_module()
    turn = 0 if change == 'feedback_before_answer' else 1
    payload = step_payload(turn)
    if change == 'empty_refs': payload['question']['refs'] = []
    if change == 'no_feedback': payload['feedback'] = None
    if change == 'opening_after_answer': payload['question']['mode'] = 'opening'
    if change == 'feedback_before_answer': payload['feedback'] = step_payload(1)['feedback']
    with pytest.raises(RunError):
        module.validate_step(payload, fixed_context(turn))

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from backend.db.agent_models import AgentRun, ToolOperation
from backend.db.career_models import InterviewTurn, InterviewEvent, InterviewSession
from backend.schemas.agent_runs import RunStatus
from backend.schemas.interviews import InterviewCreate, INTERVIEW_COMMAND_ADAPTER
from backend.services import agent_runs, interviews, interview_commands
from backend.tests.career_fixtures import career_engine, career_db
from backend.tests.interview_fixtures import seed_application, answer_command
from backend.tests.interview_model_fixture import ScriptedInterviewModel


@pytest.fixture
def runtime(career_db, career_engine, monkeypatch, tmp_path):
    assert importlib.util.find_spec('backend.agent_runtime.interviews'), 'Real interview handler is required'
    module = importlib.import_module('backend.agent_runtime.interviews')
    from backend.agent_runtime import factory, interview_context
    from backend import worker_tasks
    model = ScriptedInterviewModel()
    factory_db = sessionmaker(bind=career_engine, expire_on_commit=False)
    monkeypatch.setattr(module, 'SessionLocal', factory_db)
    monkeypatch.setattr(interview_context, 'SessionLocal', factory_db)
    monkeypatch.setattr(worker_tasks, 'SessionLocal', factory_db)
    monkeypatch.setattr(factory, 'model_for_user', lambda _uid: model)
    monkeypatch.setattr(module, 'publish_interview_hint_sync', lambda *args: None)
    monkeypatch.setenv('AGENT_STATE_DIR', str(tmp_path / 'agent'))
    seed_application(career_db)
    accepted = interviews.create_interview(career_db, 1, InterviewCreate(requestId='runtime-start', applicationId=1))
    return module, model, accepted, factory_db


def execute(db, module, run_id):
    epoch = agent_runs.claim_run(db, run_id)
    assert epoch is not None
    module.run_interview_generation(run_id, epoch)
    db.expire_all()
    return db.get(AgentRun, run_id)


def test_real_graph_eight_rounds_two_followups_new_topic_and_immutable_results(runtime, career_db):
    module, model, accepted, _ = runtime
    run = execute(career_db, module, accepted['runId'])
    assert run.status == RunStatus.SUCCEEDED, run.error_code
    opening = deepcopy(run.result_json)
    for turn in range(1, 9):
        ack = interview_commands.handle_command(career_db, 1, accepted['interviewId'],
            answer_command(f'answer-{turn}', turn=turn, text=f'I used SQL transaction {turn}'))
        run = execute(career_db, module, ack['resultRef'])
        assert run.status == RunStatus.SUCCEEDED, run.error_code
        assert run.result_json['feedback']['strengths'][0]['refs'][0]['turnIndex'] == turn
    rows = list(career_db.scalars(select(InterviewTurn).order_by(InterviewTurn.turn_index)))
    assert len(rows) == 8 and all(row.feedback for row in rows)
    assert [row.question_context['mode'] for row in rows[:4]] == ['opening', 'follow_up', 'follow_up', 'new_topic']
    assert career_db.get(InterviewSession, accepted['interviewId']).status == 'finished'
    assert career_db.get(AgentRun, accepted['runId']).result_json == opening
    assert career_db.query(ToolOperation).filter_by(operation_key='interview:step').count() == 9
    events = list(career_db.scalars(select(InterviewEvent).order_by(InterviewEvent.seq)))
    assert [event.seq for event in events] == list(range(1, len(events) + 1))
    assert [event.type for event in events].count('question.completed') == 8
    assert [event.type for event in events].count('feedback.ready') == 8
    assert events[-1].type == 'session.finished'
    assert 'InterviewStep' in model.bound_tools and 'get_interview_context' in model.bound_tools


def test_worker_dispatches_interview_and_duplicate_delivery_is_noop(runtime, career_db):
    from backend.worker_tasks import execute_run
    _module, model, accepted, _ = runtime
    career_db.commit()
    execute_run(accepted['runId'])
    career_db.expire_all()
    assert career_db.get(AgentRun, accepted['runId']).status == RunStatus.SUCCEEDED
    calls = len(model.calls)
    execute_run(accepted['runId'])
    assert len(model.calls) == calls
    assert career_db.query(InterviewTurn).count() == career_db.query(ToolOperation).count() == 1


def test_frozen_job_title_is_a_valid_material_quote():
    payload = step_payload()
    payload['question']['refs'] = [{'kind': 'job', 'quote': 'Engineer'}]
    assert context_module().validate_step(payload, fixed_context())['question']['refs'][0]['jdId'] == 1


def test_telemetry_uses_actual_interview_kind(runtime, career_db, monkeypatch):
    from backend.agent_runtime import telemetry
    from backend.tests.test_agent_telemetry import FakeClient
    client = FakeClient()
    monkeypatch.setattr(telemetry, '_configured_client', lambda: client)
    module, _model, accepted, _ = runtime
    assert execute(career_db, module, accepted['runId']).status == RunStatus.SUCCEEDED
    assert client.observations[0].name == 'interview_generation'


@pytest.mark.parametrize('command_type', ['generation.cancel', 'session.finish'])
def test_real_running_model_late_output_is_fenced(runtime, career_db, command_type):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    module, model, accepted, sessions = runtime
    entered, release = Event(), Event()
    def pause(step, context):
        entered.set()
        assert release.wait(10), 'command must commit while the model is in flight'
        return step
    model.transform_step = pause
    epoch = agent_runs.claim_run(career_db, accepted['runId'])
    with ThreadPoolExecutor() as pool:
        work = pool.submit(module.run_interview_generation, accepted['runId'], epoch)
        try:
            assert entered.wait(10)
            with sessions() as db:
                request = INTERVIEW_COMMAND_ADAPTER.validate_python({'clientMessageId': 'stop',
                    'type': command_type, 'expectedTurn': 0,
                    'payload': {'runId': accepted['runId']} if command_type == 'generation.cancel' else {}})
                interview_commands.handle_command(db, 1, accepted['interviewId'], request)
                assert db.get(AgentRun, accepted['runId']).status == RunStatus.RUNNING
        finally:
            release.set()
        work.result(timeout=15)
    career_db.expire_all()
    run = career_db.get(AgentRun, accepted['runId'])
    assert run.status == RunStatus.CANCELLED and run.result_json is None
    assert career_db.query(InterviewTurn).count() == career_db.query(ToolOperation).count() == 0
    assert career_db.query(InterviewEvent).filter_by(type='generation.cancelled').count() == 1


def test_invalid_quote_fails_whole_step_keeps_answer_and_retry_uses_new_run(runtime, career_db):
    module, model, accepted, _ = runtime
    assert execute(career_db, module, accepted['runId']).status == RunStatus.SUCCEEDED
    ack = interview_commands.handle_command(career_db, 1, accepted['interviewId'], answer_command(text='One SQL transaction'))
    def invalid(step, context):
        step['question']['refs'][0]['quote'] = 'UNSUPPORTED_QUOTE'
        return step
    model.transform_step = invalid
    failed = execute(career_db, module, ack['resultRef'])
    assert failed.status == RunStatus.FAILED and failed.error_code == 'invalid_interview_reference'
    row = career_db.scalar(select(InterviewTurn))
    assert row.answer == 'One SQL transaction' and row.feedback is None
    assert career_db.query(ToolOperation).count() == 1 and failed.result_json is None
    retry = INTERVIEW_COMMAND_ADAPTER.validate_python({'clientMessageId': 'retry', 'type': 'generation.retry',
        'expectedTurn': 1, 'payload': {'runId': failed.id}})
    retry_ack = interview_commands.handle_command(career_db, 1, accepted['interviewId'], retry)
    model.transform_step = None
    assert execute(career_db, module, retry_ack['resultRef']).status == RunStatus.SUCCEEDED
    assert career_db.get(AgentRun, failed.id).status == RunStatus.FAILED
    assert career_db.query(InterviewTurn).count() == 2


def test_partial_business_write_rolls_back_feedback_question_operation_and_events(runtime, career_db, monkeypatch):
    module, _model, accepted, _ = runtime
    assert execute(career_db, module, accepted['runId']).status == RunStatus.SUCCEEDED
    ack = interview_commands.handle_command(career_db, 1, accepted['interviewId'], answer_command())
    prior_events = career_db.query(InterviewEvent).count()
    original = module.append_interview_event
    def broken(db, iid, kind, payload):
        value = original(db, iid, kind, payload)
        if kind == 'question.completed':
            raise RuntimeError('synthetic failure after flushed question and feedback')
        return value
    monkeypatch.setattr(module, 'append_interview_event', broken)
    result = execute(career_db, module, ack['resultRef'])
    assert result.status == RunStatus.FAILED and result.result_json is None
    assert career_db.query(InterviewTurn).count() == career_db.query(ToolOperation).count() == 1
    assert career_db.scalar(select(InterviewTurn)).feedback is None
    assert career_db.query(InterviewEvent).count() == prior_events


def test_completed_checkpoint_recovers_without_another_model_call_and_fences_old_epoch(runtime, career_db, monkeypatch):
    from datetime import timedelta
    from backend.db.models import utcnow
    from backend.worker_tasks import execution_lock
    module, model, accepted, _ = runtime
    original = module._persist_step
    def process_exit(*args):
        raise SystemExit('synthetic crash after durable graph completion, before SQL step')
    monkeypatch.setattr(module, '_persist_step', process_exit)
    epoch = agent_runs.claim_run(career_db, accepted['runId'])
    with pytest.raises(SystemExit):
        module.run_interview_generation(accepted['runId'], epoch)
    calls = len(model.calls)
    career_db.expire_all()
    run = career_db.get(AgentRun, accepted['runId'])
    run.heartbeat_at = utcnow() - timedelta(minutes=5)
    career_db.commit()
    with execution_lock() as held:
        assert held and agent_runs.recover_stale_runs(career_db) == 1
    epoch2 = agent_runs.claim_run(career_db, run.id)
    assert epoch2 > epoch
    monkeypatch.setattr(module, '_persist_step', original)
    module.run_interview_generation(run.id, epoch)
    career_db.expire_all()
    assert career_db.get(AgentRun, run.id).status == RunStatus.RUNNING
    assert career_db.query(InterviewTurn).count() == 0
    module.run_interview_generation(run.id, epoch2)
    career_db.rollback()
    assert career_db.get(AgentRun, run.id).status == RunStatus.SUCCEEDED
    assert len(model.calls) == calls
    assert career_db.query(InterviewTurn).count() == career_db.query(ToolOperation).count() == 1


def test_large_frozen_context_uses_real_file_pages_without_latest_document_changes(runtime, career_db):
    from backend.db.models import Resume, JobDescription
    module, model, accepted, _ = runtime
    # Seed a supported long submitted paragraph before the first generation reads it.
    session = career_db.get(InterviewSession, accepted['interviewId'])
    source = deepcopy(session.source_snapshot)
    paragraph = '曾负责接口设计和数据库事务。' * 700
    source['structuredContent']['resume']['self_summary'] = paragraph
    session.source_snapshot = source
    career_db.get(Resume, 1).structured_data = {'self_summary': 'LATEST_RESUME_MUST_NOT_APPEAR'}
    career_db.get(JobDescription, 1).raw_text = 'LATEST_JOB_MUST_NOT_APPEAR'
    career_db.commit()
    run = execute(career_db, module, accepted['runId'])
    assert run.status == RunStatus.SUCCEEDED, run.error_code
    observed = [call['context'] for call in model.calls if 'context' in call][-1]
    assert observed['source']['structuredContent']['resume']['self_summary'] == paragraph
    assert observed['source']['job']['rawText'] == 'Build APIs'
    assert any(message.get('name') == 'read_file' for call in model.calls for message in call['messages'])
    assert 'LATEST_' not in str(model.calls)


def memory_run(db):
    from backend.schemas.memory import MemoryCreate
    from backend.services.memory import create_memory
    memory = create_memory(db, 1, MemoryCreate(kind='preference', content='请用简洁中文', confirmed=True))
    accepted = interviews.create_interview(db, 1, InterviewCreate(requestId='with-memory', applicationId=1))
    epoch = agent_runs.claim_run(db, accepted['runId'])
    return memory, accepted, epoch


def test_deleted_memory_fences_next_real_main_model_call(runtime, career_db):
    from backend.services.memory import delete_memory
    module, model, _accepted, sessions = runtime
    memory, accepted, epoch = memory_run(career_db)
    def delete(required):
        assert required['memories'][0]['content'] == '请用简洁中文'
        with sessions() as db:
            delete_memory(db, 1, memory['id'])
    model.before_generate = delete
    module.run_interview_generation(accepted['runId'], epoch)
    career_db.expire_all()
    assert len(model.calls) == 1
    assert career_db.get(AgentRun, accepted['runId']).status == RunStatus.CANCELLED
    assert career_db.query(InterviewTurn).count() == 0


def test_sdk_summary_retry_checks_deleted_memory_before_second_provider_call(runtime, career_db):
    from backend.agent_runtime.interview_context import InterviewContextMiddleware
    from backend.services.memory import delete_memory
    from deepagents.backends import StateBackend
    from langchain_core.messages import HumanMessage
    module, model, _accepted, sessions = runtime
    memory, accepted, epoch = memory_run(career_db)
    def delete_and_fail(required):
        assert required['memories'][0]['content'] == '请用简洁中文'
        with sessions() as db:
            delete_memory(db, 1, memory['id'])
        raise RuntimeError('synthetic provider error after memory deletion')
    model.before_generate = delete_and_fail
    middleware = InterviewContextMiddleware(model=model, backend=StateBackend(), run_id=accepted['runId'], epoch=epoch)
    with pytest.raises(RunError) as failure:
        middleware._create_summary([HumanMessage(content='已读冻结材料和练习偏好。')])
    assert failure.value.code == 'session_context_invalidated'
    assert len(model.summaries) == 1 and model.calls == []
    assert model.summaries[0]['required']['sourceIdentity']['revision'] == 3
    assert career_db.query(InterviewTurn).count() == 0


def test_actual_graph_summary_preserves_required_context_and_fences_post_summary_call(runtime, career_db):
    from backend.agent_runtime.factory import build_interview_agent
    from backend.services.memory import delete_memory
    from backend.worker_tasks import state_directory
    from langchain_core.messages import HumanMessage, AIMessage
    from langgraph.checkpoint.sqlite import SqliteSaver
    module, model, _accepted, sessions = runtime
    memory, accepted, epoch = memory_run(career_db)
    model.profile = {'max_input_tokens': 30000}
    career_db.expire_all()
    session_id = career_db.get(AgentRun, accepted['runId']).session_id
    career_db.commit()
    config = {'configurable': {'thread_id': session_id}}
    with SqliteSaver.from_conn_string(str(state_directory() / 'checkpoints.sqlite')) as saver:
        graph = build_interview_agent(1, saver, run_id=accepted['runId'], epoch=epoch)
        history = [HumanMessage(content='请依据冻结材料继续。')]
        for _ in range(6):
            history.extend([AIMessage(content='先前读取的练习材料。' * 300), HumanMessage(content='继续核对来源。')])
        graph.update_state(config, {'run_id': accepted['runId'], 'messages': history}, as_node='tools')
    def after_summary(required):
        assert model.summaries, 'long graph history must trigger the actual SDK summary request'
        with sessions() as db:
            delete_memory(db, 1, memory['id'])
    model.before_generate = after_summary
    module.run_interview_generation(accepted['runId'], epoch)
    career_db.expire_all()
    assert len(model.summaries) == 1 and model.calls == []
    assert model.summaries[0]['required']['expectedTurn'] == 0
    assert model.summaries[0]['required']['sourceIdentity']['resumeVersionId']
    assert career_db.get(AgentRun, accepted['runId']).status == RunStatus.CANCELLED
    assert career_db.query(InterviewTurn).count() == 0
