from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from fastapi import UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.db.database import Base
from backend.db.models import User
from backend.routes import documents as document_routes
from backend.routes.documents import upload_documents
from backend.services.documents import PageText


def _upload(filename: str) -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(b"same document bytes"))


def test_upload_reuses_structured_data_for_same_file_hash(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'parse-cache.db'}")
    Base.metadata.create_all(bind=engine)
    parsed = {"candidate_name": "Ada Lovelace", "name": "Ada Lovelace"}
    parse_calls = []
    vectorized_document_ids = []

    class FakeRagStore:
        def replace_document_chunks(self, *, user_id, document_id, chunks):
            vectorized_document_ids.append(document_id)

        def delete_document(self, **_kwargs):
            pass

    stored_calls = []

    def fake_store_upload(_file):
        index = len(stored_calls)
        stored_calls.append(index)
        return SimpleNamespace(
            filename=f"resume_{index}.txt",
            path=Path(tmp_path / f"resume_{index}.txt"),
            size=19,
            content_hash="same-sha256",
        )

    def fake_parse_profile(*_args, **_kwargs):
        parse_calls.append(True)
        if len(parse_calls) > 1:
            raise AssertionError("duplicate upload should reuse structured data")
        return parsed

    monkeypatch.setattr(document_routes.anyio.from_thread, "run", lambda func, *args: func(*args))
    monkeypatch.setattr(document_routes, "store_upload", fake_store_upload)
    monkeypatch.setattr(
        document_routes,
        "extract_stored_pages",
        lambda *_args, **_kwargs: [PageText(page_number=1, text="Candidate resume text with enough content.")],
    )
    monkeypatch.setattr(document_routes, "_parse_profile", fake_parse_profile)
    monkeypatch.setattr(document_routes, "ChromaRagStore", lambda: FakeRagStore())

    with Session(engine) as db:
        user = User(username="parse-cache-user", password_hash="hash")
        db.add(user)
        db.commit()

        first = upload_documents(
            document_type="resume",
            files=[_upload("resume.txt")],
            task_id="task-first",
            current_user=SimpleNamespace(id=user.id),
            db=db,
        )
        second = upload_documents(
            document_type="resume",
            files=[_upload("resume.txt")],
            task_id="task-second",
            current_user=SimpleNamespace(id=user.id),
            db=db,
        )

    assert len(parse_calls) == 1
    assert first.documents[0].parsed_content == parsed
    assert second.documents[0].parsed_content == parsed
    assert first.documents[0].id != second.documents[0].id
    assert vectorized_document_ids == [1, 2]
