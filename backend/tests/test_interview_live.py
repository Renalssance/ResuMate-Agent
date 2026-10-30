"""Live interview eval uses the SDK HTTP boundary; no provider network is needed."""
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, LLMResult

ROOT = Path(__file__).resolve().parents[2]


def test_recorder_uses_only_current_required_and_actual_tool_returns(tmp_path):
    from evals.interview_records import InterviewCallRecorder
    recorder = InterviewCallRecorder(tmp_path / 'calls.jsonl', case_id='synthetic')
    recorder.business_run_id, recorder.epoch = 'run-1', 2
    required = {'kind': 'interview_generation', 'runId': 'run-1', 'expectedTurn': 1,
                'currentAnswer': {'answer': 'Accepted answer'}, 'memories': []}
    context = {'source': {'job': {'rawText': 'Actual tool material'}}, 'turns': [], 'memories': []}
    messages = [SystemMessage(content='必保留业务上下文\n' + json.dumps(required)),
                HumanMessage(content='Old transcript: 必保留业务上下文\n{"runId":"not-current"}'),
                AIMessage(content='', tool_calls=[{'id': 'ctx-1', 'name': 'get_interview_context', 'args': {}}]),
                ToolMessage(content=json.dumps(context), name='get_interview_context', tool_call_id='ctx-1')]
    call_id = uuid4()
    recorder.on_chat_model_start({}, [messages], run_id=call_id)
    assert recorder.interview_calls[0]['required'] == required
    assert recorder.interview_calls[0]['context'] == context
    assert recorder.interview_calls[0]['tool_inputs'][0]['tool_call_id'] == 'ctx-1'
    assert recorder.interview_calls[0]['execution_epoch'] == 2
    assert 'not-current' not in json.dumps(recorder.interview_calls)
    called = []
    recorder.after_response = lambda record: called.append(record['step'])
    step = {'feedback': None, 'question': {'text': 'Public question'}}
    response = LLMResult(generations=[[ChatGeneration(message=AIMessage(content='', tool_calls=[
        {'id': 'step-1', 'name': 'InterviewStep', 'args': step}]))]])
    recorder.on_llm_end(response, run_id=call_id)
    assert called == [step]
    assert recorder.calls[str(call_id)]['event'] == 'completed'


def run_live(tmp_path, scenario):
    from evals.run import isolated_environment
    directory = tmp_path / scenario
    directory.mkdir()
    result = subprocess.run([sys.executable, '-m', 'backend.tests.interview_live_fixture', str(directory), scenario],
        cwd=ROOT, env=isolated_environment(directory, {'OPENAI_API_KEY': 'synthetic-not-secret',
            'OPENAI_BASE_URL': 'https://synthetic.invalid/v1'}), text=True, capture_output=True, timeout=100)
    assert result.returncode == 0, result.stdout + result.stderr
    artifact = json.loads((directory / 'result.json').read_text())
    requests = [json.loads(line) for line in (directory / 'http.jsonl').read_text().splitlines()] if (directory / 'http.jsonl').exists() else []
    return artifact, requests, directory


@pytest.mark.parametrize('scenario', ['followup', 'pages', 'cancel', 'eight', 'replay', 'frozen', 'memory', 'forbidden', 'budget'])
def test_actual_chatopenai_interview_graph_and_budget(tmp_path, scenario):
    result, requests, directory = run_live(tmp_path, scenario)
    output = result['output']
    if scenario == 'budget':
        assert result['status'] == 'incomplete'
        assert result['error_code'] == 'budget_exhausted'
        assert requests == []
        assert result['cost']['model_calls'] == 0
        assert output['executed'] is False
        assert result['db_snapshot']['runs'][0]['error_code'] == 'budget_exhausted'
    elif scenario == 'forbidden':
        assert result['status'] == 'fail'
        assert len(requests) == result['cost']['model_calls'] == 1
        assert result['cost']['unknown_usage_calls'] == 1
        assert len(result['db_snapshot']['runs']) == 1
        assert result['db_snapshot']['runs'][0]['status'] == 'failed'
        records = (directory / 'calls.jsonl').read_text()
        assert 'PermissionDeniedError' in records and '403' in records
        assert 'PRIVATE_PROVIDER_BODY' not in records + json.dumps(result)
    else:
        assert result['status'] == 'pass', result['verdict']
        assert {item['status'] for item in result['semantic']['items']} == {'unreviewed'}
        assert result['cost']['model_calls'] == len(requests) > 0
        assert result['cost']['unknown_usage_calls'] == 0
        assert output['evidence_source'] == 'sdk_model_inputs'
        assert all(call['run_id'] == call['required']['runId'] for call in output['model_calls'])
        assert len(output['model_calls']) == len(requests)
        if scenario == 'pages':
            reads = [tool for call in output['model_calls'] for tool in call['tool_inputs'] if tool['name'] == 'read_file']
            assert any(item['args'].get('offset', 0) > 0 for item in reads)
            contexts = [call['context'] for call in output['model_calls'] if 'context' in call]
            assert any('LONG_SOURCE_END' in json.dumps(item['source']) for item in contexts)
        if scenario == 'cancel':
            for stop in output['observations']['stops']:
                assert stop['barrier'] == 'after_model_response_before_delivery'
                assert stop['model_calls_at_stop'] == stop['model_calls_after']
                assert stop['settled_calls_at_stop'] > 0
                assert stop['public_step_at_stop']['feedback'] is not None
        if scenario == 'followup':
            assert len(result['db_snapshot']['turns']) == 3
            from copy import deepcopy
            from evals.interview_verifiers import verify_interview
            corrupted = deepcopy(output)
            corrupted['model_calls'][0]['required']['runId'] = 'not-this-run'
            assert not verify_interview(result['input'], corrupted, result['db_snapshot'])['passed']
            wire = json.dumps(requests)
            for answer in result['input']['input']['answers']:
                assert answer in wire


@pytest.mark.parametrize('scenario', ['cancel-slow', 'cancel-budget'])
def test_live_cancellation_waits_configured_requests_and_wakes_on_budget_stop(tmp_path, scenario):
    from time import monotonic
    started = monotonic()
    result, requests, _ = run_live(tmp_path, scenario)
    elapsed = monotonic() - started
    if scenario == 'cancel-slow':
        assert elapsed >= 16
        assert result['status'] == 'pass', result['verdict']
        assert len(result['output']['observations']['stops']) == 2
    else:
        assert elapsed < 10, 'A finished generation must wake the barrier without waiting for another response'
        assert result['status'] == 'incomplete'
        assert result['error_code'] == 'budget_exhausted'
        assert len(requests) == result['cost']['model_calls'] == 3
        assert result['db_snapshot']['runs'][-1]['error_code'] == 'budget_exhausted'
