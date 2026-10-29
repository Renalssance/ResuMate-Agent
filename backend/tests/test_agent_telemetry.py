"""Metadata-only Langfuse adapter; no provider or cloud requests."""
import builtins
import json
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from backend.db.agent_models import AgentRun, AgentAction
from backend.db.career_models import ResumeVersion
from backend.db.models import Resume
from backend.schemas.agent_runs import ActionResponse, RunStatus
from backend.services import agent_runs
from backend.tests.career_fixtures import career_engine, career_db
from backend.tests.test_agent_runtime import runtime
from backend.tests.test_agent_context import context_runtime
from backend.tests.test_worker_delivery import new_run


PRIVATE = 'PRIVATE-RESUME-ANSWER-Authorization-secret-123'


class FakeObservation:
    def __init__(self, client, parent, *, name, as_type, metadata, model=None, trace_context=None):
        self.client, self.parent = client, parent
        self.name, self.kind = name, as_type
        self.metadata, self.model = dict(metadata), model
        self.trace_context = trace_context
        self.usage = None
        self.ended = False
        client.observations.append(self)
        client.events.append(('start', self))

    def start_observation(self, *, name, as_type, metadata, model=None):
        self.client.fail('child_start')
        return FakeObservation(self.client, self, name=name, as_type=as_type, metadata=metadata, model=model)

    def update(self, *, metadata, usage_details=None, level=None, status_message=None):
        self.client.fail('update')
        self.metadata.update(metadata)
        self.usage = usage_details
        self.client.events.append(('update', self))

    def end(self):
        self.client.fail('end')
        self.ended = True
        self.client.events.append(('end', self))


class FakeClient:
    def __init__(self):
        self.observations, self.events, self.options = [], [], []
        self.failure = None

    def fail(self, stage):
        if self.failure == stage:
            raise RuntimeError(PRIVATE)

    def start_observation(self, *, name, as_type, metadata, trace_context):
        self.fail('root_start')
        return FakeObservation(self, None, name=name, as_type=as_type, metadata=metadata, trace_context=trace_context)

    def flush(self):
        pytest.fail('A business request must not synchronously flush telemetry')

    def auth_check(self):
        pytest.fail('A business request must not authenticate telemetry synchronously')


@pytest.fixture
def fake_langfuse(monkeypatch):
    client = FakeClient()
    def construct(**kwargs):
        client.fail('init')
        client.options.append(kwargs)
        return client
    predicate = lambda span: getattr(span.instrumentation_scope, 'name', None) == 'langfuse-sdk'
    monkeypatch.setitem(sys.modules, 'langfuse', SimpleNamespace(Langfuse=construct))
    monkeypatch.setitem(sys.modules, 'langfuse.span_filter', SimpleNamespace(is_langfuse_span=predicate))
    monkeypatch.setenv('LANGFUSE_PUBLIC_KEY', 'public-test')
    monkeypatch.setenv('LANGFUSE_SECRET_KEY', PRIVATE)
    monkeypatch.setenv('LANGFUSE_BASE_URL', 'https://telemetry.invalid')
    monkeypatch.delenv('LANGFUSE_TRACING_ENABLED', raising=False)
    return client


@pytest.mark.parametrize('configuration', ['missing', 'partial', 'disabled'])
def test_unconfigured_or_disabled_does_not_import_sdk(runtime, career_db, monkeypatch, configuration):
    real_import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        assert not name.startswith('langfuse'), 'Optional telemetry imported while disabled'
        return real_import(name, *args, **kwargs)
    for name in ('LANGFUSE_PUBLIC_KEY', 'LANGFUSE_SECRET_KEY', 'LANGFUSE_BASE_URL'):
        monkeypatch.delenv(name, raising=False)
    if configuration != 'missing':
        monkeypatch.setenv('LANGFUSE_PUBLIC_KEY', 'public-test')
    if configuration == 'disabled':
        monkeypatch.setenv('LANGFUSE_SECRET_KEY', PRIVATE)
        monkeypatch.setenv('LANGFUSE_BASE_URL', 'https://telemetry.invalid')
        monkeypatch.setenv('LANGFUSE_TRACING_ENABLED', 'false')
    monkeypatch.setattr(builtins, '__import__', guarded_import)
    runner, _ = runtime
    run = new_run(career_db)
    runner.run_agent(run.id, agent_runs.claim_run(career_db, run.id))
    career_db.expire_all()
    assert career_db.get(AgentRun, run.id).status == RunStatus.SUCCEEDED


def test_correlates_real_run_models_tools_versions_without_text(runtime, career_db, fake_langfuse, monkeypatch):
    from backend.agent_runtime import tools
    runner, model = runtime
    career_db.get(Resume, 1).structured_data = {'self_summary': PRIVATE}
    career_db.commit()
    run = new_run(career_db)
    run.request_id = str(uuid4())
    career_db.commit()
    callback_calls = []
    class ExistingCallback(BaseCallbackHandler):
        def on_chat_model_start(self, *args, **kwargs):
            callback_calls.append(str(kwargs['run_id']))
    model.callbacks = [ExistingCallback()]
    original = tools.save_draft
    def save(*args, **kwargs):
        live = [span for span in fake_langfuse.observations if span.name == 'create_resume_draft' and not span.ended]
        assert len(live) == 1, 'Tool span must already exist during the actual database operation'
        return original(*args, **kwargs)
    monkeypatch.setattr(tools, 'save_draft', save)
    runner.run_agent(run.id, agent_runs.claim_run(career_db, run.id))
    career_db.expire_all()
    saved = career_db.get(AgentRun, run.id)
    assert saved.status == RunStatus.SUCCEEDED
    roots = [s for s in fake_langfuse.observations if s.parent is None]
    assert len(roots) == 1, 'Configured runtime did not create a real root observation'
    root = roots[0]
    assert root.trace_context == {'trace_id': run.id.replace('-', '')}
    assert root.metadata['run_id'] == run.id
    assert root.metadata['session_id'] == run.session_id
    assert root.metadata['request_id'] == run.request_id
    assert root.metadata['attempt'] == 1 and root.metadata['execution_epoch'] == 1
    assert root.metadata['input_versions']['resume'] == saved.input_versions['resume']
    assert root.metadata['output_refs'] == saved.output_refs
    generations = [s for s in fake_langfuse.observations if s.kind == 'generation']
    assert len(generations) == len(callback_calls) > 0
    assert {s.metadata['sdk_call_id'] for s in generations} == set(callback_calls)
    assert all(s.model == model.model_name for s in generations)
    assert all(s.metadata['run_id'] == run.id and s.parent is root for s in generations)
    assert all(s.ended and s.metadata['elapsed_ms'] >= 0 for s in fake_langfuse.observations)
    draft = next(s for s in fake_langfuse.observations if s.name == 'create_resume_draft')
    assert draft.metadata['result_ref'] == saved.output_refs[0]['id']
    exported = json.dumps([{'metadata': s.metadata, 'model': s.model} for s in fake_langfuse.observations])
    assert PRIVATE not in exported and 'api_key' not in exported and 'base_url' not in exported
    assert fake_langfuse.options[0]['should_export_span'] is sys.modules['langfuse.span_filter'].is_langfuse_span


@pytest.mark.parametrize('failure', ['init', 'root_start', 'child_start', 'update', 'end'])
def test_observation_failures_leave_business_success_unchanged(runtime, career_db, fake_langfuse, failure, caplog):
    fake_langfuse.failure = failure
    runner, _ = runtime
    run = new_run(career_db)
    runner.run_agent(run.id, agent_runs.claim_run(career_db, run.id))
    career_db.expire_all()
    assert career_db.get(AgentRun, run.id).status == RunStatus.SUCCEEDED
    assert career_db.query(ResumeVersion).count() == 1
    warnings = [r for r in caplog.records if r.name == 'backend.agent_runtime.telemetry']
    assert len(warnings) == 1
    assert PRIVATE not in caplog.text


def test_pause_is_closed_then_resume_uses_same_trace_without_private_answer(runtime, career_db, fake_langfuse):
    runner, model = runtime
    model.ask = True
    run = new_run(career_db)
    run.request_id = PRIVATE
    career_db.commit()
    runner.run_agent(run.id, agent_runs.claim_run(career_db, run.id))
    career_db.expire_all()
    assert career_db.get(AgentRun, run.id).status == RunStatus.WAITING_INPUT
    paused = [s for s in fake_langfuse.observations if s.name == 'ask_applicant']
    assert len(paused) == 1 and paused[0].ended
    assert paused[0].metadata['status'] == 'paused'
    action = career_db.query(AgentAction).one()
    agent_runs.answer_action(career_db, 1, run.id, action.id,
        ActionResponse(decision='submit', answers={'role': PRIVATE}, expected_revision=1))
    runner.run_agent(run.id, agent_runs.claim_run(career_db, run.id))
    career_db.expire_all()
    assert career_db.get(AgentRun, run.id).status == RunStatus.SUCCEEDED
    roots = [s for s in fake_langfuse.observations if s.parent is None]
    assert len(roots) == 2
    assert roots[0].trace_context == roots[1].trace_context
    assert {s.metadata['execution_epoch'] for s in roots} == {1, 2}
    assert all('request_id' not in s.metadata for s in fake_langfuse.observations)
    assert PRIVATE not in json.dumps([s.metadata for s in fake_langfuse.observations])


def test_real_summary_and_filesystem_callbacks_include_usage_only(context_runtime, career_db, monkeypatch, tmp_path, fake_langfuse):
    from backend.tests.test_agent_context import LongContextModel, test_long_context_summarizes_and_recovers_real_checkpoint
    original = LongContextModel._generate
    def generate(self, messages, **kwargs):
        result = original(self, messages, **kwargs)
        result.generations[0].message.usage_metadata = {'input_tokens': 11, 'output_tokens': 7, 'total_tokens': 18}
        return result
    monkeypatch.setattr(LongContextModel, '_generate', generate)
    test_long_context_summarizes_and_recovers_real_checkpoint(context_runtime, career_db, monkeypatch, tmp_path)
    summaries = [s for s in fake_langfuse.observations if s.name == 'model.summary']
    assert summaries, 'Actual SDK summary calls are missing from telemetry'
    assert all(s.usage == {'input': 11, 'output': 7, 'total': 18} for s in summaries)
    assert any(s.name == 'read_file' and s.kind == 'tool' for s in fake_langfuse.observations)
    assert all('本人已确认' not in json.dumps(s.metadata, ensure_ascii=False) for s in fake_langfuse.observations)


def test_actual_sdk_summary_retry_has_distinct_call_ids(runtime, career_db, fake_langfuse):
    from deepagents.backends import StateBackend
    from langchain_core.messages import HumanMessage
    from backend.agent_runtime.context_middleware import BusinessContextMiddleware
    from backend.agent_runtime.telemetry import RunTelemetry, attach_model_telemetry
    from backend.tests.agent_fixtures import DraftModel
    class SummaryModel(DraftModel):
        calls: int = 0
        def _generate(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError(PRIVATE)
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=PRIVATE,
                usage_metadata={'input_tokens': 20, 'output_tokens': 5, 'total_tokens': 25}))])
    run = new_run(career_db)
    epoch = agent_runs.claim_run(career_db, run.id)
    career_db.refresh(run)
    trace = RunTelemetry(run)
    model = SummaryModel()
    attach_model_telemetry(model, trace)
    middleware = BusinessContextMiddleware(model=model, backend=StateBackend(), run_id=run.id, epoch=epoch)
    assert middleware._lc_helper._create_summary([HumanMessage(content=PRIVATE)]) == PRIVATE
    spans = [s for s in fake_langfuse.observations if s.kind == 'generation']
    assert model.calls == len(spans) == 2
    assert [s.metadata['status'] for s in spans] == ['failed', 'succeeded']
    # The SDK does not preserve retry tags through sequence steps. Distinct
    # real attempts are evidenced by IDs, ordering, errors and source instead.
    assert [s.metadata['model_call_index'] for s in spans] == [1, 2]
    assert all('retry_attempt' not in s.metadata for s in spans)
    assert len({s.metadata['sdk_call_id'] for s in spans}) == 2
    assert all(s.name == 'model.summary' and s.ended for s in spans)
    assert spans[0].usage is None and spans[1].usage == {'input': 20, 'output': 5, 'total': 25}
    assert PRIVATE not in json.dumps([s.metadata for s in spans])


def test_budget_callback_still_stops_before_model_execution(runtime, career_db, fake_langfuse, monkeypatch):
    runner, model = runtime
    class StopBudget(BaseCallbackHandler):
        raise_error = True
        run_inline = True
        def on_chat_model_start(self, *args, **kwargs):
            raise agent_runs.RunError(422, 'budget_exhausted', 'Budget stopped before network')
    model.callbacks = [StopBudget()]
    def no_request(*args, **kwargs):
        pytest.fail('Telemetry swallowed the budget exception and executed the model')
    monkeypatch.setattr(type(model), '_generate', no_request)
    run = new_run(career_db)
    runner.run_agent(run.id, agent_runs.claim_run(career_db, run.id))
    career_db.expire_all()
    assert career_db.get(AgentRun, run.id).error_code == 'budget_exhausted'
    assert career_db.get(AgentRun, run.id).status == RunStatus.FAILED
    assert career_db.query(ResumeVersion).count() == 0


def test_tool_completion_failure_also_closes_the_real_span(runtime, career_db, fake_langfuse, monkeypatch):
    from backend.agent_runtime import tools
    original = tools.append_event
    def fail_completion(db, run_id, event_type, payload):
        if event_type == 'tool.completed':
            raise agent_runs.RunError(503, 'event_write_failed', PRIVATE)
        return original(db, run_id, event_type, payload)
    monkeypatch.setattr(tools, 'append_event', fail_completion)
    runner, _ = runtime
    run = new_run(career_db)
    runner.run_agent(run.id, agent_runs.claim_run(career_db, run.id))
    career_db.expire_all()
    assert career_db.get(AgentRun, run.id).status == RunStatus.FAILED
    spans = [s for s in fake_langfuse.observations if s.kind == 'tool']
    assert len(spans) == 1 and spans[0].ended
    assert spans[0].metadata['status'] == 'failed'
    assert PRIVATE not in json.dumps(spans[0].metadata)


@pytest.mark.parametrize('file_exists', [False, True])
def test_sdk_file_result_preserves_typed_outcome_without_private_body(fake_langfuse, tmp_path, file_exists):
    from deepagents.backends import FilesystemBackend
    from deepagents.middleware.filesystem import FilesystemMiddleware
    from langchain_core.messages import ToolMessage
    from backend.agent_runtime.telemetry import RunTelemetry, SDKToolTelemetry
    trace = RunTelemetry(SimpleNamespace(id=str(uuid4()), session_id=str(uuid4()),
        request_id=str(uuid4()), input_versions={}, attempt=1, execution_epoch=1))
    path = tmp_path / (PRIVATE + '.txt')
    if file_exists:
        path.write_text(PRIVATE)
    middleware = FilesystemMiddleware(backend=FilesystemBackend(root_dir=tmp_path), tools=['read_file'])
    read_file = next(tool for tool in middleware.tools if tool.name == 'read_file')
    output = read_file.invoke({'file_path': '/' + path.name,
        'runtime': SimpleNamespace(tool_call_id='filesystem-test')},
        config={'callbacks': [SDKToolTelemetry(trace)]})
    assert isinstance(output, ToolMessage)
    assert output.status == ('success' if file_exists else 'error')
    assert PRIVATE in output.content  # Successful content and missing-path errors are both private.
    spans = [span for span in fake_langfuse.observations if span.kind == 'tool']
    assert len(spans) == 1 and spans[0].ended
    assert spans[0].metadata['status'] == ('succeeded' if file_exists else 'failed')
    if file_exists:
        assert 'error_code' not in spans[0].metadata
    else:
        assert spans[0].metadata['error_code'] == 'tool_result_error'
    assert PRIVATE not in json.dumps([span.metadata for span in fake_langfuse.observations])
