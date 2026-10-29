from typing import Literal

from pydantic import Field, field_validator, model_validator

from backend.schemas.workflow import ApiModel

JobStatus = Literal['saved', 'archived']


class JobCreate(ApiModel):
    title: str = Field(min_length=1, max_length=255)
    company: str = Field(default='', max_length=255)
    text: str = Field(min_length=1)
    source_url: str | None = Field(default=None, alias='sourceUrl', max_length=1024)
    source_site: str | None = Field(default=None, alias='sourceSite', max_length=100)
    source_job_id: str | None = Field(default=None, alias='sourceJobId', max_length=255)
    primary_resume_id: int | None = Field(default=None, alias='primaryResumeId', gt=0)

    @field_validator('title', 'company', 'text', mode='before')
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('source_url', 'source_site', 'source_job_id', mode='before')
    @classmethod
    def empty_source_is_null(cls, value):
        return value.strip() or None if isinstance(value, str) else value

    @model_validator(mode='after')
    def source_pair(self):
        if bool(self.source_site) != bool(self.source_job_id):
            raise ValueError('sourceSite and sourceJobId must be provided together')
        return self


class JobUpdate(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    status: JobStatus | None = None
    primary_resume_id: int | None = Field(default=None, alias='primaryResumeId', gt=0)

    @field_validator('title', 'company', mode='before')
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode='after')
    def non_nullable_fields(self):
        for field in ('title', 'company', 'status'):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f'{field} cannot be null')
        return self
