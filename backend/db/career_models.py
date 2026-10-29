"""Career facts, resume artifacts and interview history."""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.database import Base
from backend.db.models import LARGE_TEXT, utcnow
from backend.schemas.resume_versions import VersionStatus


class ProfileFact(Base):
    __tablename__ = 'profile_facts'
    __table_args__ = (
        UniqueConstraint('user_id', 'fact_key', 'revision', name='uq_profile_fact_revision'),
        CheckConstraint('revision > 0', name='ck_profile_fact_revision'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    fact_key: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(80))
    content: Mapped[dict] = mapped_column(JSON)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey('resumes.id', ondelete='SET NULL'))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)


class ResumeVersion(Base):
    __tablename__ = 'resume_versions'
    __table_args__ = (CheckConstraint('revision > 0', name='ck_resume_version_revision'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey('agent_runs.id', ondelete='SET NULL'), index=True)
    resume_id: Mapped[int | None] = mapped_column(ForeignKey('resumes.id', ondelete='SET NULL'), index=True)
    jd_id: Mapped[int | None] = mapped_column(ForeignKey('job_descriptions.id', ondelete='SET NULL'), index=True)
    parent_version_id: Mapped[str | None] = mapped_column(ForeignKey('resume_versions.id', ondelete='SET NULL'))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    structured_content: Mapped[dict] = mapped_column(JSON, default=dict)
    fact_refs: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[VersionStatus] = mapped_column(Enum(VersionStatus, values_callable=lambda e: [v.value for v in e], native_enum=False, create_constraint=True, name='version_status'), default=VersionStatus.DRAFT)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class InterviewSession(Base):
    __tablename__ = 'interview_sessions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    application_id: Mapped[int | None] = mapped_column(ForeignKey('job_applications.id', ondelete='SET NULL'))
    jd_id: Mapped[int | None] = mapped_column(ForeignKey('job_descriptions.id', ondelete='SET NULL'))
    resume_version_id: Mapped[str] = mapped_column(ForeignKey('resume_versions.id'))
    status: Mapped[str] = mapped_column(Enum('active', 'finished', native_enum=False, create_constraint=True, name='interview_status'), default='active')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class InterviewTurn(Base):
    __tablename__ = 'interview_turns'
    __table_args__ = (UniqueConstraint('interview_id', 'turn_index', name='uq_interview_turn'), CheckConstraint('turn_index >= 0', name='ck_interview_turn_index'))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    interview_id: Mapped[str] = mapped_column(ForeignKey('interview_sessions.id', ondelete='CASCADE'))
    turn_index: Mapped[int] = mapped_column(Integer)
    question: Mapped[str] = mapped_column(LARGE_TEXT)
    answer: Mapped[str | None] = mapped_column(LARGE_TEXT)
    feedback: Mapped[dict | None] = mapped_column(JSON)


class InterviewEvent(Base):
    __tablename__ = 'interview_events'
    __table_args__ = (UniqueConstraint('interview_id', 'seq', name='uq_interview_event_seq'), CheckConstraint('seq > 0', name='ck_interview_event_seq'))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    interview_id: Mapped[str] = mapped_column(ForeignKey('interview_sessions.id', ondelete='CASCADE'))
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class InterviewCommand(Base):
    __tablename__ = 'interview_commands'
    __table_args__ = (UniqueConstraint('interview_id', 'client_message_id', name='uq_interview_command'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    interview_id: Mapped[str] = mapped_column(ForeignKey('interview_sessions.id', ondelete='CASCADE'))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    client_message_id: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(40))
    result_ref: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(Enum('accepted', 'succeeded', 'failed', native_enum=False, create_constraint=True, name='interview_command_status'), default='accepted')
