import asyncio
import json
import logging
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from backend import logging_config
from backend.agent import agent, interview_tools
from backend.agents.harness import AgentHarness

SECRET = 'synthetic-provider-secret-012345'
MATERIAL = 'synthetic-private-resume-material'


@pytest.fixture
def llm_logs(caplog):
    logger = logging.getLogger('backend.llm')
    logger.addHandler(caplog.handler)
    caplog.set_level(logging.INFO)
    yield caplog
    logger.removeHandler(caplog.handler)


def test_llm_logs_keep_diagnostics_without_prompt_response_or_error_body(llm_logs):
    metadata = {'model': 'synthetic-model', 'attempt': 1, 'api_key': SECRET,
                'filename': MATERIAL, 'response_format': {'schema': MATERIAL}}
    logging_config.log_llm_prompt('test', MATERIAL, metadata)
    logging_config.log_llm_response('test', MATERIAL, metadata)
    logging_config.log_llm_request('test', metadata)
    try:
        raise RuntimeError(SECRET)
    except RuntimeError as exc:
        logging_config.log_llm_error('test', exc, metadata)
    logging_config.log_llm_validation_error('test', [{'loc': ['text'], 'input': MATERIAL, 'msg': SECRET}], metadata)
    assert SECRET not in llm_logs.text
    assert MATERIAL not in llm_logs.text
    assert 'RuntimeError' in llm_logs.text and 'synthetic-model' in llm_logs.text


def test_harness_progress_and_reflection_do_not_republish_provider_body(monkeypatch, llm_logs):
    class Result(BaseModel):
        text: str
    events, calls = [], []
    target = AgentHarness.__new__(AgentHarness)
    target.model = 'synthetic-model'
    target.progress_callback = lambda **event: events.append(event)
    target._record_usage_error = lambda *args: None
    monkeypatch.setattr(target, 'load_prompt', lambda _: 'synthetic')
    def fail(task, messages, *args, **kwargs):
        calls.append(messages)
        raise RuntimeError(SECRET)
    monkeypatch.setattr(target, '_create_chat_completion', fail)
    with pytest.raises(RuntimeError):
        target.run_schema(task='test', prompt_name='test', schema=Result, variables={})
    assert SECRET not in json.dumps(events)
    assert SECRET not in json.dumps(calls)
    assert SECRET not in llm_logs.text
    assert 'RuntimeError' in json.dumps(events)


def test_chat_stream_error_is_safe_but_still_finishes(monkeypatch, llm_logs):
    class FailedAgent:
        async def astream(self, *args, **kwargs):
            raise RuntimeError(SECRET)
            yield
    monkeypatch.setattr(agent, 'storage', SimpleNamespace(load=lambda *_: [], save=lambda *_: None))
    monkeypatch.setattr(agent, 'create_agent_with_interview_tools', lambda *_: (FailedAgent(), None, 1,
        SimpleNamespace(model='synthetic-model', base_url='https://model.example')))
    monkeypatch.setattr(agent, 'record_llm_usage', lambda **_: None)
    async def collect():
        return ''.join([chunk async for chunk in agent.chat_with_agent_stream(MATERIAL, 'synthetic', 'session')])
    output = asyncio.run(collect())
    assert SECRET not in output and SECRET not in llm_logs.text
    assert MATERIAL not in llm_logs.text
    assert 'model_request_failed' in output and '[DONE]' in output


@pytest.mark.parametrize('name,args', [('analyze_resume', {'raw_text': 'synthetic resume content ' * 5}),
                                      ('analyze_jd', {'jd_text': 'synthetic job description ' * 5})])
def test_legacy_tool_failure_does_not_return_provider_body(name, args, monkeypatch, llm_logs):
    class FailedModel:
        model_name = 'synthetic-model'
        def invoke(self, prompt):
            raise RuntimeError(SECRET)
    monkeypatch.setattr(interview_tools, '_get_llm', lambda **_: FailedModel())
    tool = next(tool for tool in interview_tools.create_interview_tools(1) if tool.name == name)
    result = tool.invoke(args)
    assert SECRET not in result and SECRET not in llm_logs.text
    assert 'RuntimeError' in result
