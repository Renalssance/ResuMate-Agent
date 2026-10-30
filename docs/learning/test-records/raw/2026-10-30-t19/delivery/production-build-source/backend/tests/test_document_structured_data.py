from datetime import datetime, timezone

import pytest

from backend.db.models import JobDescription, Resume, User
from backend.routes.documents import update_document_structured_data
from backend.schemas.workflow import StructuredDataUpdate


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args):
        for expression in args:
            field_name = getattr(getattr(expression, "left", None), "key", "")
            expected = getattr(getattr(expression, "right", None), "value", None)
            if field_name:
                self.rows = [row for row in self.rows if getattr(row, field_name) == expected]
        return self

    def first(self):
        return self.rows[0] if self.rows else None


class FakeDb:
    def __init__(self, rows):
        self.rows = rows
        self.committed = False
        self.refreshed = None

    def query(self, model):
        return FakeQuery([row for row in self.rows if isinstance(row, model)])

    def add(self, row):
        if row not in self.rows:
            self.rows.append(row)

    def commit(self):
        self.committed = True

    def refresh(self, row):
        self.refreshed = row


def _resume():
    return Resume(
        id=7,
        user_id=42,
        filename="resume.pdf",
        raw_text="raw",
        structured_data={"candidate_name": "Ada"},
        parse_status="success",
        document_size=10,
        created_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
    )


def test_update_document_structured_data_persists_current_user_resume():
    row = _resume()
    db = FakeDb([row])

    response = update_document_structured_data(
        "resume:7",
        StructuredDataUpdate(structuredData={"candidate_name": "Ada", "application": {"referral_code": "BT-123"}}),
        current_user=User(id=42, username="ada", role="user", password_hash="hash"),
        db=db,
    )

    assert db.committed is True
    assert db.refreshed is row
    assert row.structured_data["application"]["referral_code"] == "BT-123"
    assert row.updated_at > datetime(2026, 8, 6, tzinfo=timezone.utc)
    assert response.id == "resume:7"
    assert response.parsed_content["application"]["referral_code"] == "BT-123"


def test_update_document_structured_data_rejects_jd_documents():
    db = FakeDb([
        JobDescription(
            id=3,
            user_id=42,
            title="Engineer",
            raw_text="raw",
            structured_data={},
            parse_status="success",
            document_size=10,
            created_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
            updated_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
        )
    ])

    with pytest.raises(Exception) as exc_info:
        update_document_structured_data(
            "jd:3",
            StructuredDataUpdate(structuredData={"title": "Engineer"}),
            current_user=User(id=42, username="ada", role="user", password_hash="hash"),
            db=db,
        )

    assert getattr(exc_info.value, "status_code", None) == 422
