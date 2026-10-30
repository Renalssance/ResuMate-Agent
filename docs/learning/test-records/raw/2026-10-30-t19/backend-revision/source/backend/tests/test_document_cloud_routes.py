from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.db.agent_models import AgentRun
from backend.db.models import Resume
from backend.routes import documents
from backend.services.documents import StoredUpload
from backend.tests.career_fixtures import career_db, career_engine
from backend.tests.test_document_tasks import parse_app, upload, execute


@pytest.fixture
def cloud_original(parse_app, tmp_path, monkeypatch):
    scratch = tmp_path / 'resume.txt'
    scratch.write_text('Candidate resume original cloud content.')
    reference = 'cloud://test-env.default-bucket/documents/123/resume.txt'
    stored = StoredUpload('resume.txt', scratch, scratch.stat().st_size, 'cloud-hash', reference)
    async def saved(file):
        return stored
    monkeypatch.setattr(documents, 'store_upload', saved)
    downloads, deleted = [], []
    class Storage:
        def download(self, path, destination):
            downloads.append(path)
            Path(destination).write_text('Candidate resume original cloud content.')
        def delete(self, path):
            deleted.append(path)
    from backend.services import documents as service
    monkeypatch.setattr(service.CloudBaseStorage, 'from_env', Storage)
    return scratch, reference, downloads, deleted


def test_upload_removes_cache_but_worker_downloads_persisted_cloud_original(parse_app, cloud_original, monkeypatch):
    client, factory, originals = parse_app
    scratch, reference, downloads, deleted = cloud_original
    run_id = upload(client).json()['taskId']
    assert not scratch.exists()
    execute(factory, run_id, monkeypatch)
    with factory() as db:
        run = db.get(AgentRun, run_id)
        row = db.get(Resume, int(run.input_json['documentId'].split(':')[1]))
        assert run.status == 'succeeded'
        assert row.file_path == reference and row.raw_text == 'Candidate resume original cloud content.'
    assert downloads == [reference] and deleted == []


def test_accepted_failed_upload_retains_cloud_original(parse_app, cloud_original, monkeypatch):
    client, factory, originals = parse_app
    scratch, reference, downloads, deleted = cloud_original
    run_id = upload(client).json()['taskId']
    def fail(*args, **kwargs):
        raise ValueError('profile extraction failed')
    execute(factory, run_id, monkeypatch, parse=fail)
    with factory() as db:
        run = db.get(AgentRun, run_id)
        row = db.get(Resume, int(run.input_json['documentId'].split(':')[1]))
        assert run.status == 'failed' and row.file_path == reference and row.parse_status == 'failed'
    assert not scratch.exists() and deleted == []


def test_preaccept_failure_removes_cloud_original_and_cache(parse_app, cloud_original, monkeypatch):
    client, factory, originals = parse_app
    scratch, reference, downloads, deleted = cloud_original
    def fail(*args, **kwargs):
        raise HTTPException(status_code=400, detail='accept failed')
    monkeypatch.setattr(documents, 'submit_task', fail)
    response = upload(client)
    assert response.status_code == 400
    with factory() as db:
        assert db.query(AgentRun).count() == 0
        assert db.query(Resume).count() == 1  # seeded unrelated resume remains
    assert not scratch.exists() and deleted == [reference]


def test_reparse_preserves_cloud_reference(parse_app, cloud_original, monkeypatch):
    client, factory, originals = parse_app
    scratch, reference, downloads, deleted = cloud_original
    with factory() as db:
        row = db.get(Resume, 1)
        row.file_path, row.filename = reference, 'resume.txt'
        db.commit()
    response = client.post('/api/documents/resume:1/parse', headers={'Prefer': 'respond-async'})
    run_id = response.json()['taskId']
    execute(factory, run_id, monkeypatch)
    with factory() as db:
        assert db.get(Resume, 1).file_path == reference
        assert db.get(AgentRun, run_id).result_json['raw_text'] == 'Candidate resume original cloud content.'
    assert downloads == [reference] and deleted == []
