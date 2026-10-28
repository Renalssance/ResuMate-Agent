from datetime import date, datetime, timezone

from sqlalchemy import Boolean, JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.database import Base

# PDF extraction and generated chat content can exceed MySQL TEXT's 64 KiB.
LARGE_TEXT = Text().with_variant(LONGTEXT, "mysql")


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
    resumes = relationship("Resume", back_populates="user", cascade="all, delete-orphan")
    job_descriptions = relationship("JobDescription", back_populates="user", cascade="all, delete-orphan")
    analysis_jobs = relationship("AnalysisJob", back_populates="user", cascade="all, delete-orphan")
    applications = relationship("JobApplication", back_populates="user", cascade="all, delete-orphan")
    llm_settings = relationship("UserLlmSettings", back_populates="user", cascade="all, delete-orphan", uselist=False)
    llm_usage_events = relationship("LlmUsageEvent", back_populates="user", cascade="all, delete-orphan")


class UserLlmSettings(Base):
    """OpenAI-compatible model settings saved per user."""

    __tablename__ = "user_llm_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    api_key: Mapped[str] = mapped_column(Text, default="", nullable=False)
    base_url: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    model: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_timeout_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user = relationship("User", back_populates="llm_settings")


class LlmUsageEvent(Base):
    """Per-user model call usage for the settings dashboard."""

    __tablename__ = "llm_usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    task: Mapped[str] = mapped_column(String(120), default="", nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    base_url: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    error_type: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    called_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)

    user = relationship("User", back_populates="llm_usage_events")


class JobApplication(Base):
    """用户手动维护的简历投递记录。"""

    __tablename__ = "job_applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id: Mapped[int | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True, index=True)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[str] = mapped_column(String(255), nullable=False)
    applied_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), default="applied", nullable=False, index=True)
    job_url: Mapped[str] = mapped_column(String(1024), default="", server_default="", nullable=False)
    source: Mapped[str] = mapped_column(String(120), default="", server_default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user = relationship("User", back_populates="applications")
    resume = relationship("Resume")
    status_events = relationship(
        "JobApplicationStatusEvent",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="desc(JobApplicationStatusEvent.changed_at)",
    )
    schedules = relationship(
        "JobApplicationSchedule",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="JobApplicationSchedule.starts_at",
    )


class JobApplicationStatusEvent(Base):
    """投递状态变化时间线。"""

    __tablename__ = "job_application_status_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("job_applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    application = relationship("JobApplication", back_populates="status_events")


class JobApplicationSchedule(Base):
    """投递关联的笔试、面试等日程。"""

    __tablename__ = "job_application_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("job_applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    completed_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_application_status_events.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    application = relationship("JobApplication", back_populates="schedules")
    completed_event = relationship("JobApplicationStatusEvent")


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (UniqueConstraint("user_id", "session_id", name="uq_user_session"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user = relationship("User", back_populates="sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_ref_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    message_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(LARGE_TEXT, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    session = relationship("ChatSession", back_populates="messages")


class Resume(Base):
    """用户简历表。"""

    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), default="", server_default="", nullable=False, index=True)
    document_size: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    parse_status: Mapped[str] = mapped_column(
        String(40), default="pending", server_default="pending", nullable=False, index=True
    )
    raw_text: Mapped[str] = mapped_column(LARGE_TEXT, default="", nullable=False)
    structured_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user = relationship("User", back_populates="resumes")


class JobDescription(Base):
    """职位描述表。"""

    __tablename__ = "job_descriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    filename: Mapped[str] = mapped_column(String(255), default="", server_default="", nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), default="", server_default="", nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), default="", server_default="", nullable=False, index=True)
    document_size: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    parse_status: Mapped[str] = mapped_column(
        String(40), default="pending", server_default="pending", nullable=False, index=True
    )
    raw_text: Mapped[str] = mapped_column(LARGE_TEXT, nullable=False)
    structured_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user = relationship("User", back_populates="job_descriptions")


class AnalysisJob(Base):
    """Batch analysis task for one JD and multiple resumes."""

    __tablename__ = "analysis_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    jd_id: Mapped[int | None] = mapped_column(ForeignKey("job_descriptions.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user = relationship("User", back_populates="analysis_jobs")
    jd = relationship("JobDescription")
    candidates = relationship("AnalysisCandidate", back_populates="job", cascade="all, delete-orphan")
    match_results = relationship("MatchResult", back_populates="job", cascade="all, delete-orphan")
    question_sets = relationship("InterviewQuestionSet", back_populates="job", cascade="all, delete-orphan")
    follow_up_sets = relationship("FollowUpQuestionSet", back_populates="job", cascade="all, delete-orphan")


class AnalysisCandidate(Base):
    """Resume attached to an analysis job."""

    __tablename__ = "analysis_candidates"
    __table_args__ = (UniqueConstraint("job_id", "resume_id", name="uq_analysis_job_resume"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False, index=True)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    job = relationship("AnalysisJob", back_populates="candidates")
    resume = relationship("Resume")
    match_result = relationship("MatchResult", back_populates="candidate", uselist=False, cascade="all, delete-orphan")
    question_set = relationship("InterviewQuestionSet", back_populates="candidate", uselist=False, cascade="all, delete-orphan")
    follow_up_set = relationship("FollowUpQuestionSet", back_populates="candidate", uselist=False, cascade="all, delete-orphan")


class MatchResult(Base):
    """Persisted resume-JD match result."""

    __tablename__ = "match_results"
    __table_args__ = (UniqueConstraint("job_id", "candidate_id", name="uq_match_job_candidate"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("analysis_candidates.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False, index=True)
    jd_id: Mapped[int | None] = mapped_column(ForeignKey("job_descriptions.id", ondelete="SET NULL"), nullable=True, index=True)
    overall_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    recommendation: Mapped[str] = mapped_column(String(40), default="pending", nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    dimension_scores: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    matched_skills: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    missing_skills: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    strengths: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    gaps: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    report_json: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("('{}')"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    job = relationship("AnalysisJob", back_populates="match_results")
    candidate = relationship("AnalysisCandidate", back_populates="match_result")
    resume = relationship("Resume")
    jd = relationship("JobDescription")


class InterviewQuestionSet(Base):
    """Generated interview question set for a candidate."""

    __tablename__ = "interview_question_sets"
    __table_args__ = (UniqueConstraint("job_id", "candidate_id", name="uq_question_job_candidate"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("analysis_candidates.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False, index=True)
    jd_id: Mapped[int | None] = mapped_column(ForeignKey("job_descriptions.id", ondelete="SET NULL"), nullable=True, index=True)
    questions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    job = relationship("AnalysisJob", back_populates="question_sets")
    candidate = relationship("AnalysisCandidate", back_populates="question_set")
    resume = relationship("Resume")
    jd = relationship("JobDescription")


class FollowUpQuestionSet(Base):
    """Generated follow-up questions for ambiguous resume points."""

    __tablename__ = "follow_up_question_sets"
    __table_args__ = (UniqueConstraint("job_id", "candidate_id", name="uq_followup_job_candidate"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("analysis_candidates.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False, index=True)
    jd_id: Mapped[int | None] = mapped_column(ForeignKey("job_descriptions.id", ondelete="SET NULL"), nullable=True, index=True)
    questions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    job = relationship("AnalysisJob", back_populates="follow_up_sets")
    candidate = relationship("AnalysisCandidate", back_populates="follow_up_set")
    resume = relationship("Resume")
    jd = relationship("JobDescription")
