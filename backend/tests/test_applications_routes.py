from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app import app
from backend.auth.security import get_current_user
from backend.db.database import Base, get_db
from backend.db.models import Resume, User


def _client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'applications.db'}")
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    current_user = {"id": 1}

    def get_test_user():
        return User(
            id=current_user["id"],
            username=f"user-{current_user['id']}",
            role="user",
            password_hash="hash",
        )

    app.dependency_overrides[get_current_user] = get_test_user
    app.dependency_overrides[get_db] = lambda: session
    return TestClient(app), current_user, session


def teardown_function():
    app.dependency_overrides.clear()


def test_applications_create_list_update_and_delete_for_current_user(tmp_path):
    client, current_user, session = _client(tmp_path)
    payload = {
        "company": "ByteDance",
        "position": "后端开发工程师",
        "applied_date": "2026-08-18",
        "status": "applied",
        "job_url": "https://jobs.example.com/backend",
        "source": "官网",
        "notes": "使用通用版简历投递",
    }

    created = client.post("/api/applications", json=payload)

    assert created.status_code == 200
    body = created.json()
    assert body["id"] > 0
    assert body["company"] == "ByteDance"
    assert body["position"] == "后端开发工程师"
    assert body["applied_date"] == date(2026, 8, 18).isoformat()
    assert body["status"] == "applied"
    assert body["status_events"][0]["status"] == "applied"

    current_user["id"] = 2
    other = client.post(
        "/api/applications",
        json={**payload, "company": "Other Corp", "position": "算法工程师"},
    )
    assert other.status_code == 200

    current_user["id"] = 1
    listed = client.get("/api/applications")
    assert listed.status_code == 200
    assert [item["company"] for item in listed.json()] == ["ByteDance"]

    updated = client.patch(
        f"/api/applications/{body['id']}",
        json={"status": "interviewing", "notes": "一面已约"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "interviewing"
    assert updated.json()["notes"] == "一面已约"

    current_user["id"] = 2
    forbidden = client.patch(f"/api/applications/{body['id']}", json={"status": "passed"})
    assert forbidden.status_code == 404

    current_user["id"] = 1
    deleted = client.delete(f"/api/applications/{body['id']}")
    assert deleted.status_code == 200
    assert client.get("/api/applications").json() == []
    session.close()


def test_applications_can_edit_fields_and_link_owned_resume(tmp_path):
    client, _current_user, session = _client(tmp_path)
    resume = Resume(user_id=1, filename="backend.pdf", raw_text="", structured_data={"candidate_name": "Ada"})
    other_resume = Resume(user_id=2, filename="other.pdf", raw_text="", structured_data={})
    session.add_all([resume, other_resume])
    session.commit()

    rejected = client.post(
        "/api/applications",
        json={
            "company": "Bad Link",
            "position": "前端开发",
            "applied_date": "2026-08-18",
            "resume_id": other_resume.id,
        },
    )
    assert rejected.status_code == 404

    created = client.post(
        "/api/applications",
        json={
            "company": "ByteDance",
            "position": "后端开发",
            "applied_date": "2026-08-18",
            "resume_id": resume.id,
        },
    )
    assert created.status_code == 200
    assert created.json()["resume_id"] == resume.id
    assert created.json()["resume_filename"] == "backend.pdf"

    updated = client.patch(
        f"/api/applications/{created.json()['id']}",
        json={
            "company": "字节跳动",
            "position": "后端开发工程师",
            "job_url": "https://jobs.example.com/updated",
            "resume_id": None,
        },
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["company"] == "字节跳动"
    assert payload["position"] == "后端开发工程师"
    assert payload["job_url"] == "https://jobs.example.com/updated"
    assert payload["resume_id"] is None
    assert [event["status"] for event in payload["status_events"]] == ["applied"]
    session.close()


def test_application_status_changes_are_recorded_with_timestamps(tmp_path):
    client, _current_user, session = _client(tmp_path)
    created = client.post(
        "/api/applications",
        json={
            "company": "Tencent",
            "position": "平台开发",
            "applied_date": "2026-08-18",
        },
    ).json()

    response = client.post(
        f"/api/applications/{created['id']}/status-events",
        json={
            "status": "written_test",
            "changed_at": "2026-08-20T10:30:00Z",
            "note": "完成在线笔试",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "written_test"
    assert payload["status_events"][0]["status"] == "written_test"
    assert payload["status_events"][0]["changed_at"] == "2026-08-20T10:30:00Z"
    assert payload["status_events"][0]["note"] == "完成在线笔试"
    assert payload["status_events"][1]["status"] == "applied"
    session.close()
