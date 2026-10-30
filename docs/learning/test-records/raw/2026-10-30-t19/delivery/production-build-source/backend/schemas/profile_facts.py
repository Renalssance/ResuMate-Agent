"""User-authored facts require an explicit confirmation on every revision."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class FactContent(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='forbid')
    content: dict
    confirmed: StrictBool = False

    @field_validator('content')
    @classmethod
    def require_text(cls, value):
        text = value.get('text')
        if not isinstance(text, str) or not text.strip():
            raise ValueError('事实需要非空文本')
        return {**value, 'text': text.strip()}


class FactCreate(FactContent):
    kind: Literal['preference', 'experience']
    source_document_id: int | None = Field(default=None, alias='sourceDocumentId', gt=0)


class FactUpdate(FactContent):
    expected_revision: int = Field(alias='expectedRevision', ge=1)
