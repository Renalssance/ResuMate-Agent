from datetime import datetime, timezone

from fastapi.testclient import TestClient

from backend.app import app
from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.db.models import Resume, User


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class FakeDb:
    def __init__(self, rows):
        self.rows = rows

    def query(self, model):
        assert model is Resume
        return FakeQuery(self.rows)


def _resume() -> Resume:
    return Resume(
        id=3,
        user_id=42,
        filename="ada.pdf",
        raw_text="",
        structured_data={"candidate_name": "Ada", "contact": {"email": "ada@example.com"}},
        created_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
    )


def _client(rows):
    app.dependency_overrides[get_current_user] = lambda: User(id=42, username="ada", role="user", password_hash="hash")
    app.dependency_overrides[get_db] = lambda: FakeDb(rows)
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_list_autofill_profiles_returns_resume_summaries():
    response = _client([_resume()]).get("/api/autofill/profiles")

    assert response.status_code == 200
    assert response.json()[0]["id"] == "resume:3"
    assert response.json()[0]["name"] == "Ada"
    assert response.json()[0]["fieldCount"] > 0


def test_get_autofill_profile_returns_full_profile():
    response = _client([_resume()]).get("/api/autofill/profiles/resume:3")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sourceResumeId"] == "resume:3"
    assert payload["sections"][0]["fields"][0]["value"] == "Ada"


def test_match_autofill_profile_by_payload():
    profile = _client([_resume()]).get("/api/autofill/profiles/resume:3").json()

    response = _client([_resume()]).post(
        "/api/autofill/match",
        json={
            "profile": profile,
            "page": {"url": "https://jobs.bytedance.com", "title": "Apply"},
            "elements": [{"index": 0, "tag": "input", "type": "email", "labelText": "邮箱"}],
        },
    )

    assert response.status_code == 200
    assert response.json()["matches"][0]["fieldKey"] == "contact.email"


def test_events_endpoint_redacts_values_from_response():
    response = _client([_resume()]).post(
        "/api/autofill/events",
        json={
            "eventType": "fill",
            "status": "success",
            "profileId": "resume:3",
            "fieldKeys": ["contact.email"],
            "elementSummaries": [{"index": 0, "labelText": "Email", "value": "ada@example.com"}],
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
