from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.db.models import User
from backend.schemas.settings import LlmSettingsResponse, LlmSettingsUpdate, LlmUsageDashboard
from backend.services.llm_settings import read_llm_settings, save_llm_settings, usage_dashboard

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/llm", response_model=LlmSettingsResponse)
def get_llm_settings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return read_llm_settings(current_user.id, db)


@router.put("/llm", response_model=LlmSettingsResponse)
def update_llm_settings(
    request: LlmSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return save_llm_settings(current_user.id, request, db)


@router.get("/usage", response_model=LlmUsageDashboard)
def get_llm_usage(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return usage_dashboard(current_user.id, db)
