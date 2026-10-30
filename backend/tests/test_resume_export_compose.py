"""Opt-in: actual Linux worker, pinned CJK font, authenticated two-page PDF."""
import os
import shutil
from pathlib import Path
import socket
import subprocess
import time
from uuid import uuid4

import httpx
from jose import jwt
import pytest
from sqlalchemy.orm import Session

from backend.db.database import Base, build_engine
from backend.db.career_models import ResumeVersion
from backend.db.models import User, Resume, JobDescription
from backend.tests.resume_pdf_fixture import chinese_resume_content, inspect_pdf

pytestmark = pytest.mark.skipif(os.getenv('RESUMATE_PDF_COMPOSE_TEST') != '1',
                               reason='Requires explicit Linux PDF integration run')


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def test_linux_worker_exports_extractable_chinese_resume(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    project = 'resumate-pdf-' + uuid4().hex[:8]
    data = tmp_path / 'data'
    data.mkdir()
    evidence = tmp_path / 'pdf-evidence'
    evidence.mkdir()
    # A dependency image may predate this checkout; always exercise the saved current source.
    source = evidence / 'source' / 'backend'
    shutil.copytree(root / 'backend', source,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.pytest_cache'))
    for name in ('pyproject.toml', 'uv.lock'):
        shutil.copy2(root / name, evidence / 'source' / name)
    image = os.getenv('RESUMATE_PDF_BASE_IMAGE', 'resumate-t11-worker')
    secret = uuid4().hex
    port = free_port()
    monkeypatch.setenv('JWT_SECRET_KEY', secret)
    monkeypatch.setenv('RESUMATE_API_PORT', str(port))
    monkeypatch.setenv('RESUMATE_REDIS_PORT', str(free_port()))
    version_id = str(uuid4())
    engine = build_engine(f'sqlite:///{data / "resumate.db"}')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(User(id=1, username='pdf-fixture', password_hash='not-a-login'))
        db.flush()
        db.add_all([Resume(id=1, user_id=1, filename='synthetic.txt', raw_text='原始材料'),
                    JobDescription(id=1, user_id=1, title='全栈工程师', raw_text='接口与页面开发')])
        db.flush()
        db.add(ResumeVersion(id=version_id, user_id=1, resume_id=1, jd_id=1,
                             revision=3, status='confirmed', structured_content=chinese_resume_content()))
        db.commit()
    engine.dispose()  # Native seeding ends before Linux writes SQLite WAL.
    override = tmp_path / 'compose-pdf.yaml'
    override.write_text(f'''services:
  api:
    image: {image}
    volumes: ["{data}:/app/data", "{source}:/app/backend:ro"]
  worker:
    image: {image}
    volumes: ["{data}:/app/data", "{source}:/app/backend:ro"]
''')
    print('PDF dependency image:', image)
    print('PDF current source snapshot:', source)
    command = ['docker', 'compose', '-p', project, '-f', str(root / 'backend/tests/fixtures/compose.sqlite.yaml'), '-f', str(override)]
    token = jwt.encode({'sub': 'pdf-fixture', 'role': 'user'}, secret, algorithm='HS256')
    with httpx.Client(base_url=f'http://127.0.0.1:{port}', headers={'Authorization': 'Bearer ' + token}) as client:
        try:
            subprocess.run(command + ['up', '-d', '--no-build', '--wait', 'api', 'worker'], check=True, timeout=120)
            font = subprocess.run(command + ['exec', '-T', 'worker', 'fc-match', 'Noto Sans CJK SC'],
                                  check=True, capture_output=True, text=True, timeout=15).stdout
            assert 'NotoSansCJK' in font, font
            print('Linux font:', font.strip())
            response = client.post(f'/api/resume-versions/{version_id}/export', json={'requestId': 'linux-pdf'})
            assert response.status_code == 202, response.text
            run_id = response.json()['runId']
            repeated = client.post(f'/api/resume-versions/{version_id}/export', json={'requestId': 'linux-pdf'})
            assert repeated.json()['runId'] == run_id
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                response = client.get('/api/agent/runs/' + run_id)
                response.raise_for_status()
                state = response.json()
                if state['status'] in ('succeeded', 'failed', 'cancelled'):
                    break
                time.sleep(0.25)
            assert state['status'] == 'succeeded', state
            assert state['outputRefs'] == [{'type': 'resume_pdf', 'id': run_id,
                                             'resumeVersionId': version_id, 'revision': 3}]
            response = client.get(f'/api/agent/runs/{run_id}/download')
            assert response.status_code == 200, response.text[:200]
            assert response.headers['content-type'] == 'application/pdf'
            pdf = evidence / 'resume.pdf'
            pdf.write_bytes(response.content)
            inspect_pdf(pdf, evidence)
            unauthorized = httpx.get(f'http://127.0.0.1:{port}/api/agent/runs/{run_id}/download')
            assert unauthorized.status_code == 401
            artifacts = client.get(f'/api/agent/runs/{run_id}/artifacts').json()
            assert artifacts[0]['kind'] == 'resume_pdf'
            print('PASS: actual Linux Celery worker -> pinned Chinese font -> authenticated two-page PDF')
        finally:
            logs = subprocess.run(command + ['logs', '--no-color'], capture_output=True, text=True, timeout=30)
            (evidence / 'compose.log').write_text(logs.stdout + logs.stderr)
            print('PDF evidence:', evidence)
            subprocess.run(command + ['down', '-v', '--remove-orphans'], check=False, timeout=60)
