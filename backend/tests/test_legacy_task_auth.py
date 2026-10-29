from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.auth.security import create_access_token
from backend.db.database import Base, get_db
from backend.db.models import User
from backend.routes import tasks
from backend.services.analysis import AnalysisService
from backend.services.progress import TaskProgressHub


@pytest.fixture
def task_client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'tasks.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner = User(username="owner", password_hash="hash")
        other = User(username="other", password_hash="hash")
        db.add_all([owner, other])
        db.commit()
        owner_id, other_id = owner.id, other.id
    hub = TaskProgressHub()
    monkeypatch.setattr(tasks, "progress_hub", hub)
    app = FastAPI()
    app.include_router(tasks.router)

    def request_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = request_db
    with TestClient(app) as client:
        yield client, hub, owner_id, other_id, engine
    engine.dispose()


def test_task_registration_preserves_owner_history_and_rejects_another_user():
    hub = TaskProgressHub()
    task_id = hub.create_task("parse", user_id=1, task_id="client-generated")
    hub.publish(task_id, stage="extract", status="running", progress=30, message="Extracting")

    assert task_id == "client-generated"
    assert hub.create_task("parse", user_id=1, task_id=task_id) == task_id
    assert hub.is_owned_by(task_id, 1)
    assert not hub.is_owned_by(task_id, 2)
    assert not hub.is_owned_by("unknown", 1)
    assert len(hub._history[task_id]) == 1
    with pytest.raises(HTTPException) as error:
        hub.create_task("parse", user_id=2, task_id=task_id)
    assert error.value.status_code == 404
    assert hub.is_owned_by(task_id, 1)
    assert len(hub._history[task_id]) == 1


def test_legacy_task_events_require_token_and_owner_before_streaming(task_client):
    client, hub, owner_id, other_id, _ = task_client
    task_id = hub.create_task("parse", user_id=owner_id)
    hub.publish(task_id, stage="completed", status="success", progress=100, message="Private result")
    owner_headers = {"Authorization": f"Bearer {create_access_token('owner', 'user')}"}
    other_headers = {"Authorization": f"Bearer {create_access_token('other', 'user')}"}

    assert client.get(f"/api/tasks/{task_id}/events").status_code == 401
    assert client.get(f"/api/tasks/{task_id}/events", headers=other_headers).status_code == 404
    assert client.get("/api/tasks/unknown/events", headers=owner_headers).status_code == 404
    response = client.get(f"/api/tasks/{task_id}/events", headers=owner_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"message":"Private result"' in response.text
    assert '"status":"success"' in response.text


@pytest.mark.parametrize("operation", ["analysis", "questions"])
def test_sync_analysis_registers_caller_task_before_publishing(monkeypatch, operation):
    from backend.services import analysis

    hub = TaskProgressHub()
    monkeypatch.setattr(analysis, "progress_hub", hub)
    service = AnalysisService.__new__(AnalysisService)
    service.repository = SimpleNamespace(get_candidate_report=lambda **kwargs: None)
    task_id = f"sync-{operation}"

    with pytest.raises(ValueError):
        if operation == "analysis":
            service.analyze_document_ids(user_id=17, jd_document_id="invalid", resume_document_ids=[], task_id=task_id)
        else:
            service.generate_questions(user_id=17, run_id=1, candidate_id=1, task_id=task_id)
    assert hub.is_owned_by(task_id, 17)
    assert hub._history[task_id][-1].status == "failed"


@pytest.mark.parametrize("operation", ["upload", "reparse", "run", "questions", "followup"])
@pytest.mark.parametrize("prefer", ["", "respond-async"])
def test_submission_rejects_another_users_task_id_before_work(monkeypatch, operation, prefer):
    from io import BytesIO
    from fastapi import BackgroundTasks, UploadFile
    from backend.routes import documents, runs
    from backend.schemas.workflow import AnalyzeRequest, FollowUpAnalysisRequest

    hub = TaskProgressHub()
    task_id = hub.create_task(user_id=1, task_id="owned-task")
    monkeypatch.setattr(documents, "progress_hub", hub)
    monkeypatch.setattr(runs, "progress_hub", hub)
    monkeypatch.setattr(documents, "_find_document", lambda *args: ("resume", object()))
    common = dict(current_user=SimpleNamespace(id=2), db=object(), prefer=prefer, background_tasks=BackgroundTasks())
    with pytest.raises(HTTPException) as error:
        if operation == "upload":
            documents.upload_documents(document_type="resume", files=[UploadFile(filename="resume.txt", file=BytesIO(b"text"))], task_id=task_id, **common)
        elif operation == "reparse":
            documents.reparse_document("resume:1", task_id=task_id, **common)
        elif operation == "run":
            runs.create_run(AnalyzeRequest(jd_document_id="jd:1", resume_document_ids=["resume:1"], task_id=task_id), **common)
        elif operation == "questions":
            runs.generate_candidate_questions(1, 1, task_id=task_id, question_count=3, **common)
        else:
            documents.analyze_followup(FollowUpAnalysisRequest(question="What?", answer="This"), task_id=task_id, **common)
    assert error.value.status_code == 404
    assert hub.is_owned_by(task_id, 1)
    assert hub._history[task_id] == []
    assert common["background_tasks"].tasks == []


def test_legacy_stream_releases_auth_database_connection_before_yielding(task_client, monkeypatch):
    client, hub, owner_id, _, engine = task_client
    task_id = hub.create_task("parse", user_id=owner_id)
    checked_out = []

    async def finite_stream(_task_id):
        checked_out.append(engine.pool.checkedout())
        yield ": heartbeat\n\n"
        checked_out.append(engine.pool.checkedout())

    monkeypatch.setattr(hub, "stream", finite_stream)
    headers = {"Authorization": f"Bearer {create_access_token('owner', 'user')}"}
    response = client.get(f"/api/tasks/{task_id}/events", headers=headers)

    assert response.status_code == 200
    assert response.text == ": heartbeat\n\n"
    assert checked_out == [0, 0]
