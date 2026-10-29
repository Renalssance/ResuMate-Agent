from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator


class VersionStatus(StrEnum):
    DRAFT = 'draft'
    CONFIRMED = 'confirmed'


class ResumeVersionUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='forbid')
    expected_revision: int = Field(alias='expectedRevision', ge=1)
    structured_content: dict[str, Any]
    fact_refs: list[str]


class SourceModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='forbid')


class ProfileFactSource(SourceModel):
    kind: Literal['profile_fact']
    fact_id: str = Field(alias='factId', min_length=1)
    revision: int = Field(ge=1)


class ResumeSource(SourceModel):
    kind: Literal['resume']
    resume_id: int = Field(alias='resumeId', gt=0)
    input_version: str = Field(alias='inputVersion', min_length=1)
    section: str = Field(min_length=1)
    source_refs: list[Any] = Field(alias='sourceRefs')


class ApplicantAnswerSource(SourceModel):
    kind: Literal['applicant_answer']
    action_id: str = Field(alias='actionId', min_length=1)


EvidenceSource = Annotated[ProfileFactSource | ResumeSource | ApplicantAnswerSource, Field(discriminator='kind')]


class ResumeChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    section: str
    before: str
    after: str | None
    reason: str = Field(min_length=1)
    fact_refs: list[EvidenceSource]
    requires_input: StrictBool

    @model_validator(mode='after')
    def valid_suggestion(self):
        if not self.reason.strip():
            raise ValueError('建议需要说明理由')
        if self.requires_input:
            if self.after is not None:
                raise ValueError('待补充信息不能填写猜测内容')
        elif self.after is None or not self.fact_refs:
            raise ValueError('修改建议需要正文和事实来源')
        return self
