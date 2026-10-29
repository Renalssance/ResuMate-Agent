"""Opt-in real Docker/Redis/worker kill test; every resource belongs to this test."""
import os
from pathlib import Path
import socket
import subprocess
import time
from uuid import uuid4

import pytest
import httpx
from jose import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.db.database import Base, build_engine
from backend.db.models import User, Resume, JobDescription
from backend.db.agent_models import AgentRun, ToolOperation
from backend.db.career_models import ResumeVersion
from backend.schemas.agent_runs import RunCreate, RunStatus
from backend.services import agent_runs

pytestmark = pytest.mark.skipif(os.getenv('RESUMATE_COMPOSE_TEST') != '1', reason='Requires explicit local Docker integration run')


def wait_for(predicate, seconds, description):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(1)
    pytest.fail('Timed out: ' + description)


def test_committed_draft_survives_broker_failure_and_worker_kill(tmp_path, monkeypatch):
    from backend.services.run_delivery import publish_run
    from backend.worker import app
    root = Path(__file__).resolve().parents[2]
    project = 'resumate-test-' + uuid4().hex[:8]
    data = tmp_path / 'data'
    agent_dir = data / 'agent'
    agent_dir.mkdir(parents=True)
    (agent_dir / 'pause_after_commit').touch()
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    broker = f'redis://127.0.0.1:{port}/0'
    monkeypatch.setenv('REDIS_URL', broker)
    monkeypatch.setenv('RESUMATE_REDIS_PORT', str(port))
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        api_port = listener.getsockname()[1]
    monkeypatch.setenv('RESUMATE_API_PORT', str(api_port))
    jwt_secret = uuid4().hex
    monkeypatch.setenv('JWT_SECRET_KEY', jwt_secret)
    token = jwt.encode({'sub': 'compose-test', 'role': 'user'}, jwt_secret, algorithm='HS256')
    client = httpx.Client(base_url=f'http://127.0.0.1:{api_port}', headers={'Authorization': 'Bearer ' + token})
    old_broker = app.conf.broker_url
    app.conf.broker_url = broker
    override = tmp_path / 'compose-test.yaml'
    override.write_text(f'''services:
  api:
    volumes: ["{data}:/app/data"]
  worker:
    volumes: ["{data}:/app/data", "{root / 'backend/tests'}:/app/backend/tests:ro"]
    command: [celery, -A, 'backend.tests.worker_fixture:app', worker, --loglevel=INFO, --concurrency=1]
''')
    command = ['docker', 'compose', '-p', project, '-f', str(root / 'deploy/compose.yaml'), '-f', str(override)]
    engine = build_engine(f'sqlite:///{data / "resumate.db"}')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(User(id=1, username='compose-test', password_hash='not-a-login'))
        db.flush()
        db.add_all([Resume(id=1, user_id=1, filename='synthetic.txt', raw_text='Built an API'),
                    JobDescription(id=1, user_id=1, title='Engineer', raw_text='API development')])
        db.commit()
        run_id = agent_runs.create_run(db, 1, RunCreate(kind='tailoring', jd_id=1, resume_id=1, request_id='compose-request')).id
    engine.dispose()  # Seed before Linux services start; no native reads of live SQLite WAL.
    def snapshot():
        response = client.get('/api/agent/runs/' + run_id)
        response.raise_for_status()
        return response.json()
    def database_record():
        # Read inside the same Linux VM as the writer, not through macOS shared memory.
        script = "import sqlite3,json; c=sqlite3.connect('/app/data/resumate.db'); print(json.dumps({'run':c.execute('select status,attempt,execution_epoch,heartbeat_at from agent_runs').fetchone(),'versions':c.execute('select count(*) from resume_versions').fetchone()[0],'operations':c.execute('select count(*) from tool_operations').fetchone()[0]}))"
        result = subprocess.run(command + ['exec', '-T', 'api', 'python', '-c', script], capture_output=True, text=True, check=True, timeout=10)
        import json
        return json.loads(result.stdout)
    try:
        assert publish_run(run_id) is False  # Port is closed: SQL accepted before broker exists.
        subprocess.run(command + ['up', '-d', '--wait', 'redis'], check=True, timeout=60)
        verify_visibility_timeout(app, run_id)
        subprocess.run(command + ['up', '-d', '--build'], check=True, timeout=300)
        wait_for(lambda: (agent_dir / 'artifact_committed').exists(), 90, 'scanner redispatches and commits artifact')
        assert snapshot()['status'] == 'running'
        assert database_record()['run'][:3] == ['running', 1, 1]
        # Verify the heartbeat advances while an actual task is blocked.
        first_heartbeat = database_record()['run'][3]
        def heartbeat_advanced():
            return database_record()['run'][3] > first_heartbeat
        wait_for(heartbeat_advanced, 20, 'worker heartbeat')
        assert publish_run(run_id) and publish_run(run_id)  # Real duplicate messages.
        subprocess.run(command + ['kill', '-s', 'SIGKILL', 'worker'], check=True, timeout=30)
        (agent_dir / 'pause_after_commit').unlink()
        subprocess.run(command + ['up', '-d', 'worker'], check=True, timeout=60)
        wait_for(lambda: snapshot()['status'] in ('succeeded', 'failed'), 160, '90-second stale recovery')
        record = database_record()
        assert record['run'][:3] == ['succeeded', 2, 2]
        assert record['versions'] == record['operations'] == 1
        assert len(snapshot()['outputRefs']) == 1
        print('PASS: publish failure -> scan; heartbeat; duplicates; SIGKILL after SQL commit -> attempt 2, one artifact')
    finally:
        logs = subprocess.run(command + ['logs', '--no-color'], capture_output=True, text=True, timeout=30)
        (tmp_path / 'compose.log').write_text(logs.stdout + logs.stderr)
        print('Compose evidence:', tmp_path / 'compose.log')
        subprocess.run(command + ['down', '-v', '--remove-orphans'], check=False, timeout=60)
        app.conf.broker_url = old_broker
        client.close()
        engine.dispose()


def verify_visibility_timeout(app, run_id):
    """Exercise the configured Redis transport; age ONLY a disposable test delivery."""
    from queue import Empty
    with app.connection_for_write() as connection:
        queue = connection.SimpleQueue('resumate.visibility.probe')
        try:
            queue.put({'runId': run_id})
            message = queue.get(block=True, timeout=3)
            qos = queue.channel.qos
            assert qos.visibility_timeout == 3600
            qos.restore_visible(interval=1)
            with pytest.raises(Empty):
                queue.get(block=False)
            queue.channel.client.zadd(qos.unacked_index_key, {message.delivery_tag: time.time() - 3601})
            qos.restore_visible(interval=1)
            redelivered = queue.get(block=True, timeout=3)
            assert redelivered.payload == {'runId': run_id}
            assert redelivered.headers['redelivered'] is True
            redelivered.ack()
        finally:
            queue.close()
    print('PASS: Redis visibility_timeout=3600; fresh unacked stays hidden; aged delivery reappears')
