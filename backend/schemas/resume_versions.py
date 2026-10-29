from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class VersionStatus(StrEnum):
    DRAFT = 'draft'
    CONFIRMED = 'confirmed'


class ResumeVersionUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='forbid')
    expected_revision: int = Field(alias='expectedRevision', ge=1)
    structured_content: dict[str, Any]
    fact_refs: list[str]
