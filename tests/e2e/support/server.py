"""Own one disposable SQL/checkpoint store, Redis, real API/worker and Vite.

Run through Playwright. Docker and the repository .venv are prerequisites. Only
Redis is containerized: API and worker use the same host SQLite implementation.
No production route, queue or persistence implementation is replaced.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
STATE = Path(os.environ.get('RESUMATE_E2E_ROOT') or tempfile.mkdtemp(prefix='resumate-e2e-'))
STATE.mkdir(parents=True, exist_ok=True)
PYTHON = str(ROOT / '.venv/bin/python')
API = 'http://127.0.0.1:4174'
USER = 'browser-fixture'
PASSWORD = 'synthetic-browser-password'
children = []
logs = []
container_id = None
stopping = False


def stop(_signum, _frame):
    global stopping
    stopping = True


def start(command, env, name):
    log = (STATE / f'{name}.log').open('w')
    logs.append(log)
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log,
                               stderr=subprocess.STDOUT, start_new_session=True)
    children.append(process)
    return process


def wait_for(predicate, description, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and not stopping:
        if any(child.poll() is not None for child in children):
            raise RuntimeError(f'A test service exited before {description}; see {STATE}')
        try:
            if predicate():
                return
        except (OSError, ConnectionError):
            pass
        time.sleep(0.1)
    raise RuntimeError(f'Timed out waiting for {description}; see {STATE}')


def main():
    global container_id
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    docker = shutil.which('docker') or '/Applications/Docker.app/Contents/Resources/bin/docker'
    # Refuse to attach to another API accidentally; Vite also uses --strictPort.
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(('127.0.0.1', 4174))
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        redis_port = probe.getsockname()[1]
    env = dict(os.environ, DATABASE_URL=f'sqlite:///{STATE / "resumate.db"}',
               AGENT_STATE_DIR=str(STATE / 'agent'), RESUME_EXPORT_DIR=str(STATE / 'exports'),
               RESUMATE_E2E_ROOT=str(STATE), DOCUMENT_STORAGE_ROOT=str(STATE / 'documents'),
               CHROMA_PATH=str(STATE / 'chroma'),
               JWT_SECRET_KEY=uuid4().hex, RESUMATE_ENV='e2e-' + uuid4().hex,
               REDIS_URL=f'redis://127.0.0.1:{redis_port}/0',
               CLOUDBASE_ENV_ID='', CLOUD_STORAGE_PROVIDER='local',
               LANGSMITH_TRACING='false', LOG_LEVEL='WARNING',
               VITE_API_PROXY_TARGET=API)
    os.environ.update(env)
    import httpx
    import redis
    from backend.db.database import init_db, SessionLocal
    from backend.db.models import User, Resume, JobDescription, UserLlmSettings
    from backend.auth.security import get_password_hash

    init_db()
    with SessionLocal() as db:
        db.add(User(id=1, username=USER, password_hash=get_password_hash(PASSWORD)))
        db.flush()
        db.add_all([
            Resume(id=1, user_id=1, filename='E2E 主简历.txt', parse_status='success',
                   raw_text='在示例项目中负责 API 和数据库设计。', structured_data={
                       'candidate_name': '示例求职者', 'summary': 'API development',
                       'work_experience': [{'company': '示例团队', 'title': 'API 开发',
                                            'description': '负责 API 和数据库设计。',
                                            'source_refs': [{'page_number': 1, 'section': '工作经历',
                                                             'text': '负责 API 和数据库设计。', 'chunk_id': 'e2e-resume-1'}]}]}),
            JobDescription(id=1, user_id=1, title='E2E API 工程师', company='示例团队',
                           parse_status='success', raw_text='负责 API 和数据库设计。', structured_data={'title': 'API 工程师'}),
        ])
        db.add(UserLlmSettings(user_id=1, api_key='synthetic-browser-model-key',
                               base_url='https://model-fixture.invalid/v1', model='browser-deterministic',
                               context_window_tokens=64000, max_tokens=4096))
        db.commit()
    image = os.environ.get('RESUMATE_E2E_REDIS_IMAGE', 'public.ecr.aws/docker/library/redis:7.4-alpine')
    container_id = subprocess.check_output([
        docker, 'run', '--rm', '-d', '-p', f'127.0.0.1:{redis_port}:6379',
        image, 'redis-server', '--save', '', '--appendonly', 'no',
    ], text=True, timeout=60).strip()
    broker = redis.Redis(host='127.0.0.1', port=redis_port, socket_connect_timeout=1)
    def redis_ready():
        try:
            return broker.ping()
        except redis.ConnectionError:
            return False
    wait_for(redis_ready, 'disposable Redis')
    start([PYTHON, '-m', 'uvicorn', 'backend.tests.e2e_api_fixture:app', '--host', '127.0.0.1', '--port', '4174'], env, 'api')
    # Solo avoids macOS fork restrictions while exercising the actual Celery delivery/task.
    worker = start([PYTHON, '-m', 'celery', '-A', 'backend.tests.e2e_worker_fixture:app', 'worker',
           '--pool=solo', '--concurrency=1', '--loglevel=WARNING', '--without-gossip', '--without-mingle'], env, 'worker')
    with httpx.Client(base_url=API, timeout=5) as client:
        def healthy():
            try:
                return client.get('/healthz').status_code == 200
            except httpx.TransportError:
                return False
        wait_for(healthy, 'real API health')
        login = client.post('/auth/login', json={'username': USER, 'password': PASSWORD})
        login.raise_for_status()
        client.headers['Authorization'] = 'Bearer ' + login.json()['access_token']
        response = client.post('/api/agent/runs', json={
            'kind': 'tailoring', 'jdId': 1, 'resumeId': 1, 'requestId': 'demo-paused',
        })
        response.raise_for_status()
        paused_id = response.json()['runId']
        wait_for(lambda: client.get('/api/agent/runs/' + paused_id).json()['status'] == 'waiting_input',
                 'real checkpoint-backed paused Run')
    (STATE / 'fixture.json').write_text(json.dumps({'pausedRunId': paused_id, 'workerPid': worker.pid, 'redisUrl': env['REDIS_URL'], 'redisNamespace': 'resumate:' + env['RESUMATE_ENV']}))
    start(['npm', '--prefix', 'frontend', 'run', 'dev', '--', '--host', '127.0.0.1',
           '--port', '4173', '--strictPort'], env, 'frontend')
    start(['node', 'extension/fixtures/static-server.js'], env, 'extension-fixtures')
    print(f'E2E services ready; isolated SQL/checkpoints/logs: {STATE}', flush=True)
    while not stopping:
        if any(child.poll() is not None for child in children):
            raise RuntimeError(f'A test service exited; see {STATE}')
        time.sleep(0.2)


try:
    main()
finally:
    for child in reversed(children):
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
    for child in reversed(children):
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)
    if container_id:
        docker = shutil.which('docker') or '/Applications/Docker.app/Contents/Resources/bin/docker'
        subprocess.run([docker, 'rm', '-f', container_id], capture_output=True, timeout=15, check=False)
    for log in logs:
        log.close()
    # Keep service logs for diagnosing a failing run, remove all mutable test state.
    for filename in ('fixture.json', 'resumate.db', 'resumate.db-shm', 'resumate.db-wal'):
        (STATE / filename).unlink(missing_ok=True)
    for dirname in ('agent', 'documents', 'chroma', 'exports'):
        shutil.rmtree(STATE / dirname, ignore_errors=True)
