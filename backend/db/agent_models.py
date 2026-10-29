"""Persistent execution records. Checkpoints and queue messages live elsewhere."""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, Enum, ForeignKey, ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.database import Base
from backend.db.models import utcnow
from backend.schemas.agent_runs import RunStatus


class AgentSession(Base):
    __tablename__ = 'agent_sessions'
    __table_args__ = (UniqueConstraint('id', 'user_id', name='uq_agent_session_owner'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    purpose: Mapped[str] = mapped_column(String(80))
    context_invalidated_at: Mapped[datetime | None] = mapped_column(DateTime)
    checkpoint_deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Claimed/released by conditional SQL updates in the Run service (T03).
    active_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AgentRun(Base):
    __tablename__ = 'agent_runs'
    __table_args__ = (
        UniqueConstraint('user_id', 'request_id', name='uq_agent_run_request'),
        ForeignKeyConstraint(['session_id', 'user_id'], ['agent_sessions.id', 'agent_sessions.user_id'], ondelete='CASCADE'),
        CheckConstraint('attempt >= 1 AND execution_epoch >= 0', name='ck_agent_run_attempt'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    request_id: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(80))
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, values_callable=lambda e: [v.value for v in e], native_enum=False,
             create_constraint=True, name='run_status'), default=RunStatus.QUEUED, index=True)
    input_json: Mapped[dict] = mapped_column(JSON, default=dict)
    input_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    execution_epoch: Mapped[int] = mapped_column(Integer, default=0)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_code: Mapped[str | None] = mapped_column(String(100))
    output_refs: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AgentRunEvent(Base):
    __tablename__ = 'agent_run_events'
    __table_args__ = (
        UniqueConstraint('run_id', 'seq', name='uq_agent_run_event_seq'),
        CheckConstraint('seq > 0', name='ck_agent_run_event_seq'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey('agent_runs.id', ondelete='CASCADE'))
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AgentAction(Base):
    __tablename__ = 'agent_actions'
    __table_args__ = (UniqueConstraint('run_id', 'interrupt_id', name='uq_agent_action_interrupt'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey('agent_runs.id', ondelete='CASCADE'))
    interrupt_id: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(Enum('input', 'approval', native_enum=False, create_constraint=True, name='action_kind'))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(Enum('pending', 'answered', native_enum=False, create_constraint=True, name='action_status'), default='pending')
    response: Mapped[dict | None] = mapped_column(JSON)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime)


class ToolOperation(Base):
    __tablename__ = 'tool_operations'
    __table_args__ = (UniqueConstraint('run_id', 'operation_key', name='uq_tool_operation_key'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey('agent_runs.id', ondelete='CASCADE'))
    operation_key: Mapped[str] = mapped_column(String(160))
    tool_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(Enum('pending', 'succeeded', 'failed', native_enum=False, create_constraint=True, name='tool_operation_status'), default='pending')
    result_ref: Mapped[str | None] = mapped_column(String(255))
