"""Run the existing real E2E stack behind the shipped nginx configuration."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
STATE = Path(os.environ['RESUMATE_E2E_ROOT'])
STATE.mkdir(parents=True, exist_ok=True)
DOCKER = shutil.which('docker') or '/Applications/Docker.app/Contents/Resources/bin/docker'
NAME = 'resumate-production-browser-' + uuid4().hex[:10]
IMAGE = os.environ.get('RESUMATE_E2E_NGINX_IMAGE', 'nginx:stable-alpine')
stop_requested = False


def stop(_signum, _frame):
    global stop_requested
    stop_requested = True


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
env = dict(os.environ, RESUMATE_E2E_API_HOST='0.0.0.0')
api_port = env['RESUMATE_E2E_API_PORT']
port = env['RESUMATE_PRODUCTION_PORT']
config = (ROOT / 'deploy/nginx.conf').read_text()
for host in ('api', 'api2'):
    config = config.replace(f'server {host}:8000;', f'server host.docker.internal:{api_port};')
(STATE / 'nginx.conf').write_text(config)
shutil.copytree(ROOT / 'frontend/dist', STATE / 'dist')
(STATE / 'environment.json').write_text(json.dumps({
    'invocation_id': NAME, 'nginx_image': IMAGE,
    'frontend': 'production dist copy', 'api': 'real FastAPI + SQLite',
    'worker': 'real Celery solo + SDK graph + deterministic external models',
    'redis': 'disposable real Redis', 'ports': {'api': api_port, 'nginx': port},
    'nginx_change': 'only replace api/api2 upstream addresses with host.docker.internal',
}))
log = (STATE / 'service-launcher.log').open('w')
server = subprocess.Popen([sys.executable, 'tests/e2e/support/server.py'], cwd=ROOT,
                          env=env, stdout=log, stderr=subprocess.STDOUT,
                          start_new_session=True)
container_started = False
try:
    deadline = time.monotonic() + 80
    while not (STATE / 'fixture.json').exists():
        if server.poll() is not None or stop_requested or time.monotonic() >= deadline:
            raise RuntimeError(f'Real E2E services failed to start; see {STATE}')
        time.sleep(.1)
    result = subprocess.run([
        DOCKER, 'run', '--rm', '-d', '--name', NAME,
        '-p', f'127.0.0.1:{port}:80',
        *(['--add-host', 'host.docker.internal:host-gateway'] if sys.platform.startswith('linux') else []),
        '-v', f'{STATE / "nginx.conf"}:/etc/nginx/conf.d/default.conf:ro',
        '-v', f'{STATE / "dist"}:/usr/share/nginx/html:ro',
        IMAGE,
    ], capture_output=True, text=True, timeout=45)
    (STATE / 'nginx-start.txt').write_text(result.stdout + result.stderr)
    result.check_returncode()
    container_started = True
    print(f'Production browser services: http://127.0.0.1:{port}; evidence: {STATE}', flush=True)
    while not stop_requested:
        if server.poll() is not None:
            raise RuntimeError(f'Real E2E services stopped; see {STATE}')
        time.sleep(.2)
finally:
    if container_started:
        result = subprocess.run([DOCKER, 'logs', NAME], capture_output=True, text=True, timeout=15)
        (STATE / 'nginx.log').write_text(result.stdout + result.stderr)
        subprocess.run([DOCKER, 'rm', '-f', NAME], capture_output=True, timeout=15, check=False)
    if server.poll() is None:
        os.killpg(server.pid, signal.SIGTERM)
    try:
        server.wait(timeout=25)
    except subprocess.TimeoutExpired:
        os.killpg(server.pid, signal.SIGKILL)
        server.wait(timeout=5)
    log.close()
