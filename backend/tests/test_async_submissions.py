import json
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, FastAPI, UploadFile
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.db.database import Base, get_db
from backend.db.models import Resume, User
from backend.auth.security import get_current_user
from backend.routes import documents, runs
from backend.schemas.workflow import AnalyzeRequest, AnalyzeResponse
from backend.services.documents import StoredUpload
from backend.services.progress import progress_hub


@pytest.fixture
def background_db(tmp_path, monkeypatch):
    from backend.services import background_tasks

    engine = create_engine(f"sqlite:///{tmp_path / 'async.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    worker_sessions = []

    class TrackedSession(Session):
        closed = False

        def close(self):
            self.closed = True
            super().close()

    factory = sessionmaker(engine, class_=TrackedSession, expire_on_commit=False)

    def worker_session():
        db = factory()
        worker_sessions.append(db)
        return db

    monkeypatch.setattr(background_tasks, "SessionLocal", worker_session)
    with Session(engine) as db:
        user = User(username="async-user", password_hash="hash")
        db.add(user)
        db.commit()
        user_id = user.id
    yield engine, user_id, worker_sessions
    engine.dispose()


@pytest.mark.asyncio
async def test_async_upload_saves_file_before_accepting_and_uses_own_session(background_db, tmp_path, monkeypatch):
    engine, user_id, workers = background_db
    request_db = Session(engine)
    path = tmp_path / "resume.txt"
    path.write_text("Candidate resume text for asynchronous extraction.")
    stored = StoredUpload("resume.txt", path, path.stat().st_size, "async-upload")
    monkeypatch.setattr(documents.anyio.from_thread, "run", lambda *args: stored)
    calls = []
    monkeypatch.setattr(documents, "_parse_profile", lambda *args: calls.append("parsed") or {"candidate_name": "Ada"})
    monkeypatch.setattr(documents, "get_rag_store", lambda: SimpleNamespace(replace_document_chunks=lambda **kwargs: None))
    background = BackgroundTasks()
    upload = UploadFile(filename="resume.txt", file=BytesIO(b"already saved bytes"))

    response = documents.upload_documents(
        document_type="resume", files=[upload], task_id="async-upload", current_user=SimpleNamespace(id=user_id),
        db=request_db, prefer="respond-async", background_tasks=background,
    )

    assert response.status_code == 202
    assert json.loads(response.body) == {"taskId": "async-upload"}
    assert calls == [] and workers == []
    await upload.close()
    request_db.close()
    await background()

    assert calls == ["parsed"]
    assert len(workers) == 1 and workers[0] is not request_db and workers[0].closed
    with Session(engine) as db:
        row = db.query(Resume).one()
        assert row.file_path == str(path)
        assert row.parse_status == "success"
    terminal = progress_hub._history["async-upload"][-1]
    assert terminal.status == "success"
    assert terminal.data["documents"][0]["filename"] == "resume.txt"


@pytest.mark.asyncio
async def test_async_upload_failure_reaches_sse_and_cleans_saved_file(background_db, tmp_path, monkeypatch):
    engine, user_id, workers = background_db
    path = tmp_path / "bad.txt"
    path.write_text("Candidate resume text for asynchronous extraction.")
    stored = StoredUpload("bad.txt", path, path.stat().st_size, "bad-upload")
    monkeypatch.setattr(documents.anyio.from_thread, "run", lambda *args: stored)

    def fail(*args):
        raise ValueError("profile extraction failed")

    monkeypatch.setattr(documents, "_parse_profile", fail)
    background = BackgroundTasks()
    with Session(engine) as db:
        response = documents.upload_documents(
            document_type="resume", files=[UploadFile(filename="bad.txt", file=BytesIO())], task_id="async-failed",
            current_user=SimpleNamespace(id=user_id), db=db, prefer="respond-async", background_tasks=background,
        )
    assert response.status_code == 202
    await background()
    terminal = progress_hub._history["async-failed"][-1]
    assert terminal.status == "failed" and "profile extraction failed" in terminal.message
    assert workers[0].closed
    assert not path.exists()
    with Session(engine) as db:
        assert db.query(Resume).count() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["run", "questions", "reparse"])
async def test_long_routes_accept_before_background_work(background_db, monkeypatch, operation):
    engine, user_id, workers = background_db
    calls = []

    class Analysis:
        def __init__(self, db):
            assert db in workers

        def analyze_document_ids(self, **kwargs):
            calls.append(kwargs)
            return AnalyzeResponse(run_id=7, job_title="Backend", candidates=[], task_id=kwargs["task_id"])

        def generate_questions(self, **kwargs):
            calls.append(kwargs)
            raise ValueError("question generation failed")

    monkeypatch.setattr(runs, "AnalysisService", Analysis)
    with Session(engine) as db:
        row = Resume(user_id=user_id, filename="resume.txt", file_path="saved.txt", raw_text="old", structured_data={})
        db.add(row)
        db.commit()
        row_id = row.id
        background = BackgroundTasks()
        common = dict(current_user=SimpleNamespace(id=user_id), db=db, prefer="respond-async", background_tasks=background)
        if operation == "run":
            response = runs.create_run(AnalyzeRequest(jd_document_id="jd:1", resume_document_ids=["resume:1"]), **common)
        elif operation == "questions":
            response = runs.generate_candidate_questions(7, 8, task_id="async-questions", question_count=3, **common)
        else:
            monkeypatch.setattr(documents, "extract_stored_pages", lambda *args, **kwargs: calls.append("extracted") or (_ for _ in ()).throw(ValueError("extract failed")))
            response = documents.reparse_document(f"resume:{row_id}", task_id="async-reparse", **common)
        assert response.status_code == 202
        task_id = json.loads(response.body)["taskId"]
        assert isinstance(task_id, str) and task_id
        assert calls == [] and workers == []
    await background()
    assert calls
    assert len(workers) == 1 and workers[0].closed
    if operation != "run":
        assert progress_hub._history[task_id][-1].status == "failed"


def test_http_prefer_header_accepts_without_changing_sync_response(background_db, monkeypatch):
    engine, user_id, workers = background_db

    class Analysis:
        def __init__(self, db):
            pass

        def analyze_document_ids(self, **kwargs):
            return AnalyzeResponse(run_id=7, job_title="Backend", candidates=[], task_id=kwargs["task_id"])

    monkeypatch.setattr(runs, "AnalysisService", Analysis)
    app = FastAPI()
    app.include_router(runs.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)

    def request_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = request_db
    with TestClient(app) as client:
        payload = {"jd_document_id": "jd:1", "resume_document_ids": ["resume:1"]}
        accepted = client.post("/api/runs", json=payload, headers={"Prefer": "respond-async"})
        sync = client.post("/api/runs", json=payload)
    assert accepted.status_code == 202 and set(accepted.json()) == {"taskId"}
    assert sync.status_code == 200 and sync.json()["run_id"] == 7


@pytest.mark.asyncio
async def test_followup_async_submission_publishes_own_complete_model_result(background_db, monkeypatch):
    from backend.schemas.workflow import FollowUpAnalysisRequest, FollowUpAnalysisResponse

    engine, user_id, workers = background_db
    result = FollowUpAnalysisResponse(
        follow_up="Which part did you implement?", reason="Clarify ownership", evidence=["project scope"],
        risks=["unclear role"], current_ability="Needs more evidence", next_suggestion="Ask for an example",
    )
    calls = []

    class Harness:
        def __init__(self, *, user_id):
            assert user_id > 0

        def run_schema(self, **kwargs):
            calls.append(kwargs)
            assert kwargs["schema"] is FollowUpAnalysisResponse
            return result

    monkeypatch.setattr(documents, "AgentHarness", Harness)
    background = BackgroundTasks()
    with Session(engine) as db:
        response = documents.analyze_followup(
            FollowUpAnalysisRequest(question="What did you build?", answer="A backend service"),
            current_user=SimpleNamespace(id=user_id), db=db, prefer="respond-async",
            background_tasks=background, task_id="async-followup",
        )
    assert response.status_code == 202
    assert json.loads(response.body) == {"taskId": "async-followup"}
    assert calls == [] and workers == []
    await background()
    assert len(calls) == 1 and workers[0].closed
    terminal = progress_hub._history["async-followup"][-1]
    assert terminal.status == "success"
    assert terminal.data == result.model_dump(mode="json")
