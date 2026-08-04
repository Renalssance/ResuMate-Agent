from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


Confidence = Literal["high", "medium", "low"]
AutofillEventType = Literal["scan", "match", "fill"]
AutofillEventStatus = Literal["success", "partial", "failed"]


class AutofillModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class ApplicationField(AutofillModel):
    key: str
    label: str
    value: str = ""
    aliases: list[str] = Field(default_factory=list)
    category: str = "general"
    confidence: Confidence = "medium"
    source: str = "resume"


class ApplicationSection(AutofillModel):
    id: str
    label: str
    fields: list[ApplicationField] = Field(default_factory=list)


class ApplicationProfile(AutofillModel):
    id: str
    name: str
    source_resume_id: str = Field(alias="sourceResumeId")
    updated_at: str = Field(alias="updatedAt")
    sections: list[ApplicationSection] = Field(default_factory=list)


class ApplicationProfileSummary(AutofillModel):
    id: str
    name: str
    source_resume_id: str = Field(alias="sourceResumeId")
    updated_at: str = Field(alias="updatedAt")
    field_count: int = Field(alias="fieldCount", ge=0)


class PageElement(AutofillModel):
    index: int = Field(ge=0)
    tag: str
    type: str = ""
    id: str = ""
    name: str = ""
    placeholder: str = ""
    label_text: str = Field(default="", alias="labelText")
    aria_label: str = Field(default="", alias="ariaLabel")
    nearby_text: str = Field(default="", alias="nearbyText")
    value: str = ""


class PageContext(AutofillModel):
    url: str = ""
    title: str = ""
    company: str = ""
    position: str = ""
    confidence: dict[str, str] = Field(default_factory=dict)


class AutofillMatchRequest(AutofillModel):
    profile: ApplicationProfile | None = None
    profile_id: str = Field(default="", alias="profileId")
    page: PageContext = Field(default_factory=PageContext)
    elements: list[PageElement] = Field(default_factory=list)


class MatchSuggestion(AutofillModel):
    field_key: str = Field(alias="fieldKey")
    element_index: int = Field(alias="elementIndex", ge=0)
    confidence: Confidence
    reason: str
    field: ApplicationField
    element: PageElement


class BlockedElement(AutofillModel):
    element_index: int = Field(alias="elementIndex", ge=0)
    reason: str
    element: PageElement


class AutofillMatchResponse(AutofillModel):
    matches: list[MatchSuggestion] = Field(default_factory=list)
    blocked: list[BlockedElement] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AutofillEventRequest(AutofillModel):
    event_type: AutofillEventType = Field(alias="eventType")
    status: AutofillEventStatus
    page: PageContext = Field(default_factory=PageContext)
    profile_id: str = Field(default="", alias="profileId")
    field_keys: list[str] = Field(default_factory=list, alias="fieldKeys")
    element_summaries: list[dict[str, Any]] = Field(default_factory=list, alias="elementSummaries")
    errors: list[str] = Field(default_factory=list)


class AutofillEventResponse(AutofillModel):
    ok: bool = True
