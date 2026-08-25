from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LlmSettingsUpdate(BaseModel):
    api_key: str | None = None
    clear_api_key: bool = False
    base_url: str | None = None
    model: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    request_timeout_seconds: float | None = Field(default=None, ge=1)


class LlmSettingsResponse(BaseModel):
    has_api_key: bool
    api_key_hint: str
    base_url: str
    model: str
    max_tokens: int
    request_timeout_seconds: float


class LlmUsageDailyPoint(BaseModel):
    date: str
    calls: int
    total_tokens: int


class LlmUsageTaskPoint(BaseModel):
    task: str
    calls: int
    total_tokens: int


class LlmUsageCall(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task: str
    model: str
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    success: bool
    error_type: str
    elapsed_ms: int
    called_at: datetime


class LlmUsageDashboard(BaseModel):
    total_calls: int
    successful_calls: int
    failed_calls: int
    success_rate: int
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    last_called_at: datetime | None
    daily: list[LlmUsageDailyPoint]
    by_task: list[LlmUsageTaskPoint]
    recent_calls: list[LlmUsageCall]
