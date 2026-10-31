from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DocumentClassification(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    document_type: Literal["resume", "jd", "ambiguous"]
    confidence: Literal["high", "medium", "low"]
    reason: str = Field(min_length=1, max_length=160)
