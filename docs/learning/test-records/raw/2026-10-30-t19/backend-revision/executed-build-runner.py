from pathlib import Path
import json, os, shutil, signal, subprocess, time, uuid

os.environ['PATH'] = '/Applications/Docker.app/Contents/Resources/bin:' + os.environ.get('PATH', '')
repo = Path('/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent')
base_source = Path('/tmp/task-19-build-5cd2b8fd52/source')
base_tag = 'resumate-t19-backend:5cd2b8fd52'
base_id = 'sha256:83629f6b72ea003153d037cb314228ab268dc6f04f05360d05555fa544dd9455'
docker = '/Applications/Docker.app/Contents/Resources/bin/docker'
for name in ('pyproject.toml', 'uv.lock', 'deploy/worker.Dockerfile'):
    assert (repo / name).read_bytes() == (base_source / name).read_bytes(), name + ' changed: cannot reuse dependency image'
base = json.loads(subprocess.check_output([docker, 'image', 'inspect', base_tag], text=True))[0]
assert base['Id'] == base_id
revision_id = uuid.uuid4().hex[:10]
root = Path('/tmp') / ('task-19-backend-revision-' + revision_id)
root.mkdir(mode=0o700)
source = root / 'source'
source.mkdir()
ignore = shutil.ignore_patterns('node_modules', 'dist', '__pycache__', '.pytest_cache', '*.pyc', '.env*')
for name in ('backend', 'deploy', 'evals'):
    shutil.copytree(repo / name, source / name, ignore=ignore)
for name in ('pyproject.toml', 'uv.lock', '.dockerignore'):
    shutil.copy2(repo / name, source / name)
shutil.copy2(__file__, root / 'executed-build-runner.py')
shutil.copy2('/tmp/task-19-model-transport-runtime-probe.py', root / 'runtime-probe.py')
dockerfile = root / 'backend-revision.Dockerfile'
dockerfile.write_text('FROM ' + base_tag + '\nCOPY backend/ /app/backend/\n')
tag = 'resumate-t19-backend:' + revision_id + '-lifecycle'
evidence = dict(kind='backend source revision of previously fresh validated image', base_tag=base_tag,
                base_id=base_id, base_source=str(base_source), source=str(source), image=tag,
                unchanged_dependencies=['pyproject.toml', 'uv.lock', 'deploy/worker.Dockerfile'],
                built=False, runtime_probe_passed=False, initial_free_bytes=shutil.disk_usage('/tmp').free,
                minimum_free_bytes=shutil.disk_usage('/tmp').free, disk_stop_threshold_bytes=2*2**30,
                source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip())

def save():
    (root / 'revision.json').write_text(json.dumps(evidence, indent=2) + '\n')

save()
Path('/tmp/task-19-backend-revision-current.txt').write_text(str(root))
print(root, flush=True)
command = [docker, 'build', '--progress=plain', '-f', str(dockerfile), '-t', tag, str(source)]
(root / 'commands.json').write_text(json.dumps([command], indent=2) + '\n')
with (root / 'backend-build.txt').open('w') as log:
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
    print('backend build exit', process.returncode, flush=True)
    if process.returncode:
        raise SystemExit(1)
inspected = json.loads(subprocess.check_output([docker, 'image', 'inspect', tag], text=True))[0]
evidence['image_metadata'] = {key: inspected[key] for key in ('Id', 'Created', 'Architecture', 'Size')}
probe_command = [docker, 'run', '--rm', '-i', '--entrypoint', 'python', tag, '-']
(root / 'commands.json').write_text(json.dumps([command, probe_command], indent=2) + '\n')
probe = subprocess.run(probe_command, input=(root / 'runtime-probe.py').read_text(), capture_output=True, text=True, timeout=60)
(root / 'runtime-probe.txt').write_text(probe.stdout + probe.stderr)
evidence['runtime_probe_exit_code'] = probe.returncode
if probe.returncode == 0:
    result = json.loads(probe.stdout)
    evidence['runtime_probe_passed'] = result['status'] == 'pass' and len(result['cases']) == 8
    (root / 'runtime-probe.json').write_text(json.dumps(result, indent=2) + '\n')
evidence['final_free_bytes'] = shutil.disk_usage('/tmp').free
save()
print(json.dumps(evidence, indent=2), flush=True)
raise SystemExit(0 if evidence['runtime_probe_passed'] else 1)
