from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from fastapi import UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.db.database import Base
from backend.db.models import LlmUsageEvent, User
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


def test_upload_releases_sqlite_write_lock_before_llm_usage_recording(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'parse-lock.db'}",
        connect_args={"timeout": 0.01},
    )
    Base.metadata.create_all(bind=engine)

    class FakeRagStore:
        def replace_document_chunks(self, *, user_id, document_id, chunks):
            pass

        def delete_document(self, **_kwargs):
            pass

    def fake_store_upload(_file):
        return SimpleNamespace(
            filename="jd.txt",
            path=Path(tmp_path / "jd.txt"),
            size=19,
            content_hash="jd-sha256",
        )

    def fake_parse_profile(*_args, **_kwargs):
        with Session(engine) as usage_db:
            usage_db.add(
                LlmUsageEvent(
                    user_id=1,
                    task="document.parse_jd",
                    model="model",
                    base_url="base",
                    prompt_tokens=1,
                    completion_tokens=1,
                    total_tokens=2,
                    success=True,
                    error_type="",
                    elapsed_ms=1,
                )
            )
            usage_db.commit()
        return {"job_title": "Backend Engineer", "title": "Backend Engineer"}

    monkeypatch.setattr(document_routes.anyio.from_thread, "run", lambda func, *args: func(*args))
    monkeypatch.setattr(document_routes, "store_upload", fake_store_upload)
    monkeypatch.setattr(
        document_routes,
        "extract_stored_pages",
        lambda *_args, **_kwargs: [PageText(page_number=1, text="Backend Engineer JD with enough content.")],
    )
    monkeypatch.setattr(document_routes, "_parse_profile", fake_parse_profile)
    monkeypatch.setattr(document_routes, "ChromaRagStore", lambda: FakeRagStore())

    with Session(engine) as db:
        user = User(username="parse-lock-user", password_hash="hash")
        db.add(user)
        db.commit()

        result = upload_documents(
            document_type="jd",
            files=[_upload("jd.txt")],
            task_id="task-lock",
            current_user=SimpleNamespace(id=user.id),
            db=db,
        )

        usage_count = db.query(LlmUsageEvent).count()

    assert result.documents[0].parse_status == "success"
    assert usage_count == 1
