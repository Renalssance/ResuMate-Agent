"""All eight live task scenarios use actual HTTP serialization, services and SQL, offline."""
import json
from pathlib import Path
import subprocess
import sys
import pytest

from backend.tests.test_eval_budget import config
from evals.fixtures import load_cases
from evals.run import isolated_environment

TASK_IDS = [case['id'] for case in load_cases() if case.get('runner') == 'durable']


def run_local(tmp_path, case_id, *, fail=False, total=None, fail_after=None):
    case = next(case for case in load_cases() if case['id'] == case_id)
    request = {'case':case, 'mode':'live', 'invocation':str(tmp_path), 'config':config(
        max_total_cost=total or ('1.3' if fail else '10'), max_case_cost=total or '10', max_model_calls=100, max_case_model_calls=100).public()}
    (tmp_path / 'request.json').write_text(json.dumps(request))
    script = '''
import json, os
from pathlib import Path
from unittest.mock import patch
import httpx
from evals import task_live_model
from backend.tests.task_http_fixture import TaskHTTPFixture
from evals.task_runner import execute_task_case
root = Path(os.environ['DATABASE_URL'].removeprefix('sqlite:///')).parent
request = json.loads((root / 'request.json').read_text())
original = task_live_model.LiveTaskModel
fixture = TaskHTTPFixture(root / 'http-requests.jsonl', fail=FAIL, fail_after=AFTER)
def model(config, recorder):
    return original(config, recorder, transport=httpx.MockTransport(fixture))
with patch.object(task_live_model, 'LiveTaskModel', model):
    result = execute_task_case(request)
print(json.dumps({'status':result['status'], 'error_code':result.get('error_code')}))
'''.replace('fail=FAIL', f'fail={fail!r}').replace('fail_after=AFTER', f'fail_after={fail_after!r}')
    env = isolated_environment(tmp_path, {'OPENAI_API_KEY':'synthetic-not-secret', 'OPENAI_BASE_URL':'https://synthetic.invalid/v1'})
    process = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[2],
                             env=env, capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    result = json.loads((tmp_path / 'cases' / f'{case_id}.json').read_text())
    wire = [json.loads(line) for line in (tmp_path / 'http-requests.jsonl').read_text().splitlines()]
    return result, wire


@pytest.mark.parametrize('case_id', TASK_IDS)
def test_live_task_scenario_uses_real_http_and_sql(tmp_path, case_id):
    result, wire = run_local(tmp_path, case_id)
    assert result['status'] == 'pass', json.dumps(result['verdict'])
    assert result['mode'] == 'live'
    assert all(item['status'] == 'unreviewed' for item in result['semantic']['items'])
    assert len(wire) == result['cost']['model_calls'] == len(result['output']['model_calls'])
    assert wire and result['cost']['unknown_usage_calls'] == 0
    assert [call['request'] for call in result['output']['model_calls']] == wire
    assert result['db_snapshot']['runs']
    if case_id == 'question-result-replay':
        assert result['output']['coverage']['original_question'] == result['output']['coverage']['current_question']
    if case_id == 'cancel-recovery':
        assert result['output']['coverage']['model_calls_after_cancel'] == 0


def test_live_task_budget_failure_preserves_sql_and_unknown_reserve(tmp_path):
    result, wire = run_local(tmp_path, 'followup-result-replay', fail=True)
    assert result['status'] == 'incomplete'
    assert result['error_code'] == 'budget_exhausted'
    assert len(wire) == result['cost']['model_calls'] == result['cost']['unknown_usage_calls'] == 1
    assert result['cost']['reserved_cost'] == '1.21970880'
    assert not result['db_snapshot']['operations']
    assert result['db_snapshot']['runs'][0]['result_json'] is None
    assert 'private provider failure' not in (tmp_path / 'cases' / 'followup-result-replay.json').read_text()


def test_cli_live_tasks_share_one_ledger_and_stop_before_next_case(tmp_path):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from backend.tests.test_eval_runner import launch
    sent = []
    class LocalProvider(BaseHTTPRequestHandler):
        def do_POST(self):
            sent.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(403)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"private body","code":"insufficient_quota"}}')
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), LocalProvider)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    budget = tmp_path / 'config.json'
    budget.write_text(json.dumps(config(max_total_cost='1.3').public()))
    credentials = tmp_path / 'local.env'
    credentials.write_text(f'OPENAI_API_KEY=synthetic-not-secret\nOPENAI_BASE_URL=http://127.0.0.1:{server.server_port}/v1\n')
    try:
        process, report, invocation = launch(tmp_path, '--mode', 'live', '--cases',
            'parse-upload-stable-identity,followup-result-replay', '--config', str(budget), '--env-file', str(credentials))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert process.returncode == 2
    assert len(sent) == 1
    assert report['counts'] == {'pass':0, 'fail':0, 'incomplete':1, 'not_run':1}
    assert all(row['error_code'] == 'budget_exhausted' for row in report['results'])
    ledger = json.loads((invocation / 'budget.json').read_text())
    assert len(ledger['calls']) == 1
    assert next(iter(ledger['calls'].values()))['reserved_cost'] == '1.21970880'
    assert len(list(invocation.glob('state/*/eval.sqlite'))) == 1


def test_source_oracle_counts_business_units_instead_of_http_format_retries():
    from evals.task_verifiers import verify_task
    # Both sources changed after a successful response; an earlier format retry is not a third business unit.
    case = {'id':'source-deleted-or-reassigned'}
    output = {'mode':'live', 'subject_run_ids':['one','two'], 'coverage':{'mutations':['delete_jd','reassign_resume']},
              'model_calls':[{'task':'evaluate_match'}] * 3, 'business_calls':[{'task':'evaluate_match'}] * 2}
    data = {'runs':[{'id':rid,'user_id':1,'status':'failed','session_id':rid,'result_json':None} for rid in ('one','two')],
            'sessions':[{'id':rid,'active_run_id':None} for rid in ('one','two')], 'operations':[], 'events':[], 'match_results':[]}
    assert verify_task(case, output, data)['passed']


def test_http_failure_cannot_claim_source_ownership_fault_was_exercised(tmp_path):
    result, wire = run_local(tmp_path, 'source-deleted-or-reassigned', fail=True, total='10')
    assert result['status'] == 'fail'
    assert result['output']['coverage']['mutations'] == []
    assert len(wire) == result['cost']['unknown_usage_calls'] == 3
    assert result['error_code'] == 'source_fault_not_exercised'
    assert not result['verdict']['passed']


def test_provider_failure_cannot_claim_sql_rollback_was_injected(tmp_path):
    result, wire = run_local(tmp_path, 'business-write-rollback', total='50', fail_after=1)
    assert result['status'] == 'fail'
    assert result['output']['coverage']['fault_kinds'] == []
    assert not next(check for check in result['verdict']['checks'] if check['name']=='four_write_boundaries')['passed']
    assert len(wire) == 13  # One actual setup match, then three HTTP attempts for each of four tasks.
