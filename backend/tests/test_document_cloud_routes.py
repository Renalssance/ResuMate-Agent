from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.db.database import Base
from backend.db.models import Resume, User
from backend.routes import documents as routes
from backend.services.documents import PageText, StoredUpload


@pytest.fixture
def document_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'documents.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(username="cloud-documents", password_hash="hash")
        db.add(user)
        db.commit()
        yield db, user
    engine.dispose()


@pytest.fixture
def rag_store(monkeypatch):
    class FakeRagStore:
        def replace_document_chunks(self, **kwargs):
            pass

        def delete_document(self, **kwargs):
            pass

    monkeypatch.setattr(routes, "get_rag_store", FakeRagStore)


def test_reparse_preserves_cloud_reference(document_db, monkeypatch, rag_store):
    db, user = document_db
    reference = "cloud://test-env.default-bucket/documents/123/简历.txt"
    row = Resume(user_id=user.id, filename="简历.txt", file_path=reference, raw_text="old content", structured_data={})
    db.add(row)
    db.commit()
    received_paths = []

    def extract(path, filename, **kwargs):
        received_paths.append(path)
        return [PageText(page_number=1, text="Candidate resume original cloud content.")]

    monkeypatch.setattr(routes, "extract_stored_pages", extract)
    monkeypatch.setattr(routes, "_parse_profile", lambda *args: {"candidate_name": "Ada"})
    result = routes.reparse_document(f"resume:{row.id}", task_id="cloud-reparse", current_user=user, db=db)

    assert received_paths == [reference]
    assert result.raw_text == "Candidate resume original cloud content."
    assert db.get(Resume, row.id).file_path == reference


def _prepared_upload(tmp_path, monkeypatch):
    scratch = tmp_path / "resume.txt"
    scratch.write_text("Candidate resume original cloud content.")
    reference = "cloud://test-env.default-bucket/documents/123/resume.txt"
    stored = StoredUpload("resume.txt", scratch, scratch.stat().st_size, "test-content-hash", reference)
    monkeypatch.setattr(routes.anyio.from_thread, "run", lambda *args: stored)
    return scratch, reference


def test_upload_persists_cloud_reference_and_removes_scratch(document_db, tmp_path, monkeypatch, rag_store):
    db, user = document_db
    scratch, reference = _prepared_upload(tmp_path, monkeypatch)
    monkeypatch.setattr(routes, "_parse_profile", lambda *args: {"candidate_name": "Ada"})

    result = routes.upload_documents(
        document_type="resume", files=[UploadFile(filename="resume.txt", file=BytesIO())],
        task_id="cloud-upload", current_user=user, db=db,
    )

    row = db.get(Resume, int(result.documents[0].id.partition(":")[2]))
    assert row.file_path == reference
    assert row.raw_text == "Candidate resume original cloud content."
    assert not scratch.exists()


def test_failed_upload_deletes_cloud_original_and_scratch(document_db, tmp_path, monkeypatch, rag_store):
    db, user = document_db
    scratch, reference = _prepared_upload(tmp_path, monkeypatch)
    deleted = []

    def parse(*args):
        raise ValueError("profile extraction failed")

    monkeypatch.setattr(routes, "_parse_profile", parse)
    monkeypatch.setattr(routes, "delete_stored_file", deleted.append)
    with pytest.raises(HTTPException, match="profile extraction failed"):
        routes.upload_documents(
            document_type="resume", files=[UploadFile(filename="resume.txt", file=BytesIO())],
            task_id="cloud-failed-upload", current_user=user, db=db,
        )

    assert deleted == [reference]
    assert not scratch.exists()
    assert db.query(Resume).count() == 0
