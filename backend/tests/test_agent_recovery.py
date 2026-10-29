"""Four opt-in real Docker/Redis/SIGKILL experiments with invocation-bound evidence."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import tempfile
from uuid import uuid4

import httpx
from jose import jwt
import pytest
from sqlalchemy.orm import Session

from backend.db.database import Base, build_engine
from backend.db.models import JobDescription, Resume, User
from backend.schemas.agent_runs import RunCreate
from backend.services import agent_runs

pytestmark = pytest.mark.skipif(os.getenv('RESUMATE_COMPOSE_TEST') != '1',
                               reason='Requires explicit local Docker integration run')
CASE_IDS = ['recovery-model-before-return', 'recovery-draft-after-commit',
            'recovery-checkpoint-before-terminal', 'recovery-answer-before-delivery']
DOCKER = '/Applications/Docker.app/Contents/Resources/bin/docker'


def now():
    return datetime.now(timezone.utc).isoformat()


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def wait_for(predicate, seconds, label):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(1)
    pytest.fail('Timed out: ' + label)


@pytest.fixture(scope='module')
def recovery_context():
    context_path = os.getenv('RESUMATE_RECOVERY_CONTEXT')
    assert context_path, 'Set RESUMATE_RECOVERY_CONTEXT to the current eval invocation context'
    context = json.loads(Path(context_path).read_text())
    assert set(item['id'] for item in context['cases']) == set(CASE_IDS)
    root = Path(__file__).resolve().parents[2]
    # Integration evidence must outlive other pytest sessions' retention cleanup.
    artifacts = Path(tempfile.mkdtemp(prefix='task-14-recovery-artifacts-' + context['invocation_id'][:8] + '-', dir='/tmp'))
    shutil.copy2(context_path, artifacts / 'eval-context.json')
    snapshot = artifacts / 'source'
    shutil.copytree(root / 'backend', snapshot / 'backend',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.pytest_cache'))
    evidence_path = Path(os.getenv('RESUMATE_RECOVERY_EVIDENCE', '/tmp/task-14-recovery-evidence.json'))
    evidence = {'invocation_id': context['invocation_id'], 'started_at': now(),
                'artifact_archive_root': str(artifacts),
                'source': {'base_commit': '26d1a35', 'backend_snapshot_path': str(snapshot / 'backend'),
                           'mount': '/app/backend', 'image': 'resumate-t11-worker:latest',
                           'description': 'Current backend source copied once before all four cases; image supplies dependencies only'},
                'results': []}
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    yield context, root, snapshot, artifacts, evidence, evidence_path
    evidence['completed_at'] = now()
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    shutil.copy2(evidence_path, artifacts / 'evidence.json')


@pytest.mark.parametrize('case_id', CASE_IDS, ids=CASE_IDS)
def test_real_process_kill_recovers_durable_state(recovery_context, case_id):
    context, root, snapshot_root, artifacts, evidence, evidence_path = recovery_context
    inputs = next(case['input'] for case in context['cases'] if case['id'] == case_id)
    case_dir = artifacts / case_id
    state = case_dir / 'data' / 'agent'
    state.mkdir(parents=True)
    (state / 'hold').touch()
    project = 'resumate-recovery-' + uuid4().hex[:10]
    api_port, redis_port = free_port(), free_port()
    secret = uuid4().hex
    env = {**os.environ, 'JWT_SECRET_KEY': secret, 'RESUMATE_API_PORT': str(api_port),
           'RESUMATE_REDIS_PORT': str(redis_port)}
    token = jwt.encode({'sub': 'compose-recovery', 'role': 'user'}, secret, algorithm='HS256')
    client = httpx.Client(base_url=f'http://127.0.0.1:{api_port}', timeout=15,
                         headers={'Authorization': 'Bearer ' + token})
    override = case_dir / 'compose.yaml'
    services = {}
    for service in ('api', 'worker', 'scheduler'):
        services[service] = {'image': 'resumate-t11-worker:latest',
                             'volumes': [f'{case_dir / "data"}:/app/data',
                                         f'{snapshot_root / "backend"}:/app/backend:ro'],
                             'environment': {'AGENT_STATE_DIR': '/app/data/agent',
                                             'RESUMATE_RECOVERY_POINT': case_id,
                                             'LANGCHAIN_TRACING_V2': 'false'}}
    services['api']['command'] = ['uvicorn', 'backend.tests.recovery_api_fixture:app', '--host', '0.0.0.0', '--port', '8000']
    services['worker']['command'] = ['celery', '-A', 'backend.tests.recovery_worker_fixture:app', 'worker', '--loglevel=INFO', '--concurrency=1']
    # JSON is valid YAML, keeping generated paths and strings unambiguous.
    override.write_text(json.dumps({'services': services}, indent=2))
    command = [DOCKER, 'compose', '-p', project, '-f', str(root / 'deploy/compose.yaml'), '-f', str(override)]
    command_log = case_dir / 'commands.log'

    def compose(*args, timeout=60, check=True):
        completed = subprocess.run(command + list(args), env=env, capture_output=True, text=True, timeout=timeout)
        with command_log.open('a') as handle:
            handle.write(json.dumps({'at': now(), 'command': list(args), 'exit_code': completed.returncode}) + '\n')
            handle.write(completed.stdout + completed.stderr + '\n')
        if check and completed.returncode:
            pytest.fail(f'Compose {args[0]} failed: {completed.stderr[-2000:]}')
        return completed

    engine = build_engine(f'sqlite:///{case_dir / "data" / "resumate.db"}')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(User(id=1, username='compose-recovery', password_hash='not-a-login'))
        db.flush()
        db.add_all([Resume(id=1, user_id=1, **inputs['resume']), JobDescription(id=1, user_id=1, **inputs['job'])])
        db.commit()
        run_id = agent_runs.create_run(db, 1, RunCreate(kind=inputs['kind'], jdId=1, resumeId=1,
                                                       requestId=context['invocation_id'] + ':' + case_id)).id
    engine.dispose()  # No native SQL access after Linux writers start.
    record = {'invocation_id': context['invocation_id'], 'case_id': case_id, 'input': inputs,
              'executed': False, 'status': 'fail', 'started_at': now(), 'project': project,
              'run_id': run_id, 'observed': {}, 'artifacts': []}
    evidence['results'].append(record)
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    answer_executor = None
    try:
        compose('up', '-d', '--no-build', '--wait', timeout=150)

        def snapshot():
            response = client.get('/api/agent/runs/' + run_id)
            response.raise_for_status()
            return response.json()

        def inspect_state(label):
            script = ('import json; from backend.tests.recovery_worker_fixture import inspect_recovery; '
                      f'print(json.dumps(inspect_recovery({run_id!r}), ensure_ascii=False))')
            completed = compose('exec', '-T', 'api', 'python', '-c', script, timeout=30)
            value = json.loads(completed.stdout)
            destination = case_dir / f'{label}.json'
            destination.write_text(json.dumps(value, ensure_ascii=False, indent=2))
            record['artifacts'].append(str(destination))
            return value

        action_id = None
        if case_id == 'recovery-answer-before-delivery':
            wait_for(lambda: snapshot()['status'] == 'waiting_input', 90, 'real graph input interrupt')
            waiting = inspect_state('waiting-input')
            assert len(waiting['actions']) == 1 and waiting['actions'][0]['status'] == 'pending'
            action_id = waiting['actions'][0]['id']
            compose('stop', '-t', '5', 'worker')
            answer_executor = ThreadPoolExecutor(max_workers=1)
            def answer():
                try:
                    return client.post(f'/api/agent/runs/{run_id}/actions/{action_id}',
                        json={'decision': 'submit', 'answers': inputs['answer'], 'expectedRevision': 1}, timeout=60).status_code
                except httpx.HTTPError as error:
                    return type(error).__name__
            answer_future = answer_executor.submit(answer)
        wait_for(lambda: (state / 'barrier.json').exists(), 90, 'test-only crash barrier ' + case_id)
        barrier = json.loads((state / 'barrier.json').read_text())
        assert barrier['point'] == case_id
        before = inspect_state('before-kill')
        record['observed'].update(barrier=barrier, before=before,
            run_before={**before['run'], 'execution_epoch': before['run']['epoch']},
            model_starts_before=len(before['model_starts']), checkpoint_before=before['checkpoint'])
        assert before['run']['epoch'] == 1 and before['run']['attempt'] == 1
        if case_id == 'recovery-model-before-return':
            assert before['run']['status'] == 'running'
            assert len(before['model_starts']) == 1 and before['versions'] == before['operations'] == []
        elif case_id == 'recovery-draft-after-commit':
            assert before['run']['status'] == 'running'
            assert len(before['versions']) == len(before['operations']) == 1
            assert before['versions'][0]['id'] == barrier['version_id']
        elif case_id == 'recovery-checkpoint-before-terminal':
            assert before['run']['status'] == 'running'
            assert before['checkpoint']['run_id'] == run_id
            assert before['checkpoint']['next'] == before['checkpoint']['interrupts'] == []
            assert len(before['versions']) == 1
        else:
            assert before['run']['status'] == 'queued'
            assert before['actions'] == [{**before['actions'][0], 'id': action_id,
                                         'status': 'answered', 'response': {'decision': 'submit', 'answers': inputs['answer']}}]
            assert before['checkpoint']['interrupts']
        killed_service = 'api' if case_id == 'recovery-answer-before-delivery' else 'worker'
        container_id = compose('ps', '-a', '-q', killed_service).stdout.strip()
        compose('kill', '-s', 'SIGKILL', killed_service, timeout=30)
        killed = subprocess.run([DOCKER, 'inspect', '--format', '{{json .State}}', container_id],
                                env=env, capture_output=True, text=True, check=True, timeout=10)
        killed_state = json.loads(killed.stdout)
        assert not killed_state['Running'] and killed_state['ExitCode'] == 137
        record['executed'] = True
        record['observed'].update(kill_signal='SIGKILL', killed_service=killed_service,
                                   killed_container=container_id, killed_state=killed_state, killed_at=now())
        if answer_executor:
            record['observed']['interrupted_http_result'] = answer_future.result(timeout=10)
            assert record['observed']['interrupted_http_result'] != 202
        (state / 'hold').unlink()
        compose('up', '-d', '--no-build', '--wait', *(['api', 'worker'] if killed_service == 'api' else ['worker']), timeout=90)
        wait_for(lambda: snapshot()['status'] in ('succeeded', 'failed'), 170, 'scanner and real recovery finish')
        after = inspect_state('after-recovery')
        record['observed'].update(after=after, completed_at=now(),
            run_after={**after['run'], 'execution_epoch': after['run']['epoch']},
            model_starts_after=len(after['model_starts']),
            version_ids=[row['id'] for row in after['versions']], operation_rows=after['operations'],
            action_rows=after['actions'], checkpoint=after['checkpoint'], events=after['events'],
            killed_live_equivalent_usage='unknown; deterministic fixture start counts do not establish paid-provider usage')
        assert after['run']['status'] == 'succeeded'
        assert after['run']['epoch'] == 2
        assert after['run']['attempt'] == (1 if killed_service == 'api' else 2)
        assert len(after['versions']) == len(after['operations']) == len(after['run']['output_refs']) == 1
        assert after['operations'][0]['status'] == 'succeeded'
        assert after['operations'][0]['result_ref'] == after['versions'][0]['id']
        assert after['checkpoint']['run_id'] == run_id
        assert after['checkpoint']['next'] == after['checkpoint']['interrupts'] == []
        events = after['events']
        assert [event['seq'] for event in events] == list(range(1, len(events) + 1))
        assert sum(event['type'] == 'artifact.created' for event in events) == 1
        assert sum(event['type'] == 'run.status' and event['payload']['status'] == 'succeeded' for event in events) == 1
        if case_id == 'recovery-model-before-return':
            assert len(after['model_starts']) > len(before['model_starts'])
            assert sum(start['phase'] == [] for start in after['model_starts']) == 2
        if case_id in ('recovery-draft-after-commit', 'recovery-checkpoint-before-terminal'):
            assert after['versions'] == before['versions'] and after['operations'] == before['operations']
        if case_id == 'recovery-checkpoint-before-terminal':
            assert after['model_starts'] == before['model_starts']
        if case_id == 'recovery-answer-before-delivery':
            assert after['actions'] == before['actions']
            assert any(ref.get('actionId') == action_id for ref in after['versions'][0]['fact_refs'])
        record['status'] = 'pass'
        print(f'{case_id}: PASS, attempt={after["run"]["attempt"]}, epoch=2, model starts={len(before["model_starts"])}->{len(after["model_starts"])}, one operation/version/artifact')
    except BaseException as error:
        record['error'] = str(error)
        raise
    finally:
        logs = compose('logs', '--no-color', timeout=30, check=False)
        log_path = case_dir / 'compose.log'
        log_path.write_text(logs.stdout + logs.stderr)
        record['artifacts'].extend([str(log_path), str(command_log), str(override)])
        compose('down', '-v', '--remove-orphans', timeout=60, check=False)
        record['completed_at'] = now()
        evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
        client.close()
        if answer_executor:
            answer_executor.shutdown(wait=True)
        print('Recovery evidence:', case_dir)
