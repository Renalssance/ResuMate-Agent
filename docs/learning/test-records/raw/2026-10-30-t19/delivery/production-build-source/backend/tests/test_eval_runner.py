"""CLI contracts run in fresh processes so ambient project databases stay untouched."""
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]


def launch(tmp_path, *arguments, env=None):
    output = tmp_path / 'out'
    process = subprocess.run([sys.executable, '-m', 'evals.run', '--suite', 'core', '--output', str(output),
                              *arguments], cwd=ROOT, env={**os.environ, **(env or {})}, capture_output=True, text=True)
    reports = list(output.glob('*/report.json'))
    assert reports, process.stderr
    return process, json.loads(reports[0].read_text()), reports[0].parent


def test_explicit_env_file_only_loads_model_whitelist(tmp_path):
    from evals.run import load_model_env
    path = tmp_path / 'credentials.env'
    path.write_text('OPENAI_API_KEY=synthetic-secret\nLLM_MODEL=synthetic-model\n'
                    'DATABASE_URL=sqlite:///private.db\nAGENT_STATE_DIR=/private/state\n'
                    'LANGFUSE_SECRET_KEY=private-observation\n')
    assert load_model_env(path) == {'OPENAI_API_KEY': 'synthetic-secret', 'LLM_MODEL': 'synthetic-model'}


def test_live_missing_config_is_incomplete_without_reading_credentials(tmp_path):
    process, report, invocation = launch(tmp_path, '--mode', 'live', '--cases', 'normal-api',
        '--env-file', str(tmp_path / 'does-not-exist.env'))
    assert process.returncode == 2
    assert report['results'][0]['status'] == 'not_run'
    assert report['error_code'] == 'configuration_error'
    assert not list(invocation.rglob('*.sqlite'))


def test_two_stub_cases_have_isolated_databases_and_no_provider_client(tmp_path):
    sentinel = tmp_path / 'existing.db'
    sentinel.write_text('existing operator database must stay untouched')
    process, report, invocation = launch(tmp_path, '--mode', 'stub', '--cases', 'normal-api,ask-metric',
        env={'DATABASE_URL': 'sqlite:///' + str(sentinel), 'OPENAI_API_KEY': 'must-not-use',
             'OPENAI_BASE_URL': 'http://127.0.0.1:1'})
    assert process.returncode == 0, process.stderr + json.dumps(report)
    assert sentinel.read_text() == 'existing operator database must stay untouched'
    cases = [json.loads((invocation / 'cases' / (name + '.json')).read_text())
             for name in ('normal-api', 'ask-metric')]
    assert cases[0]['output']['run_id'] != cases[1]['output']['run_id']
    assert cases[1]['output']['coverage']['waiting_observed'] is True
    assert cases[1]['output']['coverage']['checkpoint_reopened'] is True
    assert all(case['verdict']['passed'] for case in cases)
    assert len(list(invocation.glob('state/*/eval.sqlite'))) == 2
    assert report['semantic_status'] == 'not_applicable'
    recorded = list(map(json.loads, (invocation / 'calls.jsonl').read_text().splitlines()))
    assert recorded and {row['model'] for row in recorded} == {case['output']['model'] for case in cases}


def test_only_public_main_text_is_saved(tmp_path):
    from evals.records import CallRecorder
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, LLMResult
    from uuid import uuid4
    recorder = CallRecorder(tmp_path / 'calls.jsonl', case_id='synthetic')
    call_id = uuid4()
    recorder.on_chat_model_start({}, [[]], run_id=call_id)
    message = AIMessage(content=[{'type': 'text', 'text': 'public text'},
                                 {'type': 'reasoning', 'reasoning': 'private reasoning'}],
                        additional_kwargs={'reasoning_content': 'private additional reasoning'})
    recorder.on_llm_end(LLMResult(generations=[[ChatGeneration(message=message)]]), run_id=call_id)
    text = (tmp_path / 'calls.jsonl').read_text()
    assert 'public text' in text
    assert 'private' not in text
    summary_id = uuid4()
    recorder.on_chat_model_start({}, [[]], run_id=summary_id, metadata={'lc_source': 'summarization'})
    recorder.on_llm_end(LLMResult(generations=[[ChatGeneration(message=AIMessage(content='private summary'))]]), run_id=summary_id)
    assert 'private summary' not in (tmp_path / 'calls.jsonl').read_text()


def test_real_faults_rollback_and_cancellation_leave_no_artifacts(tmp_path):
    process, report, invocation = launch(tmp_path, '--mode', 'stub', '--cases',
        'tool-read-failure,tool-write-rollback,cancel-waiting,duplicate-draft')
    assert process.returncode == 0, json.dumps(report)
    details = {path.stem: json.loads(path.read_text()) for path in (invocation / 'cases').glob('*.json')}
    for case_id in ('tool-read-failure', 'tool-write-rollback'):
        detail = details[case_id]
        assert detail['output']['coverage']['fault_injected'] is True
        assert detail['db_snapshot']['versions'] == []
        assert detail['db_snapshot']['operations'] == []
        assert not any(event['type'] == 'artifact.created' for event in detail['db_snapshot']['events'])
        assert any(event['type'] == 'tool.failed' for event in detail['db_snapshot']['events'])
    rollback = details['tool-write-rollback']
    proposals = [call for message in rollback['output']['public_model_output']
                 for call in message['tool_calls'] if call['name'] == 'create_resume_draft']
    assert len(proposals) == 1
    assert proposals[0]['args']['changes'][0]['after'] == rollback['input']['proposal']['after']
    assert details['cancel-waiting']['output']['coverage']['cancel_claim_blocked'] is True
    repeated = details['duplicate-draft']['output']['coverage']['duplicate_result_refs']
    assert len(repeated) == 2 and repeated[0] == repeated[1]


@pytest.mark.parametrize('provider_status', [400, 200])
def test_live_failure_removes_only_generated_raw_checkpoints_and_reports_unknown_cost(tmp_path, provider_status):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from backend.tests.test_eval_budget import config
    class ProviderError(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', '0')))
            self.send_response(provider_status)
            self.send_header('Content-Type', 'application/json' if provider_status == 400 else 'text/event-stream')
            self.end_headers()
            if provider_status == 400:
                self.wfile.write(b'{"error":{"message":"private-provider-body","type":"invalid_request_error","code":"synthetic_failure"}}')
            else:
                chunks = [dict(id='local', object='chat.completion.chunk', created=1, model='synthetic',
                    choices=[dict(index=0, delta=dict(role='assistant', content='Public refusal'), finish_reason=None)]),
                    dict(id='local', object='chat.completion.chunk', created=1, model='synthetic',
                    choices=[dict(index=0, delta={}, finish_reason='stop')],
                    usage=dict(prompt_tokens=1000001, completion_tokens=1, total_tokens=1000002))]
                self.wfile.write((''.join('data: ' + json.dumps(chunk) + '\n\n' for chunk in chunks)
                                 + 'data: [DONE]\n\n').encode())

        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), ProviderError)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    budget_file = tmp_path / 'budget.json'
    budget_file.write_text(json.dumps(config(max_total_cost='1.3', max_case_cost='1.3').public()))
    env_file = tmp_path / 'synthetic.env'
    env_file.write_text(f'OPENAI_API_KEY=local-fake-key\nOPENAI_BASE_URL=http://127.0.0.1:{server.server_port}/v1\n')
    unrelated = tmp_path / 'checkpoints.sqlite'
    unrelated.write_text('unrelated checkpoint must remain')
    try:
        process, report, invocation = launch(tmp_path, '--mode', 'live', '--cases', 'normal-api',
            '--config', str(budget_file), '--env-file', str(env_file))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert process.returncode == (1 if provider_status == 400 else 2), json.dumps(report)
    assert report['cost']['model_calls'] == 1
    if provider_status == 400:
        assert report['cost']['reserved_cost'] == '1.21970880'
        assert report['cost']['unknown_usage_calls'] == 1
    else:
        assert report['results'][0]['status'] == 'incomplete'
        assert report['results'][0]['error_code'] == 'budget_config_mismatch'
        assert report['cost']['stop_reason'] == 'budget_config_mismatch'
    assert list(invocation.glob('state/*/eval.sqlite'))
    assert not list(invocation.glob('state/*/agent/checkpoints.sqlite*'))
    assert unrelated.read_text() == 'unrelated checkpoint must remain'
    for path in invocation.rglob('*.json*'):
        assert 'private-provider-body' not in path.read_text()
        assert 'local-fake-key' not in path.read_text()


def test_tool_only_and_invalid_proposals_remain_public_record_evidence(tmp_path):
    from evals.records import CallRecorder
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, LLMResult
    from uuid import uuid4
    recorder = CallRecorder(tmp_path / 'calls.jsonl', case_id='rejected-proposal')
    call_id = uuid4()
    proposal = {'changes': [{'section': '/self_summary', 'before': 'wrong before',
                             'after': 'Proposed public text', 'fact_refs': []}]}
    message = AIMessage(content='',
        tool_calls=[{'id': 'draft-call', 'name': 'create_resume_draft', 'args': proposal}],
        invalid_tool_calls=[{'id': 'bad-json', 'name': 'create_resume_draft', 'args': '{broken-json',
                             'error': 'private parser diagnostic'}],
        additional_kwargs={'reasoning_content': 'private reasoning', 'provider_body': 'private provider body'})
    recorder.on_chat_model_start({}, [[]], run_id=call_id)
    recorder.on_llm_end(LLMResult(generations=[[ChatGeneration(message=message)]]), run_id=call_id)
    expected = {'text': '', 'tool_calls': [{'id': 'draft-call', 'name': 'create_resume_draft', 'args': proposal}],
                'invalid_tool_calls': [{'id': 'bad-json', 'name': 'create_resume_draft', 'args': '{broken-json'}]}
    assert recorder.outputs == [expected]
    lines = [json.loads(line) for line in (tmp_path / 'calls.jsonl').read_text().splitlines()]
    assert lines[-1]['public_output'] == expected
    assert 'private' not in (tmp_path / 'calls.jsonl').read_text()


@pytest.mark.parametrize('lost_field', ['constraints', 'facts', 'memories', 'applicantAnswers', 'outputs', 'system_message'])
def test_later_context_loss_cannot_be_masked_by_earlier_or_embedded_context(tmp_path, lost_field):
    from copy import deepcopy
    from evals.records import CallRecorder
    from langchain_core.messages import HumanMessage, SystemMessage
    from uuid import uuid4
    recorder = CallRecorder(tmp_path / 'calls.jsonl', case_id='context-proof')
    required = dict(runId='run-1', inputVersions={'resume': 'v1'}, constraints=['keep fact', 'no invention'],
                    facts=[{'id': 'fact-1', 'content': '仅测试环境'}],
                    memories=[{'id': 'memory-1', 'content': '中文简短表达'}],
                    applicantAnswers=[{'actionId': 'answered-1'}], outputs=[{'id': 'draft-1'}])
    recorder.context_expectations = lambda: deepcopy(required)
    recorder.epoch = 2
    recorder.on_chat_model_start({}, [[SystemMessage(content='必保留业务上下文\n' + json.dumps(required))]], run_id=uuid4())
    assert recorder.required_contexts[-1]['passed'] is True
    damaged = deepcopy(required)
    if lost_field == 'constraints':
        damaged['constraints'][0] = 'replace facts'
    elif lost_field in ('facts', 'memories', 'applicantAnswers', 'outputs'):
        damaged[lost_field] = []
    messages = [SystemMessage(content='必保留业务上下文（摘要调用）\n' + json.dumps(damaged))]
    if lost_field == 'system_message':
        messages = []
    # Summary history embeds a formerly valid context. It is not this call's injected context.
    messages.append(HumanMessage(content='Old transcript: 必保留业务上下文\n' + json.dumps(required)))
    second_id = uuid4()
    recorder.on_chat_model_start({}, [messages], run_id=second_id, metadata={'lc_source': 'summarization'})
    assert recorder.required_contexts[-1]['passed'] is False
    assert recorder.required_contexts[-1]['sdk_call_id'] == str(second_id)
    assert recorder.required_contexts[-1]['execution_epoch'] == 2
    assert recorder.required_contexts[-1]['kind'] == 'summary'


def test_long_context_checks_every_real_request_against_available_sql_refs(tmp_path):
    process, report, invocation = launch(tmp_path, '--mode', 'stub', '--cases', 'long-context')
    assert process.returncode == 0, json.dumps(report)
    detail = json.loads((invocation / 'cases' / 'long-context.json').read_text())
    proof = detail['output']['required_context_checks']
    assert proof and all(item['passed'] for item in proof)
    assert any(item['kind'] == 'summary' and item['execution_epoch'] == 2 for item in proof)
    assert any(item['expected']['applicantAnswers'] for item in proof if item['execution_epoch'] == 2)
    assert any(item['expected']['outputs'] for item in proof)
    calls = [json.loads(line) for line in (invocation / 'calls.jsonl').read_text().splitlines()]
    assert {item['sdk_call_id'] for item in proof} == {call['sdk_call_id'] for call in calls if call['event'] == 'started'}
