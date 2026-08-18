from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


ApplicationStatus = Literal[
    "applied",
    "assessment",
    "written_test",
    "interviewing",
    "first_interview",
    "second_interview",
    "third_interview",
    "hr_interview",
    "offer",
    "resume_rejected",
    "assessment_rejected",
    "written_test_rejected",
    "interview_rejected",
    "passed",
    "withdrawn",
]


class ApplicationBase(BaseModel):
    company: str = Field(min_length=1, max_length=255)
    position: str = Field(min_length=1, max_length=255)
    applied_date: date
    resume_id: int | None = None
    status: ApplicationStatus = "applied"
    job_url: str = ""
    source: str = ""
    notes: str = ""


class ApplicationCreate(ApplicationBase):
    pass


class ApplicationUpdate(BaseModel):
    company: str | None = Field(default=None, min_length=1, max_length=255)
    position: str | None = Field(default=None, min_length=1, max_length=255)
    applied_date: date | None = None
    resume_id: int | None = None
    status: ApplicationStatus | None = None
    job_url: str | None = None
    source: str | None = None
    notes: str | None = None


class ApplicationStatusEventCreate(BaseModel):
    status: ApplicationStatus
    changed_at: datetime | None = None
    note: str = ""


class ApplicationStatusEventRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: ApplicationStatus
    changed_at: datetime
    note: str
    created_at: datetime

    @field_serializer("changed_at", "created_at")
    def _serialize_datetime(self, value: datetime):
        if value.tzinfo is None:
            return value.isoformat() + "Z"
        return value.isoformat().replace("+00:00", "Z")


class ApplicationRecord(ApplicationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resume_filename: str = ""
    status_events: list[ApplicationStatusEventRecord] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def _serialize_datetime(self, value: datetime):
        if value.tzinfo is None:
            return value.isoformat() + "Z"
        return value.isoformat().replace("+00:00", "Z")
