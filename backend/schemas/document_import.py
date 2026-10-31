from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas.agent_runs import RunStatus


class DocumentImportAccepted(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    run_id: str = Field(alias="runId")
    status: RunStatus


class DocumentClassification(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    document_type: Literal["resume", "jd", "ambiguous"]
    confidence: Literal["high", "medium", "low"]
    reason: str = Field(min_length=1, max_length=160)
