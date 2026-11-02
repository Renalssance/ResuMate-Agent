import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException
from backend.db.database import Base
from backend.db.models import User
from backend.services import llm_calls


@pytest.fixture
def calls(monkeypatch):
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(llm_calls, 'SessionLocal', factory)
    with factory() as db:
        db.add_all([User(id=1, username='one', password_hash='x'), User(id=2, username='two', password_hash='x')])
        db.commit()
    yield factory
    engine.dispose()


def test_call_records_exact_input_partial_failure_and_owner(calls):
    call = llm_calls.CallTrace(1, 'document.parse_resume', 'https://model.test/v1',
        {'model': 'test', 'messages': [{'role': 'user', 'content': 'resume'}],
         'reasoning_effort': 'none', 'api_key': 'secret'}, attempt=2)
    call.add_chunk({'choices': [{'delta': {'content': '{"name":'}, 'finish_reason': None}]})
    call.finish(error=RuntimeError('stream interrupted'))
    with calls() as db:
        row = llm_calls.get_call(db, 1, call.id)
        assert row['request']['messages'][0]['content'] == 'resume'
        assert row['request']['reasoning_effort'] == 'none'
        assert 'api_key' not in row['request']
        assert row['output']['choices'][0]['message']['content'] == '{"name":'
        assert row['status'] == 'failed'
        assert row['attempt'] == 2
        assert row['usage'] is None
        assert llm_calls.list_calls(db, 2, 0, 20)['total'] == 0
        with pytest.raises(HTTPException) as error:
            llm_calls.get_call(db, 2, call.id)
        assert error.value.status_code == 404


def test_stream_usage_and_length_are_preserved(calls):
    call = llm_calls.CallTrace(1, 'chat', '', {'model': 'test'})
    call.add_chunk({'choices': [{'index': 0, 'delta': {'content': 'part', 'reasoning_content': 'thinking'}, 'finish_reason': 'length'}]})
    call.add_chunk({'choices': [], 'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30}})
    call.finish()
    with calls() as db:
        row = llm_calls.get_call(db, 1, call.id)
        assert row['status'] == 'truncated'
        assert row['usage']['total_tokens'] == 30
        assert row['output']['choices'][0]['message']['reasoning_content'] == 'thinking'
        page = llm_calls.list_calls(db, 1, 0, 20)
        assert page['total'] == 1
        assert 'request' not in page['items'][0]


def test_langchain_records_messages_reasoning_and_usage(calls):
    import json
    import httpx
    from backend.agent_runtime.reasoning_model import ReasoningChatOpenAI
    from backend.agent_runtime.call_inspection import ModelCallInspection
    from langchain_core.messages import SystemMessage, HumanMessage

    def respond(request):
        payload = json.loads(request.content)
        assert payload['messages'][0]['content'] == 'Extract fields'
        events = [
            {'choices': [{'index': 0, 'delta': {'role': 'assistant', 'reasoning_content': 'brief reasoning'}, 'finish_reason': None}]},
            {'choices': [{'index': 0, 'delta': {'content': '{"skill":"Python"}'}, 'finish_reason': 'stop'}]},
            {'choices': [], 'usage': {'prompt_tokens': 10, 'completion_tokens': 8, 'total_tokens': 18}},
        ]
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, text=''.join(
            'data: '+json.dumps({'id': 'call', 'object': 'chat.completion.chunk', 'created': 0, 'model': 'test', **event})+'\n\n'
            for event in events)+'data: [DONE]\n\n')

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        model = ReasoningChatOpenAI(model='test', api_key='secret', base_url='https://model.test/v1',
            http_client=client, max_tokens=100, stream_usage=True,
            callbacks=[ModelCallInspection(1, 'https://model.test/v1', 'chat', 30)])
        list(model.stream([SystemMessage(content='Extract fields'), HumanMessage(content='Skills: Python')]))
    with calls() as db:
        items = llm_calls.list_calls(db, 1, 0, 20)['items']
        assert len(items) == 1
        row = llm_calls.get_call(db, 1, items[0]['id'])
        assert row['request']['messages'][0] == {'role': 'system', 'content': 'Extract fields'}
        assert row['request']['max_completion_tokens'] == 100
        assert row['output']['choices'][0]['message']['content'] == '{"skill":"Python"}'
        assert row['output']['choices'][0]['message']['reasoning_content'] == 'brief reasoning'
        assert row['usage']['total_tokens'] == 18
        assert row['status'] == 'completed'
