"""Canonical Run states and typed event payloads shared by API and worker."""
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from backend.schemas.workflow import FollowUpAnalysisRequest


class RunStatus(StrEnum):
    QUEUED = 'queued'
    RUNNING = 'running'
    WAITING_INPUT = 'waiting_input'
    WAITING_APPROVAL = 'waiting_approval'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


class Payload(BaseModel):
    model_config = ConfigDict(extra='forbid')


class StatusPayload(Payload):
    status: RunStatus
    error_code: str | None = None


class DeltaPayload(Payload):
    text: str


class ToolPayload(Payload):
    tool_name: str
    operation_key: str


class ToolCompletedPayload(ToolPayload):
    result_ref: str | None = None


class ToolFailedPayload(ToolPayload):
    error_code: str
    message: str


class ActionPayload(Payload):
    action_id: str
    kind: Literal['input', 'approval']


class ArtifactPayload(Payload):
    artifact_id: str
    kind: str


class UsagePayload(Payload):
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)


class TaskProgressPayload(Payload):
    stage: str
    status: Literal['pending', 'running'] = 'running'
    progress: int = Field(ge=0, le=100)
    overall_progress: int = Field(ge=0, le=100)
    message: str
    document_id: str | None = None
    filename: str | None = None
    stage_progress: int | None = Field(default=None, ge=0, le=100)
    current: int | None = None
    total: int | None = None
    data: dict = Field(default_factory=dict)


class EventEnvelope(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='forbid')
    run_id: str = Field(alias='runId')
    seq: int = Field(ge=1)
    created_at: datetime = Field(alias='createdAt')


class StatusEvent(EventEnvelope):
    type: Literal['run.status']
    payload: StatusPayload


class DeltaEvent(EventEnvelope):
    type: Literal['assistant.delta']
    payload: DeltaPayload


class ToolStartedEvent(EventEnvelope):
    type: Literal['tool.started']
    payload: ToolPayload


class ToolCompletedEvent(EventEnvelope):
    type: Literal['tool.completed']
    payload: ToolCompletedPayload


class ToolFailedEvent(EventEnvelope):
    type: Literal['tool.failed']
    payload: ToolFailedPayload


class ActionEvent(EventEnvelope):
    type: Literal['action.required']
    payload: ActionPayload


class ArtifactEvent(EventEnvelope):
    type: Literal['artifact.created']
    payload: ArtifactPayload


class UsageEvent(EventEnvelope):
    type: Literal['usage.updated']
    payload: UsagePayload


class TaskProgressEvent(EventEnvelope):
    type: Literal['task.progress']
    payload: TaskProgressPayload


RunEvent = Annotated[
    StatusEvent | DeltaEvent | ToolStartedEvent | ToolCompletedEvent | ToolFailedEvent
    | ActionEvent | ArtifactEvent | UsageEvent | TaskProgressEvent,
    Field(discriminator='type'),
]
RUN_EVENT_ADAPTER = TypeAdapter(RunEvent)


class RunCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='forbid', str_strip_whitespace=True)
    session_id: str | None = Field(default=None, alias='sessionId', min_length=1, max_length=36)
    kind: Literal['tailoring', 'resume_export', 'document_parse', 'match_analysis', 'question_generation', 'answer_followup']
    jd_id: int | None = Field(default=None, alias='jdId', gt=0)
    resume_id: int | None = Field(default=None, alias='resumeId', gt=0)
    resume_version_id: str | None = Field(default=None, alias='resumeVersionId', min_length=1, max_length=36)
    document_id: str | None = Field(default=None, alias='documentId', pattern=r'^(resume|jd):[1-9][0-9]*$')
    parse_mode: Literal['upload', 'reparse', 'saved_job'] | None = Field(default=None, alias='parseMode')
    resume_ids: list[Annotated[int, Field(gt=0)]] | None = Field(default=None, alias='resumeIds', min_length=1)
    analysis_job_id: int | None = Field(default=None, alias='analysisJobId', gt=0)
    candidate_id: int | None = Field(default=None, alias='candidateId', gt=0)
    question_count: int = Field(default=10, alias='questionCount', ge=1, le=10)
    followup: FollowUpAnalysisRequest | None = None
    request_id: str = Field(alias='requestId', min_length=1, max_length=100)

    @model_validator(mode='after')
    def validate_inputs(self):
        fields = {
            'tailoring': {'jd_id', 'resume_id'},
            'resume_export': {'resume_version_id'},
            'document_parse': {'document_id', 'parse_mode'},
            'match_analysis': {'jd_id', 'resume_ids'},
            'question_generation': {'analysis_job_id', 'candidate_id', 'question_count'},
            'answer_followup': {'followup'},
        }[self.kind]
        if self.model_fields_set - fields - {'kind', 'session_id', 'request_id'}:
            raise ValueError('不能混用其他任务类型的字段')
        if any(getattr(self, field) is None for field in fields):
            raise ValueError('缺少任务需要的输入字段')
        if self.kind == 'document_parse' and self.parse_mode == 'saved_job' and not self.document_id.startswith('jd:'):
            raise ValueError('已保存岗位解析需要岗位文档')
        if self.kind == 'match_analysis' and len(set(self.resume_ids)) != len(self.resume_ids):
            raise ValueError('同一次匹配不能重复选择简历')
        return self


class RunAccepted(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    run_id: str = Field(alias='runId')
    status: RunStatus


class ActionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='forbid')
    decision: Literal['submit', 'approve', 'reject']
    answers: dict[str, str] = Field(default_factory=dict)
    expected_revision: int = Field(alias='expectedRevision', ge=1)
