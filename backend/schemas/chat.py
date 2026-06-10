from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = Field(default="default_session", max_length=120)
