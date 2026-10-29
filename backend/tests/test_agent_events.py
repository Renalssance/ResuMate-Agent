"""Persistent business events from the real SDK, with no paid model requests."""
import json

from sqlalchemy import select

from backend.db.agent_models import AgentAction, AgentRun, AgentRunEvent, ToolOperation
from backend.db.career_models import ResumeVersion
from backend.schemas.agent_runs import ActionResponse, RunStatus
from backend.services import agent_runs
from backend.tests.agent_fixtures import DraftModel
from backend.tests.career_fixtures import career_engine, career_db
from backend.tests.test_agent_runtime import runtime
from backend.tests.test_worker_delivery import new_run


def events(db, run_id, event_type=None):
    db.rollback()  # End any observer snapshot before reading worker commits.
    query = select(AgentRunEvent).where(AgentRunEvent.run_id == run_id).order_by(AgentRunEvent.seq)
    if event_type:
        query = query.where(AgentRunEvent.type == event_type)
    return list(db.scalars(query))


def test_runtime_persists_visible_text_and_tool_progress(runtime, career_db):
    runner, model = runtime
    run_id = new_run(career_db).id
    runner.run_agent(run_id, agent_runs.claim_run(career_db, run_id))
    recorded = events(career_db, run_id)
    assert ''.join(e.payload['text'] for e in recorded if e.type == 'assistant.delta') == '请审阅草稿'
    started = [e.payload for e in recorded if e.type == 'tool.started']
    assert started == [
        {'tool_name': 'get_application_context', 'operation_key': 'call-0'},
        {'tool_name': 'create_resume_draft', 'operation_key': 'draft:1:initial'},
    ]
    completed = [e.payload for e in recorded if e.type == 'tool.completed']
    assert [e['tool_name'] for e in completed] == ['get_application_context', 'create_resume_draft']
    assert completed[-1]['result_ref'] == career_db.query(ResumeVersion).one().id
    assert not any(e.type == 'usage.updated' for e in recorded)  # This model reports no usage.


def test_repeated_draft_tool_emits_one_artifact(runtime, career_db):
    runner, model = runtime
    model.repeat = True
    run_id = new_run(career_db).id
    runner.run_agent(run_id, agent_runs.claim_run(career_db, run_id))
    artifacts = events(career_db, run_id, 'artifact.created')
    assert len(artifacts) == 1
    version = career_db.query(ResumeVersion).one()
    assert artifacts[0].payload == {'artifact_id': version.id, 'kind': 'resume_version'}
    assert career_db.query(ToolOperation).one().result_ref == version.id


def test_interrupt_has_one_action_event_and_is_not_tool_failure(runtime, career_db):
    runner, model = runtime
    model.ask = True
    run_id = new_run(career_db).id
    epoch = agent_runs.claim_run(career_db, run_id)
    runner.run_agent(run_id, epoch)
    required = events(career_db, run_id, 'action.required')
    assert len(required) == 1
    action = career_db.query(AgentAction).one()
    assert required[0].payload == {'action_id': action.id, 'kind': 'input'}
    assert career_db.get(AgentRun, run_id).status == RunStatus.WAITING_INPUT
    assert events(career_db, run_id, 'tool.failed') == []
    assert not any(e.payload['tool_name'] == 'ask_applicant'
                   for e in events(career_db, run_id, 'tool.completed'))
    agent_runs.answer_action(career_db, 1, run_id, action.id,
                            ActionResponse(decision='submit', answers={'role': 'API'}, expected_revision=1))
    runner.run_agent(run_id, agent_runs.claim_run(career_db, run_id))
    assert len(events(career_db, run_id, 'action.required')) == 1
    assert career_db.get(AgentRun, run_id).status == RunStatus.SUCCEEDED
    assert any(e.payload['tool_name'] == 'ask_applicant'
               for e in events(career_db, run_id, 'tool.completed'))


def test_tool_failure_records_a_code_without_arguments(runtime, career_db):
    runner, model = runtime
    model.bad_fact = True
    run_id = new_run(career_db).id
    runner.run_agent(run_id, agent_runs.claim_run(career_db, run_id))
    failed = events(career_db, run_id, 'tool.failed')
    assert len(failed) == 1
    assert failed[0].payload == {
        'tool_name': 'create_resume_draft', 'operation_key': 'draft:1:initial',
        'error_code': 'invalid_fact', 'message': '工具执行失败',
    }
    assert 'missing' not in json.dumps([e.payload for e in events(career_db, run_id)])
    assert career_db.query(ResumeVersion).count() == 0
    assert career_db.get(AgentRun, run_id).status == RunStatus.FAILED


class StreamDraftModel(DraftModel):
    def _stream(self, messages, **kwargs):
        from langchain_core.messages import AIMessageChunk
        from langchain_core.outputs import ChatGenerationChunk
        message = self._generate(messages, **kwargs).generations[0].message
        if message.tool_calls:
            yield ChatGenerationChunk(message=AIMessageChunk(content='', tool_call_chunks=[{
                'name': call['name'], 'args': json.dumps(call['args']), 'id': call['id'], 'index': index,
            } for index, call in enumerate(message.tool_calls)]))
        else:
            yield ChatGenerationChunk(message=AIMessageChunk(content=[{
                'type': 'reasoning', 'reasoning': 'private reasoning',
            }], additional_kwargs={'reasoning_content': 'private provider reasoning'}))
            for text in ['a' * 200, 'b' * 200, 'c' * 200, 'tail']:
                yield ChatGenerationChunk(message=AIMessageChunk(content=[{'type': 'text', 'text': text}]))
        yield ChatGenerationChunk(message=AIMessageChunk(content='', usage_metadata={
            'input_tokens': 2, 'output_tokens': 1, 'total_tokens': 3,
        }))


def test_sdk_stream_buffers_text_filters_reasoning_and_sums_usage(runtime, career_db, monkeypatch):
    from backend.agent_runtime import events as runtime_events, factory
    runner, _ = runtime
    monkeypatch.setattr(runtime_events, 'monotonic', lambda: 0, raising=False)
    monkeypatch.setattr(factory, 'model_for_user', lambda user_id: StreamDraftModel())
    run_id = new_run(career_db).id
    runner.run_agent(run_id, agent_runs.claim_run(career_db, run_id))
    recorded = events(career_db, run_id)
    assert [e.payload['text'] for e in recorded if e.type == 'assistant.delta'] == [
        'a' * 200 + 'b' * 200 + 'c' * 200, 'tail',
    ]
    assert [e.payload for e in recorded if e.type == 'usage.updated'] == [
        {'prompt_tokens': 2, 'completion_tokens': 1},
        {'prompt_tokens': 4, 'completion_tokens': 2},
        {'prompt_tokens': 6, 'completion_tokens': 3},
    ]
    assert 'private' not in json.dumps([e.payload for e in recorded])
    assert 'fact_refs' not in json.dumps([e.payload for e in recorded])
    assert career_db.get(AgentRun, run_id).status == RunStatus.SUCCEEDED


def test_text_flushes_on_next_chunk_after_interval(runtime, career_db, career_engine, monkeypatch):
    from langchain_core.messages import AIMessageChunk
    from sqlalchemy.orm import sessionmaker
    from backend.agent_runtime import events as runtime_events
    clock = [0]
    monkeypatch.setattr(runtime_events, 'monotonic', lambda: clock[0], raising=False)
    run_id = new_run(career_db).id
    epoch = agent_runs.claim_run(career_db, run_id)
    sink = runtime_events.RuntimeEvents(run_id, epoch, sessionmaker(career_engine))
    sink.message(AIMessageChunk(content='first'), {'langgraph_node': 'model'})
    assert events(career_db, run_id, 'assistant.delta') == []
    clock[0] = 0.101
    sink.message(AIMessageChunk(content=' second'), {'langgraph_node': 'model'})
    assert [e.payload for e in events(career_db, run_id, 'assistant.delta')] == [{'text': 'first second'}]
    sink.message(AIMessageChunk(content='internal summary'), {'langgraph_node': 'SummarizationMiddleware.before_model'})
    sink.flush()
    assert len(events(career_db, run_id, 'assistant.delta')) == 1


def test_usage_resumes_from_persisted_total(runtime, career_db, career_engine):
    from langchain_core.messages import AIMessageChunk
    from sqlalchemy.orm import sessionmaker
    from backend.agent_runtime.events import RuntimeEvents
    run_id = new_run(career_db).id
    epoch = agent_runs.claim_run(career_db, run_id)
    chunk = AIMessageChunk(content='', usage_metadata={'input_tokens': 5, 'output_tokens': 2, 'total_tokens': 7})
    RuntimeEvents(run_id, epoch, sessionmaker(career_engine)).message(chunk, {'langgraph_node': 'model'})
    RuntimeEvents(run_id, epoch, sessionmaker(career_engine)).message(chunk, {'langgraph_node': 'model'})
    assert [e.payload for e in events(career_db, run_id, 'usage.updated')] == [
        {'prompt_tokens': 5, 'completion_tokens': 2}, {'prompt_tokens': 10, 'completion_tokens': 4},
    ]


def test_artifact_and_event_rollback_together(runtime, career_db, monkeypatch):
    import pytest
    from backend.agent_runtime import tools
    original_append = tools.append_event
    def fail_after_append(db, run_id, event_type, payload):
        original_append(db, run_id, event_type, payload)
        raise RuntimeError('transaction failure')
    monkeypatch.setattr(tools, 'append_event', fail_after_append)
    run_id = new_run(career_db).id
    epoch = agent_runs.claim_run(career_db, run_id)
    with pytest.raises(RuntimeError, match='transaction failure'):
        tools.save_draft(run_id, epoch, {'summary': 'real work'}, [])
    assert events(career_db, run_id, 'artifact.created') == []
    assert career_db.query(ResumeVersion).count() == 0
    assert career_db.query(ToolOperation).count() == 0


def test_action_waiting_status_and_event_rollback_together(runtime, career_db, monkeypatch):
    import pytest
    from langgraph.types import Interrupt
    runner, _ = runtime
    original_append = agent_runs.append_event
    def fail_after_waiting(db, run_id, event_type, payload):
        original_append(db, run_id, event_type, payload)
        if payload.get('status') == RunStatus.WAITING_INPUT:
            raise RuntimeError('transaction failure')
    monkeypatch.setattr(agent_runs, 'append_event', fail_after_waiting)
    run_id = new_run(career_db).id
    epoch = agent_runs.claim_run(career_db, run_id)
    with pytest.raises(RuntimeError, match='transaction failure'):
        runner._save_interrupts(run_id, epoch, [Interrupt(value={'kind': 'input', 'question': 'Role?'}, id='pause-1')])
    assert events(career_db, run_id, 'action.required') == []
    assert career_db.query(AgentAction).count() == 0
    assert career_db.get(AgentRun, run_id).status == RunStatus.RUNNING


def test_custom_model_endpoint_requests_stream_usage(monkeypatch):
    from functools import partial
    from types import SimpleNamespace
    import httpx
    from langchain_core.messages import HumanMessage
    from backend.agent_runtime import factory
    requested = []
    def respond(request):
        requested.append(json.loads(request.content))
        chunks = [
            {'id': 'completion-1', 'object': 'chat.completion.chunk', 'created': 0, 'model': 'compatible-model',
             'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': 'Hello'}, 'finish_reason': None}]},
            {'id': 'completion-1', 'object': 'chat.completion.chunk', 'created': 0, 'model': 'compatible-model',
             'choices': [], 'usage': {'prompt_tokens': 4, 'completion_tokens': 1, 'total_tokens': 5}},
        ]
        stream = ''.join(f'data: {json.dumps(chunk)}\n\n' for chunk in chunks) + 'data: [DONE]\n\n'
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, text=stream)
    monkeypatch.setattr(factory, 'resolve_effective_llm_settings', lambda user_id: SimpleNamespace(
        api_key='synthetic-key', base_url='https://model.invalid/v1', model='compatible-model',
        max_tokens=100, request_timeout_seconds=30,
    ))
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(factory, 'ChatOpenAI', partial(factory.ChatOpenAI, http_client=client))
        chunks = list(factory.model_for_user(1).stream([HumanMessage(content='Hello')]))
    assert requested[0].get('stream_options') == {'include_usage': True}
    usage = [chunk.usage_metadata for chunk in chunks if chunk.usage_metadata is not None]
    assert sum(item['input_tokens'] for item in usage) == 4
    assert sum(item['output_tokens'] for item in usage) == 1


def test_cancelled_worker_cannot_publish_buffered_text_or_usage(runtime, career_db, career_engine):
    import pytest
    from langchain_core.messages import AIMessageChunk
    from sqlalchemy.orm import sessionmaker
    from backend.agent_runtime.events import RuntimeEvents
    run_id = new_run(career_db).id
    epoch = agent_runs.claim_run(career_db, run_id)
    sink = RuntimeEvents(run_id, epoch, sessionmaker(career_engine))
    sink.message(AIMessageChunk(content='pending text'), {'langgraph_node': 'model'})
    agent_runs.cancel_run(career_db, 1, run_id)
    with pytest.raises(agent_runs.RunError):
        sink.flush()
    with pytest.raises(agent_runs.RunError):
        sink.message(AIMessageChunk(content='', usage_metadata={
            'input_tokens': 8, 'output_tokens': 3, 'total_tokens': 11,
        }), {'langgraph_node': 'model'})
    assert events(career_db, run_id, 'assistant.delta') == []
    assert events(career_db, run_id, 'usage.updated') == []


def test_model_stream_failure_flushes_text_before_failed_status(runtime, career_db, monkeypatch):
    from langchain_core.messages import AIMessageChunk
    from langchain_core.outputs import ChatGenerationChunk
    from backend.agent_runtime import events as runtime_events, factory
    class FailingStreamModel(DraftModel):
        def _stream(self, messages, **kwargs):
            yield ChatGenerationChunk(message=AIMessageChunk(content='partial answer'))
            raise ValueError('private provider response')
    monkeypatch.setattr(runtime_events, 'monotonic', lambda: 0)
    monkeypatch.setattr(factory, 'model_for_user', lambda user_id: FailingStreamModel())
    runner, _ = runtime
    run_id = new_run(career_db).id
    runner.run_agent(run_id, agent_runs.claim_run(career_db, run_id))
    recorded = events(career_db, run_id)
    assert recorded[-2].type == 'assistant.delta'
    assert recorded[-2].payload == {'text': 'partial answer'}
    assert recorded[-1].payload == {'status': 'failed', 'error_code': 'agent_failed'}
    assert 'private' not in json.dumps([e.payload for e in recorded])
