"""Opt-in real MySQL + Redis + two API processes + deterministic Celery worker."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import socket
import re
import tomllib
import subprocess
import time
from uuid import uuid4

import httpx
from jose import jwt
import pytest

pytestmark = [pytest.mark.real_redis, pytest.mark.skipif(
    os.getenv('RESUMATE_REDIS_INTEGRATION') != '1', reason='Explicit Docker Redis integration opt-in required')]
DOCKER = shutil.which('docker') or '/Applications/Docker.app/Contents/Resources/bin/docker'


def now():
    return datetime.now(timezone.utc).isoformat()


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def wait_for(read, condition, timeout=30):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = read()
        if condition(last):
            return last
        time.sleep(.25)
    pytest.fail(f'Timed out waiting for condition; last observation: {last}')


class Stack:
    def __init__(self):
        self.root = Path(__file__).resolve().parents[2]
        self.invocation = uuid4().hex
        self.artifacts = Path('/tmp') / ('task-20-artifacts-' + self.invocation)
        self.artifacts.mkdir()
        source = self.artifacts / 'source'
        shutil.copytree(self.root / 'backend', source / 'backend', ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.pytest_cache'))
        for name in ('pyproject.toml', 'uv.lock', 'compose.redis-integration.yaml'):
            shutil.copy2(self.root / name, source / name)
        shutil.copytree(self.root / 'deploy', source / 'deploy')
        self.project = 'resumate-t20-' + self.invocation[:10]
        self.secret = uuid4().hex
        ports = [free_port(), free_port()]
        self.env = {**os.environ, 'MYSQL_ROOT_PASSWORD': uuid4().hex, 'MYSQL_PASSWORD': uuid4().hex,
                    'JWT_SECRET_KEY': self.secret, 'RESUMATE_ENV': self.project,
                    'RESUMATE_API_PORT': str(ports[0]), 'RESUMATE_API2_PORT': str(ports[1]),
                    'T20_IMAGE': os.getenv('RESUMATE_REDIS_BASE_IMAGE') or self.project + ':test', 'T20_SOURCE': str(source)}
        self.command = [DOCKER, 'compose', '-p', self.project, '-f', str(self.root / 'deploy/compose.yaml'),
                        '-f', str(self.root / 'compose.redis-integration.yaml')]
        self.clients = [httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=20) for port in ports]
        self.evidence = {'invocation_id': self.invocation, 'started_at': now(), 'project': self.project,
                         'image': self.env['T20_IMAGE'], 'executed': False, 'source': str(source),
                         'model': 'existing deterministic DraftModel; no external calls', 'results': []}
        self.save()

    def save(self):
        (self.artifacts / 'evidence.json').write_text(json.dumps(self.evidence, ensure_ascii=False, indent=2))

    def compose(self, *args, timeout=60, check=True):
        result = subprocess.run(self.command + list(args), env=self.env, text=True, capture_output=True, timeout=timeout)
        # Arguments contain no credentials; never archive resolved Compose environment.
        with (self.artifacts / 'commands.txt').open('a') as out:
            out.write(json.dumps({'at': now(), 'args': args, 'exit_code': result.returncode}) + '\n')
            out.write(result.stdout + result.stderr + '\n')
        if check:
            assert result.returncode == 0, f'Compose {args[:2]} failed: {result.stderr[-2000:]}'
        return result

    def redis(self, *args):
        return self.compose('exec', '-T', 'redis', 'redis-cli', '--raw', *map(str, args)).stdout.strip()

    def headers(self, uid=1, expires=None):
        token = jwt.encode({'sub': f'redis-user-{uid}', 'role': 'user', 'exp': expires or int(time.time()) + 3600},
                           self.secret, algorithm='HS256')
        return {'Authorization': 'Bearer ' + token}

    def call(self, method, path, *, api=0, uid=1, **kwargs):
        return self.clients[api].request(method, path, headers=kwargs.pop('headers', self.headers(uid)), **kwargs)

    def get(self, path, **kwargs):
        response = self.call('GET', path, **kwargs)
        assert response.status_code == 200, response.text
        return response.json()

    def post(self, path, **kwargs):
        response = self.call('POST', path, **kwargs)
        assert response.status_code in (200, 202), response.text
        return response.json()

    @contextmanager
    def case(self, name):
        record = {'case_id': name, 'started_at': now(), 'executed': True, 'status': 'fail', 'observed': {}}
        self.evidence['results'].append(record)
        self.save()
        try:
            yield record['observed']
            record['status'] = 'pass'
        finally:
            record['completed_at'] = now()
            self.save()


@pytest.fixture(scope='module')
def stack():
    value = Stack()
    print('T20 artifact directory:', value.artifacts, flush=True)
    try:
        # Current dependency lock and application source are built once for all five services.
        if os.getenv('RESUMATE_REDIS_BASE_IMAGE'):
            result = subprocess.run([DOCKER, 'run', '--rm', '--entrypoint', 'python', value.env['T20_IMAGE'], '-c',
                "import importlib.metadata,json;print(json.dumps({d.metadata['Name']:d.version for d in importlib.metadata.distributions()}))"],
                capture_output=True, text=True, timeout=60)
            assert result.returncode == 0, result.stderr
            runtime = json.loads(result.stdout)
            normalized = lambda name: re.sub('[-_.]+', '-', name).lower()
            installed = {normalized(name): version for name, version in runtime.items()}
            locked = {normalized(row['name']): row['version'] for row in tomllib.loads((value.root / 'uv.lock').read_text())['package']}
            mismatches = {name: version for name, version in installed.items() if name in locked and version != locked[name]}
            direct = tomllib.loads((value.root / 'pyproject.toml').read_text())['project']['dependencies']
            missing = [requirement for requirement in direct if normalized(re.match(r'[A-Za-z0-9_.-]+', requirement).group()) not in installed]
            (value.artifacts / 'runtime-packages.json').write_text(json.dumps(runtime, indent=2))
            verification = {'missing_direct_dependencies': missing, 'lock_version_differences': mismatches}
            (value.artifacts / 'runtime-verification.json').write_text(json.dumps(verification, indent=2))
            assert not missing and not mismatches, verification
            assert installed['redis'] == '6.4.0'
            value.evidence['dependency_image_reuse'] = {'image': value.env['T20_IMAGE'], 'full_backend_mount': '/app/backend',
                'current_lock_installed_versions_match': True, 'new_dockerfile_build_succeeded': False}
            value.save()
        else:
            value.compose('build', 'api', timeout=1200)
        value.compose('up', '-d', '--no-build', '--wait', timeout=240)
        value.post('/__redis_test/seed')
        value.evidence['executed'] = True
        value.save()
        yield value
    finally:
        value.compose('logs', '--no-color', timeout=30, check=False)
        value.compose('--profile', 'oom', 'down', '--volumes', '--remove-orphans', timeout=90, check=False)
        value.evidence['completed_at'] = now()
        value.save()
        for client in value.clients:
            client.close()


def test_topology_shared_sql_and_worker_only_checkpoints(stack):
    with stack.case('topology') as observed:
        first = stack.get('/__redis_test/topology')
        second = stack.get('/__redis_test/topology', api=1)
        observed.update(api1=first, api2=second)
        assert first['hostname'] != second['hostname']
        assert first['database'] == second['database'] == 'resumate'
        assert first['users'] == second['users'] == list(range(1, 8))
        assert first['mysql'].startswith('8.4') and first['redis'].startswith('7.4')
        assert first['redisPy'] == second['redisPy'] == '6.4.0'
        assert first['namespace'] == second['namespace'] == 'resumate:' + stack.project
        assert first['config']['maxmemory-policy'] == 'noeviction'
        assert not first['agentStateVisible'] and not second['agentStateVisible']
        worker = stack.compose('exec', '-T', 'worker', 'python', '-c',
            "import json; from pathlib import Path; from backend.worker_tasks import execution_lock; "
            "\nwith execution_lock() as acquired: print(json.dumps({'lock':acquired,'directory':Path('/app/agent-state').exists()}))")
        observed['worker'] = json.loads(worker.stdout)
        assert observed['worker'] == {'lock': True, 'directory': True}
        stack.evidence['topology'] = observed


def test_rate_limit_is_atomic_across_apis_and_ttl_does_not_slide(stack):
    with stack.case('rate-limit') as observed:
        with ThreadPoolExecutor(max_workers=20) as executor:
            responses = list(executor.map(lambda n: stack.call('POST', '/__redis_test/rate/run', api=n % 2, uid=3), range(20)))
        statuses = [r.status_code for r in responses]
        observed['statuses'] = statuses
        assert statuses.count(200) == statuses.count(429) == 10
        assert all(int(r.headers['Retry-After']) >= 1 for r in responses if r.status_code == 429)
        key = f'resumate:{stack.project}:rl:run:3'
        before = int(stack.redis('PTTL', key))
        time.sleep(1.05)
        assert stack.call('POST', '/__redis_test/rate/run', uid=3).status_code == 429
        after = int(stack.redis('PTTL', key))
        observed['ttlMs'] = [before, after]
        assert 0 < after < before - 900
        assert stack.call('POST', '/__redis_test/rate/run', uid=4).status_code == 200
        assert stack.call('POST', '/__redis_test/rate/chat', uid=3).status_code == 200
        statuses = [stack.call('POST', '/auth/login', api=n % 2,
                    headers={'X-Forwarded-For': '203.0.113.20'},
                    json={'username': 'no-such-test-user', 'password': 'synthetic'}).status_code for n in range(6)]
        observed['authStatuses'] = statuses
        assert statuses == [401] * 5 + [429]


def test_ticket_single_consumer_and_expiration_across_apis(stack):
    with stack.case('ticket') as observed:
        expiry = int(time.time()) + 120
        issued = stack.post('/__redis_test/tickets/interview-1', headers=stack.headers(expires=expiry),
                            json={'userId': 2, 'authExpiresAt': '2099-01-01'})
        assert 29000 <= issued['ttlMs'] <= 30000
        with ThreadPoolExecutor(max_workers=2) as executor:
            claims = list(executor.map(lambda api: stack.post('/__redis_test/consume', api=api,
                                            json={'ticket': issued['ticket']}), (0, 1)))
        accepted = [value for value in claims if value is not None]
        observed.update(consumedCount=len(accepted), claims=accepted, ttlMs=issued['ttlMs'])
        assert len(accepted) == 1
        assert accepted[0] == {'userId': 1, 'interviewId': 'interview-1', 'authExpiresAt': issued['authExpiresAt']}
        assert stack.post('/__redis_test/consume', json={'ticket': issued['ticket']}) is None
        assert stack.call('POST', '/__redis_test/tickets/interview-1', uid=2).status_code == 404
        short = stack.post('/__redis_test/tickets/interview-1', headers=stack.headers(expires=int(time.time()) + 2))
        time.sleep(2.1)
        assert stack.post('/__redis_test/consume', api=1, json={'ticket': short['ticket']}) is None
        assert stack.call('POST', '/__redis_test/tickets/interview-1', headers=stack.headers(expires=int(time.time()) - 1)).status_code == 401
        no_exp = jwt.encode({'sub': 'redis-user-1'}, stack.secret, algorithm='HS256')
        assert stack.call('POST', '/__redis_test/tickets/interview-1', headers={'Authorization': 'Bearer ' + no_exp}).status_code == 401
        observed['expiredTicket'] = None


def test_cache_reduces_aggregates_and_real_worker_invalidates(stack):
    with stack.case('cache') as observed:
        before = [stack.get('/__redis_test/counts', api=api) for api in (0, 1)]
        responses = [stack.get('/api/settings/usage', api=n % 2) for n in range(20)]
        after = [stack.get('/__redis_test/counts', api=api) for api in (0, 1)]
        delta = {key: sum(a[key] - b[key] for a, b in zip(after, before)) for key in before[0]}
        observed['twentyGetsSql'] = delta
        assert delta['aggregate'] == 3 and delta['recent'] == 20
        assert all(r['total_calls'] == 1 and r['total_tokens'] == 10 for r in responses)
        other = stack.get('/api/settings/usage', uid=2)
        assert other['total_calls'] == 1 and other['total_tokens'] == 20
        key = f'resumate:{stack.project}:stats:1'
        assert stack.redis('EXISTS', key) == '1'
        stack.post('/__redis_test/usage')
        wait_for(lambda: stack.get('/__redis_test/state')['tables']['llm_usage_events'], lambda n: n == 3)
        assert stack.redis('EXISTS', key) == '0'
        updated = stack.get('/api/settings/usage', api=1)
        assert updated['total_calls'] == 2 and updated['total_tokens'] == 35
        assert updated['recent_calls'][0]['task'] == 'real-worker-fixture'
        observed['afterWorker'] = {'calls': updated['total_calls'], 'tokens': updated['total_tokens'], 'cacheDeleted': True}
        ttl = int(stack.redis('PTTL', key))
        assert 0 < ttl <= 30000
        before = stack.get('/__redis_test/counts')
        time.sleep(ttl / 1000 + .1)
        assert stack.get('/api/settings/usage')['total_calls'] == 2
        after = stack.get('/__redis_test/counts')
        assert after['aggregate'] - before['aggregate'] == 3
        observed['ttlExpiryAggregateSql'] = 3


def test_notifications_wake_then_sql_fills_missing_and_duplicate_hints(stack):
    with stack.case('notifications') as observed, ThreadPoolExecutor(max_workers=1) as executor:
        def consumer(after, count=1):
            return stack.post('/__redis_test/consumer/interview-1', api=1, json={'after': after, 'count': count})
        future = executor.submit(consumer, 0)
        wait_for(lambda: stack.get('/__redis_test/consumers', api=1), lambda names: 'interview-1' in names)
        started = time.monotonic()
        stack.post('/__redis_test/events/interview-1/1', json={})
        normal = future.result(timeout=4)
        observed['normalElapsed'] = time.monotonic() - started
        assert [e['seq'] for e in normal['events']] == [1]
        assert observed['normalElapsed'] < 1.5  # Below the 2 s SQL fallback: the hint actually woke this consumer.
        stack.post('/__redis_test/reader/stop', api=1)
        future = executor.submit(consumer, 1)
        wait_for(lambda: stack.get('/__redis_test/consumers', api=1), lambda names: 'interview-1' in names)
        started = time.monotonic()
        stack.post('/__redis_test/events/interview-1/2', json={'publish': False})
        missing = future.result(timeout=4)
        observed['missingHintElapsed'] = time.monotonic() - started
        assert [e['seq'] for e in missing['events']] == [2]
        assert observed['missingHintElapsed'] <= 3
        stack.post('/__redis_test/reader/start', api=1)
        future = executor.submit(consumer, 2, 2)
        wait_for(lambda: stack.get('/__redis_test/consumers', api=1), lambda names: 'interview-1' in names)
        stack.post('/__redis_test/events/interview-1/3', json={})
        for _ in range(3):
            stack.post('/__redis_test/hint/interview-1/3')
        stack.post('/__redis_test/events/interview-1/4', json={})
        assert [e['seq'] for e in future.result(timeout=4)['events']] == [3, 4]
        assert stack.call('POST', '/__redis_test/consumer/interview-1', uid=2, json={'after': 0}).status_code == 404
        observed['seq'] = [1, 2, 3, 4]


def test_redis_down_rejects_admission_but_committed_run_recovers(stack):
    from backend.tests.test_rate_limit_routes import ACCEPTANCES
    with stack.case('down-restart-recovery') as observed, ThreadPoolExecutor(max_workers=1) as executor:
        usage_before = stack.get('/api/settings/usage')
        stack.compose('stop', '-t', '5', 'worker', 'scheduler')
        stack.post('/__redis_test/barrier/arm')
        future = executor.submit(stack.call, 'POST', '/api/agent/runs', json={
            'kind': 'tailoring', 'resumeId': 1, 'jdId': 1, 'requestId': 'publish-gap-' + stack.invocation})
        barrier = wait_for(lambda: stack.post('/__redis_test/barrier/status'), lambda b: b['reached'])
        run_id = barrier['runId']
        before = stack.get('/__redis_test/run/' + run_id, api=1)
        assert before['status'] == 'queued' and before['executionEpoch'] == 0
        observed['before'] = before
        stack.compose('stop', '-t', '2', 'redis')
        try:
            stack.post('/__redis_test/barrier/release')
            accepted = future.result(timeout=20)
            assert accepted.status_code == 202 and accepted.json()['runId'] == run_id
            observed['acceptedStatus'] = accepted.status_code
            state_before = stack.get('/__redis_test/state')
            denied = [stack.call('POST', path, **kwargs).status_code for path, kwargs in ACCEPTANCES]
            assert denied == [503] * 9
            assert stack.get('/__redis_test/state') == state_before
            observed['admissionStatuses'] = denied
            observed['stateBeforeAfter'] = state_before
            assert stack.call('POST', '/__redis_test/tickets/interview-1').status_code == 503
            assert stack.call('POST', '/__redis_test/consume', json={'ticket': 'synthetic-not-a-ticket'}).status_code == 503
            stack.post('/__redis_test/usage-direct')
            usage = stack.get('/api/settings/usage', api=1)
            assert usage['total_calls'] == usage_before['total_calls'] + 1
            assert usage['total_tokens'] == usage_before['total_tokens'] + 9
            observed['downUsage'] = {'calls': usage['total_calls'], 'tokens': usage['total_tokens']}
            assert stack.call('GET', '/api/agent/runs/' + run_id).status_code == 200
            assert stack.call('POST', '/api/agent/runs/run-cancel/cancel').status_code == 202
            assert stack.call('POST', '/api/agent/runs/run-action/actions/action-action',
                              json={'decision': 'reject', 'answers': {}, 'expectedRevision': 1}).status_code == 202
            stack.post('/__redis_test/events/interview-1/5', json={'publish': False})
            events = stack.post('/__redis_test/consumer/interview-1', api=1, json={'after': 4})
            assert [e['seq'] for e in events['events']] == [5]
        finally:
            stack.compose('start', 'redis')
            wait_for(lambda: stack.redis('PING'), lambda result: result == 'PONG')
            stack.compose('start', 'worker', 'scheduler')
        after = wait_for(lambda: stack.get('/__redis_test/run/' + run_id),
                         lambda run: run['status'] in ('succeeded', 'failed'), timeout=90)
        observed['after'] = after
        assert after['status'] == 'succeeded'
        assert after['attempt'] == after['executionEpoch'] == after['versions'] == after['operations'] == 1
        assert len([e for e in after['events'] if e['type'] == 'run.status' and e['payload'].get('status') == 'succeeded']) == 1
        checkpoint = stack.compose('exec', '-T', 'worker', 'python', '-c',
            "import json; from langgraph.checkpoint.sqlite import SqliteSaver; "
            "\nwith SqliteSaver.from_conn_string('/app/agent-state/checkpoints.sqlite') as saver: "
            f"print(json.dumps({{'exists':saver.get_tuple({{'configurable':{{'thread_id':{after['sessionId']!r}}}}}) is not None}}))")
        observed['checkpoint'] = json.loads(checkpoint.stdout)
        assert observed['checkpoint']['exists']
        issued = stack.post('/__redis_test/tickets/interview-1', api=1)
        assert stack.post('/__redis_test/consume', json={'ticket': issued['ticket']})['userId'] == 1
        with ThreadPoolExecutor(max_workers=20) as workers:
            statuses = list(workers.map(lambda n: stack.call('POST', '/__redis_test/rate/run', uid=7, api=n % 2).status_code, range(20)))
        assert statuses.count(200) == statuses.count(429) == 10
        observed['postRestartRateStatuses'] = statuses
        # AOF may retain cache/counters/tickets; wait for stats' documented bound before asserting refreshed summary.
        key = f'resumate:{stack.project}:stats:1'
        remaining = int(stack.redis('PTTL', key))
        if remaining > 0:
            time.sleep(remaining / 1000 + .1)
        assert stack.get('/api/settings/usage')['total_calls'] == usage_before['total_calls'] + 1
        with ThreadPoolExecutor(max_workers=1) as workers:
            next_event = workers.submit(stack.post, '/__redis_test/consumer/interview-1', api=1, json={'after': 5})
            wait_for(lambda: stack.get('/__redis_test/consumers', api=1), lambda names: 'interview-1' in names)
            stack.post('/__redis_test/events/interview-1/6', json={})
            assert [e['seq'] for e in next_event.result(timeout=4)['events']] == [6]


def test_oom_noeviction_preserves_marker_and_services_fail_as_designed(stack):
    with stack.case('oom') as observed:
        expected_calls = stack.get('/api/settings/usage')['total_calls']
        stack.compose('--profile', 'oom', 'up', '-d', 'redis-oom', timeout=60)
        result = stack.compose('exec', '-T', 'api', 'python', '-m', 'backend.tests.fixtures.redis_oom', timeout=60)
        # The script's stdout is redacted JSON only; warning logs remain in stderr evidence.
        observed.update(json.loads(result.stdout))
        assert observed['markerPresent'] and observed['policy'] == 'noeviction'
        assert observed['limiterUnavailable'] and observed['ticketUnavailable']
        assert observed['cacheCalls'] == expected_calls
        assert 'redis_capacity_high' in result.stderr
