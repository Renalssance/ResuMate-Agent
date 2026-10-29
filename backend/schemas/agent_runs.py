"""Canonical Run states and typed event payloads shared by API and worker."""
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator


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


RunEvent = Annotated[
    StatusEvent | DeltaEvent | ToolStartedEvent | ToolCompletedEvent | ToolFailedEvent
    | ActionEvent | ArtifactEvent | UsageEvent,
    Field(discriminator='type'),
]
RUN_EVENT_ADAPTER = TypeAdapter(RunEvent)


class RunCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='forbid', str_strip_whitespace=True)
    session_id: str | None = Field(default=None, alias='sessionId', min_length=1, max_length=36)
    kind: Literal['tailoring', 'resume_export']
    jd_id: int | None = Field(default=None, alias='jdId', gt=0)
    resume_id: int | None = Field(default=None, alias='resumeId', gt=0)
    resume_version_id: str | None = Field(default=None, alias='resumeVersionId', min_length=1, max_length=36)
    request_id: str = Field(alias='requestId', min_length=1, max_length=100)

    @model_validator(mode='after')
    def validate_inputs(self):
        if self.kind == 'tailoring':
            if self.jd_id is None or self.resume_id is None or 'resume_version_id' in self.model_fields_set:
                raise ValueError('准备材料需要岗位和简历，不能混用已确认版本')
        elif self.resume_version_id is None or {'jd_id', 'resume_id'} & self.model_fields_set:
            raise ValueError('导出需要已确认版本，不能混用原始简历或岗位')
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
