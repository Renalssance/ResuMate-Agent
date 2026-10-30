"""Autofill HTTP contracts against disposable SQL, including the profile-only API."""
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.db.models import Resume, User
from backend.routes.autofill import router
from backend.tests.career_fixtures import career_db, career_engine


@pytest.fixture
def client(career_db, career_engine):
    app = FastAPI()
    app.include_router(router)
    factory = sessionmaker(career_engine, expire_on_commit=False)
    def request_db():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = request_db
    app.dependency_overrides[get_current_user] = lambda: User(
        id=1, username='alice', password_hash='test')
    with TestClient(app) as result:
        yield result


@pytest.fixture
def saved_resume(career_db):
    row = Resume(id=3, user_id=1, filename='ada.pdf', raw_text='',
                 structured_data={'candidate_name': 'Ada', 'contact': {'email': 'ada@example.com'}})
    career_db.add(row)
    career_db.commit()
    return row


def test_list_autofill_profiles_returns_resume_summaries(client, saved_resume):
    response = client.get("/api/autofill/profiles")

    assert response.status_code == 200
    profile = next(item for item in response.json() if item["id"] == "resume:3")
    assert profile["name"] == "Ada"
    assert profile["fieldCount"] > 0


def test_get_autofill_profile_returns_full_profile(client, saved_resume):
    response = client.get("/api/autofill/profiles/resume:3")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sourceResumeId"] == "resume:3"
    assert payload["sections"][0]["fields"][0]["value"] == "Ada"


def test_get_autofill_profile_rejects_wrong_profile_id(client):
    response = client.get("/api/autofill/profiles/resume:999")

    assert response.status_code == 404


def test_get_autofill_profile_rejects_other_user_resume(client, saved_resume, career_db):
    saved_resume.user_id = 2
    career_db.commit()
    response = client.get("/api/autofill/profiles/resume:3")

    assert response.status_code == 404


def test_match_autofill_profile_by_payload(client, saved_resume):
    profile = client.get("/api/autofill/profiles/resume:3").json()

    response = client.post(
        "/api/autofill/match",
        json={
            "profile": profile,
            "page": {"url": "https://jobs.bytedance.com", "title": "Apply"},
            "elements": [{"index": 0, "tag": "input", "type": "email", "labelText": "邮箱"}],
        },
    )

    assert response.status_code == 200
    assert response.json()["matches"][0]["fieldKey"] == "contact.email"


def test_events_endpoint_redacts_values_from_response(client, caplog):
    caplog.set_level(logging.INFO, logger="backend.routes.autofill")

    response = client.post(
        "/api/autofill/events",
        json={
            "eventType": "fill",
            "status": "success",
            "profileId": "resume:3",
            "fieldKeys": ["contact.email"],
            "elementSummaries": [
                {
                    "index": 0,
                    "labelText": "Email",
                    "name": "email",
                    "type": "email",
                    "value": "ada@example.com",
                    "inputValue": "secret@example.com",
                    "nested": {"value": "nested@example.com"},
                }
            ],
            "errors": ["failed to fill secret@example.com"],
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "ada@example.com" not in messages
    assert "secret@example.com" not in messages
    assert "nested@example.com" not in messages
