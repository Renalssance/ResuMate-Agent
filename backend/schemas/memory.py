"""Only explicitly confirmed manual business memory is accepted."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class MemoryCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['preference', 'interview_feedback']
    content: str = Field(min_length=1, max_length=4000)
    confirmed: StrictBool

    @field_validator('content')
    @classmethod
    def require_content(cls, value):
        if not value.strip():
            raise ValueError('记忆需要非空文本')
        return value.strip()

    @field_validator('confirmed')
    @classmethod
    def require_confirmation(cls, value):
        if not value:
            raise ValueError('请先明确确认这条记忆')
        return value
