"""Opt-in isolated MySQL/dual-API load experiment; no model/provider calls.

Host: python tests/load/api_sse.py --output /tmp/task-17-baseline --source-ref cdde2c5
Driver runs in the same Docker VM as the commit clock. Source is captured before startup.
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time
import tomllib
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
RUN_IDS = [f'load-run-{n:02}' for n in range(10)]


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def summarize_api(samples):
    def stats(rows):
        durations = [row['elapsed_ms'] for row in rows]
        return {'samples': len(rows), 'p50_ms': percentile(durations, .5), 'p95_ms': percentile(durations, .95),
                'max_ms': max(durations, default=None), 'errors': sum(not row['valid'] or row['status'] != 200 for row in rows),
                'statuses': dict(Counter(str(row['status']) for row in rows))}
    groups = {name: stats([row for row in samples if row['endpoint'] == name]) for name in sorted({r['endpoint'] for r in samples})}
    overall = stats(samples)
    return {'overall': overall, 'endpoints': groups,
            'passed': bool(samples) and all(value['errors'] == 0 and value['p95_ms'] <= 300 for value in groups.values())}


def summarize_delivery(commits, receives, subscribers):
    committed = {(row['run_id'], row['seq']): row['committed_ns'] for row in commits}
    expected = {(sid, run, seq) for sid, watched in subscribers.items() for run, seq in committed if watched == run}
    counts = Counter((row['subscriber'], row['run_id'], row['seq']) for row in receives if (row['run_id'], row['seq']) in committed)
    delays = [(row['received_ns'] - committed[row['run_id'], row['seq']]) / 1e6 for row in receives if (row['run_id'], row['seq']) in committed]
    missing = len(expected - counts.keys())
    duplicates = sum(max(0, n - 1) for n in counts.values())
    unexpected = len(counts.keys() - expected)
    p95 = percentile(delays, .95)
    latest, out_of_order = {}, 0
    for row in receives:
        key = row['subscriber'], row['run_id']
        if (row['run_id'], row['seq']) not in committed:
            continue
        if row['seq'] < latest.get(key, 0):
            out_of_order += 1
        latest[key] = max(row['seq'], latest.get(key, 0))
    return {'commits': len(commits), 'expected': len(expected), 'received': len(delays), 'missing': missing,
            'duplicates': duplicates, 'unexpected': unexpected, 'out_of_order': out_of_order, 'p50_ms': percentile(delays, .5), 'p95_ms': p95,
            'max_ms': max(delays, default=None), 'negative_clock_samples': sum(d < 0 for d in delays),
            'passed': bool(expected) and not (missing or duplicates or unexpected or out_of_order) and p95 <= 1000 and min(delays) >= 0}


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def jsonlines(path, rows):
    Path(path).write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))


async def drive(args):
    import httpx
    from jose import jwt
    out = args.output
    bases = args.bases.split(',')
    token = jwt.encode({'sub': 'load-user', 'exp': int(time.time()) + 7200}, os.environ['JWT_SECRET_KEY'], algorithm='HS256')
    headers = {'Authorization': 'Bearer ' + token}
    timeout = httpx.Timeout(10, read=30)
    clients = [httpx.AsyncClient(base_url=base, headers=headers, timeout=timeout, limits=httpx.Limits(max_connections=80, max_keepalive_connections=40)) for base in bases]
    control_clients = [httpx.AsyncClient(base_url=base, headers=headers, timeout=timeout) for base in args.controls.split(',')]
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'executed': True, 'model_calls': 0,
              'clock': 'Linux CLOCK_MONOTONIC shared by Docker VM processes', 'phases': {},
              'business_base_urls': bases, 'control_base_urls': args.controls.split(',')}
    receives, stream_errors, metrics = [], [], []
    streams, ready = {}, {}
    subscribers = {sid: RUN_IDS[sid % 10] for sid in range(30)}

    async def observe():
        for api, client in enumerate(control_clients):
            response = await client.get('/__load/metrics')
            response.raise_for_status()
            metrics.append({'at_ns': time.monotonic_ns(), 'api': api, **response.json()})

    async def stream(sid, after, *, api=None, slow=False):
        run = subscribers[sid]
        client = clients[(sid % len(clients)) if api is None else api]
        event_name, lines = '', []
        try:
            async with client.stream('GET', f'/api/agent/runs/{run}/events?after={after}') as response:
                response.raise_for_status()
                ready[sid].set()
                async for line in response.aiter_lines():
                    if slow:
                        await asyncio.sleep(.08)
                    if line.startswith('event: '):
                        event_name = line[7:]
                    elif line.startswith('data: '):
                        lines.append(line[6:])
                    elif line == '':
                        if event_name == 'run.event' and lines:
                            value = json.loads('\n'.join(lines))
                            receives.append({'subscriber': sid, 'run_id': value['runId'], 'seq': value['seq'],
                                             'received_ns': time.monotonic_ns()})
                        event_name, lines = '', []
        except asyncio.CancelledError:
            raise
        except Exception as error:
            stream_errors.append({'subscriber': sid, 'type': type(error).__name__})
            ready[sid].set()

    async def start(sid, after, **kwargs):
        ready[sid] = asyncio.Event()
        streams[sid] = asyncio.create_task(stream(sid, after, **kwargs))
        await asyncio.wait_for(ready[sid].wait(), 15)

    async def stop(sid):
        task = streams.pop(sid, None)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    endpoints = [('jobs_first', '/api/jobs?limit=20&offset=0'),
                 ('jobs_search', '/api/jobs?query=API&limit=20&offset=0'),
                 ('jobs_deep', '/api/jobs?limit=20&offset=8000'),
                 ('job_detail', '/api/jobs/5000'),
                 ('run_snapshot', '/api/agent/runs/load-run-00')]

    async def api_phase(name):
        rows = []
        async def request(worker, index, measured):
            endpoint, path = endpoints[index % len(endpoints)]
            started = time.monotonic_ns()
            status, valid, error = 0, False, None
            try:
                response = await clients[worker % len(clients)].get(path)
                status = response.status_code
                body = response.json()
                valid = status == 200 and (len(body.get('items', [])) == 20 if endpoint.startswith('jobs_') else
                    body.get('id') == 5000 and bool(body.get('text')) if endpoint == 'job_detail' else body.get('runId') == 'load-run-00')
            except Exception as cause:
                error = type(cause).__name__
            if measured:
                rows.append({'worker': worker, 'endpoint': endpoint, 'status': status, 'valid': valid,
                             'error_type': error, 'elapsed_ms': (time.monotonic_ns() - started) / 1e6})
        async def lane(worker):
            index = worker
            deadline = time.monotonic() + args.warmup
            while time.monotonic() < deadline:
                await request(worker, index, False); index += 1
            deadline = time.monotonic() + args.duration
            while time.monotonic() < deadline:
                await request(worker, index, True); index += 1
        phase_started = time.monotonic()
        await asyncio.gather(*(lane(n) for n in range(20)))
        measured_seconds = time.monotonic() - phase_started - args.warmup
        jsonlines(out / f'{name}-api.jsonl', rows)
        result = summarize_api(rows)
        result.update(concurrency=20, warmup_seconds=args.warmup, duration_seconds=args.duration,
                      observed_measurement_seconds=measured_seconds, requests_per_second=len(rows) / measured_seconds)
        report['phases'][name] = result
        write(out / 'report.json', report)
        print(name, json.dumps(result['overall']), flush=True)

    async def append(text='new load event'):
        response = await control_clients[0].post('/__load/append', json={'runIds': RUN_IDS, 'text': text})
        response.raise_for_status()
        return response.json()

    try:
        await observe()
        await api_phase('api_only')
        await asyncio.gather(*(start(sid, 5000) for sid in subscribers))
        await observe()
        commits = []
        async def writer():
            for n in range(args.event_seconds):
                commits.extend(await append(f'new live event {n}'))
                await asyncio.sleep(1)
                if n % 5 == 0:
                    await observe()
        await asyncio.gather(api_phase('api_with_30_sse'), writer())
        await asyncio.sleep(1)
        report['sse'] = summarize_delivery(commits, receives, subscribers)
        jsonlines(out / 'sse-commits.jsonl', commits)
        jsonlines(out / 'sse-receives.jsonl', receives)
        # Real TCP connections close; persistent writes continue; reconnect to the other API.
        cursors = {sid: max(row['seq'] for row in receives if row['subscriber'] == sid) for sid in range(6)}
        await asyncio.gather(*(stop(sid) for sid in cursors))
        missed = await append('written while six TCP subscribers disconnected')
        restored_ns = time.monotonic_ns()
        before = len(receives)
        await asyncio.gather(*(start(sid, cursor, api=(sid + 1) % len(clients)) for sid, cursor in cursors.items()))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and len([r for r in receives[before:] if r['subscriber'] in cursors]) < 6:
            await asyncio.sleep(.05)
        replay = [r for r in receives[before:] if r['subscriber'] in cursors]
        recovery = summarize_delivery(missed, replay, {sid: subscribers[sid] for sid in cursors})
        recovery['visible_after_reconnect_ms'] = max((r['received_ns'] - restored_ns) / 1e6 for r in replay) if replay else None
        recovery['passed'] = recovery['missing'] == recovery['duplicates'] == recovery['unexpected'] == recovery['out_of_order'] == 0 and recovery['visible_after_reconnect_ms'] is not None and recovery['visible_after_reconnect_ms'] <= 5000
        report['reconnect'] = recovery
        jsonlines(out / 'reconnect-commits.jsonl', missed); jsonlines(out / 'reconnect-receives.jsonl', replay)
        # One client reads a real 5000-frame backlog slowly. Other 29 remain live.
        await stop(29)
        await start(29, 0, slow=True)
        before = len(receives)
        slow_commits = []
        for n in range(5):
            slow_commits.extend(await append(f'slow-peer test {n}'))
            await asyncio.sleep(1)
            await observe()
        await asyncio.sleep(1)
        fast = [r for r in receives[before:] if r['subscriber'] != 29]
        report['slow_consumer_other_29'] = summarize_delivery(slow_commits, fast, {sid: run for sid, run in subscribers.items() if sid != 29})
        jsonlines(out / 'slow-peer-commits.jsonl', slow_commits); jsonlines(out / 'slow-peer-receives.jsonl', fast)
    finally:
        await asyncio.gather(*(stop(sid) for sid in list(streams)))
        await asyncio.sleep(1)
        await observe()
        jsonlines(out / 'metrics.jsonl', metrics)
        report['metrics_final'] = metrics[-len(control_clients):]
        report['stream_errors'] = stream_errors
        report['completed_at'] = datetime.now(timezone.utc).isoformat()
        report['passed'] = all(item['passed'] for item in report['phases'].values()) and all(report.get(name, {}).get('passed', False) for name in ('sse', 'reconnect', 'slow_consumer_other_29')) and not stream_errors and all(m['checked_out'] == 0 and m.get('streams', 0) == 0 for m in report['metrics_final'])
        write(out / 'report.json', report)
        for client in [*clients, *control_clients]:
            await client.aclose()
    print(json.dumps({key: report[key] for key in ('sse', 'reconnect', 'slow_consumer_other_29', 'passed')}, indent=2), flush=True)
    return 0 if report['passed'] else 1


def free_port():
    with socket.socket() as connection:
        connection.bind(('127.0.0.1', 0))
        return connection.getsockname()[1]


def host(args):
    import tarfile
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    capture_root = args.source_directory.resolve() if args.source_directory else ROOT
    source = output / 'source'
    source.mkdir()
    docker = shutil.which('docker') or '/Applications/Docker.app/Contents/Resources/bin/docker'
    invocation = uuid4().hex
    project = 'resumate-t17-' + invocation[:10]
    env = {**os.environ, 'MYSQL_PASSWORD': uuid4().hex, 'MYSQL_ROOT_PASSWORD': uuid4().hex,
           'JWT_SECRET_KEY': uuid4().hex, 'RESUMATE_ENV': project,
           'RESUMATE_API_PORT': str(free_port()), 'RESUMATE_API2_PORT': str(free_port()),
           'LOAD_IMAGE': args.image, 'LOAD_SOURCE': str(source), 'LOAD_OUTPUT': str(output),
           'LOAD_PROXY_PORT': str(free_port()), 'LOAD_PROXY_IMAGE': 'public.ecr.aws/docker/library/nginx:stable-alpine'}
    if args.source_ref:
        archive = subprocess.run(['git', 'archive', args.source_ref, 'backend', 'deploy', 'pyproject.toml', 'uv.lock'], cwd=ROOT, capture_output=True, check=True).stdout
        import io
        with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
            bundle.extractall(source, filter='data')
    else:
        for folder in ('backend', 'deploy'):
            shutil.copytree(capture_root / folder, source / folder, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.pytest_cache'))
        for name in ('pyproject.toml', 'uv.lock'):
            shutil.copy2(capture_root / name, source / name)
    for name in ('load_api.py', 'load_data.py'):
        shutil.copy2(ROOT / 'backend/tests/fixtures' / name, source / 'backend/tests/fixtures' / name)
    shutil.copytree(ROOT / 'tests/load', source / 'tests/load', ignore=shutil.ignore_patterns('__pycache__'))
    if args.proxy:
        shutil.copytree(capture_root / 'frontend/dist', source / 'frontend/dist')
        shutil.copy2(capture_root / 'deploy/nginx.conf', source / 'deploy/nginx.conf')
    command = [docker, 'compose', '-p', project, '-f', str(source / 'deploy/compose.yaml'), '-f', str(source / 'tests/load/compose.yaml')]
    if args.proxy:
        command += ['--profile', 'proxy']
    def call(*parts, timeout=60, check=True):
        result = subprocess.run(command + list(parts), env=env, capture_output=True, text=True, timeout=timeout)
        with (output / 'commands.txt').open('a') as handle:
            handle.write(json.dumps({'args': parts, 'returncode': result.returncode}) + '\n' + result.stdout + result.stderr + '\n')
        if check and result.returncode:
            raise RuntimeError(f'Compose {parts[:2]} failed: {result.stderr[-1000:]}')
        return result
    evidence = {'invocation': invocation, 'project': project, 'executed': False, 'source_ref': args.source_ref, 'captured_source_directory': str(capture_root),
                'source': str(source), 'model_calls': 0, 'proxy_port': env['LOAD_PROXY_PORT'] if args.proxy else None, 'api_ports': [env['RESUMATE_API_PORT'], env['RESUMATE_API2_PORT']]}
    write(output / 'environment.json', evidence)
    try:
        info = subprocess.run([docker, 'info', '--format', '{{json .NCPU}} {{json .MemTotal}} {{json .ServerVersion}}'], capture_output=True, text=True, check=True).stdout.strip().split(' ', 2)
        evidence['docker'] = {'vcpus': int(info[0]), 'memory_bytes': int(info[1]), 'version': json.loads(info[2])}
        packages = subprocess.run([docker, 'run', '--rm', '--entrypoint', 'python', args.image, '-c', "import importlib.metadata,json;print(json.dumps({d.metadata['Name']:d.version for d in importlib.metadata.distributions()}))"], capture_output=True, text=True, check=True, timeout=60)
        runtime = json.loads(packages.stdout)
        norm = lambda value: re.sub('[-_.]+', '-', value).lower()
        installed = {norm(name): value for name, value in runtime.items()}
        locked = {norm(row['name']): row['version'] for row in tomllib.loads((source / 'uv.lock').read_text())['package']}
        direct = tomllib.loads((source / 'pyproject.toml').read_text())['project']['dependencies']
        differences = {key: value for key, value in installed.items() if key in locked and value != locked[key]}
        missing = [line for line in direct if norm(re.match(r'[A-Za-z0-9_.-]+', line).group()) not in installed]
        write(output / 'runtime-verification.json', {'differences': differences, 'missing': missing, 'installed': runtime})
        if differences or missing:
            raise RuntimeError('Dependency image does not match current source lock')
        if args.proxy and subprocess.run([docker, 'image', 'inspect', env['LOAD_PROXY_IMAGE']], capture_output=True).returncode:
            call('pull', 'proxy', timeout=60)
        call('up', '-d', '--no-build', timeout=60)
        # Separate bounded polls avoid one uninterruptible multi-minute command.
        deadline = time.monotonic() + 90
        while True:
            state = call('ps', '--format', 'json').stdout
            states = [json.loads(line) for line in state.splitlines() if line.strip()]
            healthy = {r['Service'] for r in states if r.get('Health') == 'healthy'}
            if ({'api', 'api2', 'mysql', 'redis', 'proxy'} if args.proxy else {'api', 'api2', 'mysql', 'redis'}) <= healthy:
                break
            if time.monotonic() > deadline:
                raise RuntimeError('Load services failed to become healthy')
            time.sleep(2)
        rows = json.loads(call('exec', '-T', 'api', 'python', '-m', 'backend.tests.fixtures.load_data', timeout=60).stdout)
        write(output / 'data.json', rows)
        assert rows['counts']['job_descriptions'] == 10000 and rows['counts']['agent_run_events'] == 50000
        ids = call('ps', '-q').stdout.split()
        inspected = json.loads(subprocess.run([docker, 'inspect', *ids], capture_output=True, text=True, check=True).stdout)
        evidence['containers'] = [{'name': row['Name'], 'memory': row['HostConfig']['Memory'], 'cpuset': row['HostConfig']['CpusetCpus']} for row in inspected]
        evidence['steady_product_memory_limit_bytes'] = sum(row['memory'] for row in evidence['containers'])
        evidence['driver_memory_limit_bytes'] = 512 * 1024**2
        evidence['executed'] = True
        write(output / 'environment.json', evidence)
        driver = call('--profile', 'load', 'run', '-d', '--no-deps', 'driver', 'python', '/app/tests/load/api_sse.py', '--inside', '--output', '/load-output', '--duration', str(args.duration), '--warmup', str(args.warmup), '--event-seconds', str(args.event_seconds), '--bases', 'http://proxy:80' if args.proxy else args.bases, '--controls', args.controls).stdout.strip()
        driver_info = json.loads(subprocess.run([docker, 'inspect', driver], capture_output=True, text=True, check=True).stdout)[0]
        evidence['driver'] = {'memory': driver_info['HostConfig']['Memory'], 'cpuset': driver_info['HostConfig']['CpusetCpus']}
        assert all(row['cpuset'] == '0-3' for row in [*evidence['containers'], evidence['driver']])
        assert evidence['steady_product_memory_limit_bytes'] + evidence['driver']['memory'] <= 7.5 * 1024**3
        if args.proxy:
            evidence['nginx'] = call('exec', '-T', 'proxy', 'nginx', '-v').stderr.strip()
        write(output / 'environment.json', evidence)
        print('Load project', project, 'artifact', output, 'driver', driver, flush=True)
        while True:
            status = subprocess.run([docker, 'inspect', '-f', '{{json .State}}', driver], capture_output=True, text=True, check=True)
            current = json.loads(status.stdout)
            if not current['Running']:
                evidence['driver_exit_code'] = current['ExitCode']
                break
            stats = subprocess.run([docker, 'stats', '--no-stream', '--format', '{{json .}}', *ids, driver], capture_output=True, text=True, timeout=15)
            with (output / 'docker-stats.jsonl').open('a') as log:
                log.write(stats.stdout)
            time.sleep(3)
        log = subprocess.run([docker, 'logs', driver], capture_output=True, text=True)
        (output / 'driver.txt').write_text(log.stdout + log.stderr)
        print(log.stdout + log.stderr, flush=True)
        if args.keep_stack:
            # Private mode-only launcher state supports a deliberate later stop, not saved public evidence.
            private = Path('/tmp') / f'{project}-private.json'
            private.write_text(json.dumps({key: env[key] for key in ('MYSQL_PASSWORD', 'MYSQL_ROOT_PASSWORD', 'JWT_SECRET_KEY', 'RESUMATE_ENV', 'RESUMATE_API_PORT', 'RESUMATE_API2_PORT', 'LOAD_IMAGE', 'LOAD_SOURCE', 'LOAD_OUTPUT', 'LOAD_PROXY_PORT', 'LOAD_PROXY_IMAGE')})); private.chmod(0o600)
            evidence['kept_running'] = True
            evidence['private_cleanup_state'] = str(private)
        return evidence['driver_exit_code']
    finally:
        call('logs', '--no-color', timeout=30, check=False)
        if not args.keep_stack:
            call('--profile', 'load', 'down', '--volumes', '--remove-orphans', timeout=60, check=False)
        write(output / 'environment.json', evidence)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inside', action='store_true')
    parser.add_argument('--proxy', action='store_true')
    parser.add_argument('--controls', default='http://api:8000,http://api2:8000')
    parser.add_argument('--source-ref')
    parser.add_argument('--source-directory', type=Path)
    parser.add_argument('--image', default='resumate-t20-deps:aligned')
    parser.add_argument('--bases', default='http://api:8000,http://api2:8000')
    parser.add_argument('--duration', type=int, default=60)
    parser.add_argument('--warmup', type=int, default=10)
    parser.add_argument('--event-seconds', type=int, default=30)
    parser.add_argument('--keep-stack', action='store_true')
    args = parser.parse_args()
    return asyncio.run(drive(args)) if args.inside else host(args)

if __name__ == '__main__':
    raise SystemExit(main())
