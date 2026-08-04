from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.db.models import Resume, User
from backend.schemas.autofill import (
    ApplicationProfile,
    ApplicationProfileSummary,
    AutofillEventRequest,
    AutofillEventResponse,
    AutofillMatchRequest,
    AutofillMatchResponse,
)
from backend.services.autofill import build_application_profile, flatten_application_fields, match_application_fields

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/autofill", tags=["autofill"])
SAFE_ELEMENT_KEYS = {"index", "tag", "type", "id", "name", "placeholder", "labelText", "ariaLabel", "nearbyText"}
MAX_LOG_VALUE_LENGTH = 160


def _resume_id(profile_id: str) -> int:
    prefix, _, raw_id = profile_id.partition(":")
    if prefix != "resume" or not raw_id.isdigit():
        raise HTTPException(status_code=404, detail="profile not found")
    return int(raw_id)


def _find_resume(db: Session, user_id: int, profile_id: str) -> Resume:
    row = db.query(Resume).filter(Resume.id == _resume_id(profile_id), Resume.user_id == user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="profile not found")
    return row


def _safe_element_summary(element: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key in SAFE_ELEMENT_KEYS:
        if key not in element:
            continue
        value = element[key]
        if key == "index":
            try:
                safe[key] = int(value)
            except (TypeError, ValueError):
                continue
            continue
        if isinstance(value, (dict, list, tuple, set)):
            continue
        safe[key] = str(value)[:MAX_LOG_VALUE_LENGTH]
    return safe


@router.get("/profiles", response_model=list[ApplicationProfileSummary])
def list_profiles(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Resume).filter(Resume.user_id == current_user.id).order_by(Resume.updated_at.desc()).all()
    summaries: list[ApplicationProfileSummary] = []
    for row in rows:
        profile = build_application_profile(row)
        summaries.append(
            ApplicationProfileSummary(
                id=profile.id,
                name=profile.name,
                source_resume_id=profile.source_resume_id,
                updated_at=profile.updated_at,
                field_count=len([field for field in flatten_application_fields(profile) if field.value]),
            )
        )
    return summaries


@router.get("/profiles/{profile_id}", response_model=ApplicationProfile)
def get_profile(profile_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return build_application_profile(_find_resume(db, current_user.id, profile_id))


@router.post("/match", response_model=AutofillMatchResponse)
def match_fields(
    request: AutofillMatchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = request.profile
    if profile is None:
        if not request.profile_id:
            raise HTTPException(status_code=422, detail="profile or profileId is required")
        profile = build_application_profile(_find_resume(db, current_user.id, request.profile_id))
    return match_application_fields(profile, request.elements)


@router.post("/events", response_model=AutofillEventResponse)
def record_event(request: AutofillEventRequest, current_user: User = Depends(get_current_user)):
    safe_elements = [_safe_element_summary(element) for element in request.element_summaries]
    logger.info(
        "Autofill event | user_id=%s type=%s status=%s profile_id=%s fields=%s elements=%s error_count=%s",
        current_user.id,
        request.event_type,
        request.status,
        request.profile_id,
        request.field_keys,
        safe_elements,
        len(request.errors),
    )
    return AutofillEventResponse(ok=True)
