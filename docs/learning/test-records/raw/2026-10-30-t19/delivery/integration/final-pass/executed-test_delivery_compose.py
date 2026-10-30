"""Opt-in fresh production image: readiness, PDF, offline backup and checkpoint restore."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from uuid import uuid4
import httpx
from jose import jwt
import pytest
from backend.tests.resume_pdf_fixture import inspect_pdf

pytestmark = pytest.mark.skipif(os.getenv('RESUMATE_DELIVERY_INTEGRATION') != '1', reason='Explicit fresh-image delivery test required')
DOCKER = shutil.which('docker') or '/Applications/Docker.app/Contents/Resources/bin/docker'


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def wait(read, accept, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = read()
        if accept(value): return value
        time.sleep(.25)
    pytest.fail(f'Timed out: {value}')


def test_fresh_images_and_offline_backup_resume_waiting_checkpoint():
    root = Path(__file__).resolve().parents[2]
    source = Path(os.environ['RESUMATE_DELIVERY_SOURCE'])
    artifacts = Path('/tmp') / ('task-19-artifacts-' + uuid4().hex)
    artifacts.mkdir()
    os.chmod(artifacts, 0o700)
    shutil.copy2(__file__, artifacts / 'executed-test_delivery_compose.py')
    print('T19 evidence:', artifacts, flush=True)
    projects = ['resumate-t19-source-' + uuid4().hex[:8], 'resumate-t19-restore-' + uuid4().hex[:8]]
    secret = uuid4().hex
    evidence = {'source': str(source), 'backend_image': os.environ['RESUMATE_BACKEND_IMAGE'],
        'frontend_image': os.environ['RESUMATE_FRONTEND_IMAGE'], 'executed': False, 'projects': projects}
    def save(): (artifacts / 'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    save()
    override = artifacts / 'test-override.yaml'
    override.write_text(f'''services:
  api:
    volumes: ["{source / 'backend/tests'}:/app/backend/tests:ro"]
  api2:
    volumes: ["{source / 'backend/tests'}:/app/backend/tests:ro"]
  worker:
    volumes: ["{source / 'backend/tests'}:/app/backend/tests:ro"]
    command: [celery, -A, 'backend.tests.fixtures.delivery:app', worker, --loglevel=INFO, --concurrency=1]
''')
    commands, envfiles, clients = [], [], []
    compose_env = os.environ.copy()
    for project in projects:
        port, api, api2 = free_port(), free_port(), free_port()
        env = artifacts / (project + '.env')
        configuration = {
            'MYSQL_PASSWORD': uuid4().hex, 'MYSQL_ROOT_PASSWORD': uuid4().hex, 'JWT_SECRET_KEY': secret,
            'RESUMATE_WEB_PORT': port, 'RESUMATE_API_PORT': api, 'RESUMATE_API2_PORT': api2,
            'RESUMATE_ENV': project, 'RESUMATE_BACKEND_IMAGE': evidence['backend_image'],
            'RESUMATE_FRONTEND_IMAGE': evidence['frontend_image']}
        env.write_text('\n'.join(f'{k}={v}' for k, v in configuration.items()) + '\n')
        # Compose shell values override --env-file; keep each isolated file authoritative.
        for key in configuration:
            compose_env.pop(key, None)
        env.chmod(0o600)
        envfiles.append(env)
        commands.append([DOCKER, 'compose', '--env-file', str(env), '-p', project,
                         '-f', str(source / 'deploy/compose.yaml'), '-f', str(override)])
        clients.append(httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=15,
            headers={'Authorization': 'Bearer ' + jwt.encode({'sub': 'delivery-user', 'role': 'user', 'exp': int(time.time()) + 3600}, secret, algorithm='HS256')}))
    def command(index, *args, check=True, timeout=180):
        result = subprocess.run(commands[index] + list(args), capture_output=True, text=True, timeout=timeout, env=compose_env)
        with (artifacts / 'commands.txt').open('a') as out:
            out.write(json.dumps({'project': projects[index], 'args': args, 'code': result.returncode}) + '\n')
            out.write(result.stdout + result.stderr + '\n')
        if check: assert result.returncode == 0, result.stderr[-2000:]
        return result
    def fixture(index, mode, rid=None):
        result = command(index, 'exec', '-T', 'worker', 'python', '-m', 'backend.tests.fixtures.delivery', mode, *([rid] if rid else []))
        return json.loads(result.stdout.strip().splitlines()[-1])
    def snapshot(index, rid):
        response = clients[index].get('/api/agent/runs/' + rid)
        assert response.status_code == 200, response.text
        return response.json()
    def archive_command(index, mode):
        result = subprocess.run([sys.executable, str(source / 'deploy/backup.py'), mode, str(artifacts / 'backup'),
            '--project', projects[index], '--env-file', str(envfiles[index]), '-f', str(override)],
            capture_output=True, text=True, timeout=300, env=compose_env)
        (artifacts / (mode + '.txt')).write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stderr[-2000:]
    try:
        command(0, 'up', '-d', '--no-build', '--wait')
        evidence['executed'] = True
        save()
        fixture(0, 'seed')
        for dependency in ('redis', 'mysql'):
            command(0, 'stop', dependency)
            status = wait(lambda: clients[0].get('/readyz').status_code, lambda code: code == 503, 20)
            assert clients[0].get('/healthz').status_code == 200
            evidence.setdefault('readiness_down', {})[dependency] = status
            command(0, 'up', '-d', '--no-build', '--wait', dependency)
            wait(lambda: clients[0].get('/readyz').status_code, lambda code: code == 200, 30)
        response = clients[0].post('/api/resume-versions/delivery-confirmed/export', json={'requestId': 'delivery-pdf'})
        assert response.status_code == 202, response.text
        pdf_run = response.json()['runId']
        assert wait(lambda: snapshot(0, pdf_run), lambda s: s['status'] in ('succeeded', 'failed'))['status'] == 'succeeded'
        pdf = clients[0].get(f'/api/agent/runs/{pdf_run}/download')
        assert pdf.status_code == 200
        path = artifacts / 'production-resume.pdf'
        path.write_bytes(pdf.content)
        inspect_pdf(path, artifacts / 'pdf-pages')
        response = clients[0].post('/api/agent/runs', json={'kind': 'tailoring', 'resumeId': 1, 'jdId': 1, 'requestId': 'backup-waiting'})
        assert response.status_code == 202, response.text
        rid = response.json()['runId']
        pending = wait(lambda: snapshot(0, rid), lambda s: s['status'] in ('waiting_input', 'failed'))
        assert pending['status'] == 'waiting_input'
        before = fixture(0, 'inspect', rid)
        before_files = fixture(0, 'files')
        assert before['checkpoint']['interrupts'] and before['versions'] == 0
        archive_command(0, 'backup')
        archive_command(1, 'restore')
        restored = snapshot(1, rid)
        after = fixture(1, 'inspect', rid)
        assert restored['status'] == 'waiting_input'
        assert after['checkpoint'] == before['checkpoint']
        assert after['actions'] == before['actions'] and after['events'] == before['events']
        assert fixture(1, 'files') == before_files
        assert clients[1].get(f'/api/agent/runs/{pdf_run}/download').content == pdf.content
        action = restored['actions'][0]
        response = clients[1].post(f"/api/agent/runs/{rid}/actions/{action['actionId']}",
            json={'decision': 'submit', 'answers': {'role': '负责 API 和数据库设计'}, 'expectedRevision': action['revision']})
        assert response.status_code == 202, response.text
        assert wait(lambda: snapshot(1, rid), lambda s: s['status'] in ('succeeded', 'failed'))['status'] == 'succeeded'
        final = fixture(1, 'inspect', rid)
        assert final['versions'] == final['operations'] == 1
        assert sum(e['type'] == 'artifact.created' for e in final['events']) == 1
        assert final['checkpoint']['run_id'] == rid and not final['checkpoint']['next']
        evidence.update(status='pass', run_id=rid, before=before, restored=after, final=final,
                        files=before_files, pdf_run_id=pdf_run)
        save()
    finally:
        for index in range(2):
            logs = command(index, 'logs', '--no-color', check=False, timeout=30)
            (artifacts / (projects[index] + '-services.txt')).write_text(logs.stdout + logs.stderr)
            command(index, 'down', '--volumes', '--remove-orphans', check=False, timeout=90)
            clients[index].close()
        evidence['completed'] = True
        save()
