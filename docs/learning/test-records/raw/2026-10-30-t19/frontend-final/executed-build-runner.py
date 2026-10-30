from pathlib import Path
import json, os, shutil, signal, subprocess, time, uuid

os.environ['PATH'] = '/Applications/Docker.app/Contents/Resources/bin:' + os.environ.get('PATH', '')
repo = Path('/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent')
docker = '/Applications/Docker.app/Contents/Resources/bin/docker'
revision_id = uuid.uuid4().hex[:10]
root = Path('/tmp') / ('task-19-frontend-final-' + revision_id)
root.mkdir(mode=0o700)
source = root / 'source'
source.mkdir()
ignore = shutil.ignore_patterns('node_modules', 'dist', '__pycache__', '.pytest_cache', '*.pyc', '.env*')
shutil.copytree(repo / 'frontend', source / 'frontend', ignore=ignore)
(source / 'deploy').mkdir()
for name in ('deploy/frontend.Dockerfile', 'deploy/nginx.conf', '.dockerignore'):
    shutil.copy2(repo / name, source / name)
shutil.copy2(__file__, root / 'executed-build-runner.py')
tag = 'resumate-t19-frontend:' + revision_id + '-terminal'
evidence = dict(kind='full production frontend Dockerfile build with final terminal-state fix',
                source=str(source), image=tag, built=False,
                previous_image='resumate-t19-frontend:5cd2b8fd52',
                backend_image='resumate-t19-backend:7a3122655a-lifecycle',
                initial_free_bytes=shutil.disk_usage('/tmp').free,
                minimum_free_bytes=shutil.disk_usage('/tmp').free, disk_stop_threshold_bytes=2*2**30,
                source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip())

def save():
    (root / 'build.json').write_text(json.dumps(evidence, indent=2) + '\n')

save()
Path('/tmp/task-19-frontend-final-current.txt').write_text(str(root))
print(root, flush=True)
command = [docker, 'build', '--progress=plain', '-f', str(source / 'deploy/frontend.Dockerfile'), '-t', tag, str(source)]
(root / 'commands.json').write_text(json.dumps([command], indent=2) + '\n')
with (root / 'frontend-build.txt').open('w') as log:
    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    while process.poll() is None:
        free = shutil.disk_usage('/tmp').free
        evidence['minimum_free_bytes'] = min(evidence['minimum_free_bytes'], free)
        if free < evidence['disk_stop_threshold_bytes']:
            evidence['stopped_for_disk_space'] = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            break
        time.sleep(1)
    evidence['build_exit_code'] = process.returncode
    evidence['built'] = process.returncode == 0
    save()
    print('frontend build exit', process.returncode, flush=True)
    if process.returncode:
        raise SystemExit(1)
inspected = json.loads(subprocess.check_output([docker, 'image', 'inspect', tag], text=True))[0]
evidence['image_metadata'] = {key: inspected[key] for key in ('Id', 'Created', 'Architecture', 'Size')}
evidence['final_free_bytes'] = shutil.disk_usage('/tmp').free
save()
print(json.dumps(evidence, indent=2), flush=True)

# Verify only the updated static-serving artifact; API readiness was tested
# separately with the real Compose dependencies during delivery acceptance.
import re
from urllib.request import urlopen
from urllib.error import URLError
container_name = 'resumate-t19-frontend-probe-' + revision_id
start_command = [docker, 'run', '--detach', '--name', container_name,
                 '--add-host', 'api:127.0.0.1', '--add-host', 'api2:127.0.0.1',
                 '--publish', '127.0.0.1::80', tag]
commands = [command, start_command]
probe = {'status': 'pending', 'container_name': container_name, 'api_dependencies': 'test-only local host mappings; no API request'}
try:
    subprocess.run(start_command, capture_output=True, text=True, check=True)
    port_command = [docker, 'port', container_name, '80/tcp']
    commands.append(port_command)
    address = subprocess.check_output(port_command, text=True).strip()
    base_url = 'http://' + address
    deadline = time.monotonic() + 20
    while True:
        try:
            with urlopen(base_url + '/', timeout=2) as response:
                body = response.read().decode()
                probe['index_status'] = response.status
                probe['csp'] = response.headers.get('Content-Security-Policy')
                probe['content_type_options'] = response.headers.get('X-Content-Type-Options')
            break
        except (URLError, TimeoutError, ConnectionError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.2)
    assets = re.findall(r'(?:src|href)="(/assets/[^"?]+)"', body)
    assert probe['index_status'] == 200 and assets
    assert "default-src 'self'" in probe['csp'] and probe['content_type_options'] == 'nosniff'
    probe['assets'] = []
    for asset in assets:
        with urlopen(base_url + asset, timeout=5) as response:
            content = response.read()
            assert response.status == 200 and len(content) > 0
            probe['assets'].append({'path': asset, 'status': response.status, 'bytes': len(content)})
    probe['status'] = 'pass'
finally:
    logs = subprocess.run([docker, 'logs', container_name], capture_output=True, text=True)
    (root / 'nginx-runtime.txt').write_text(logs.stdout + logs.stderr)
    cleanup_command = [docker, 'rm', '--force', container_name]
    commands.append(cleanup_command)
    cleanup = subprocess.run(cleanup_command, capture_output=True, text=True)
    probe['cleanup_exit_code'] = cleanup.returncode
    (root / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    (root / 'runtime-probe.json').write_text(json.dumps(probe, indent=2) + '\n')
    evidence['static_runtime_passed'] = probe['status'] == 'pass'
    evidence['probe_cleanup_exit_code'] = cleanup.returncode
    save()
print(json.dumps(probe, indent=2), flush=True)
