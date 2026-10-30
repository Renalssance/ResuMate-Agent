from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.db.models import User
from backend.schemas.settings import LlmSettingsResponse, LlmSettingsUpdate, LlmUsageDashboard
from backend.services.llm_settings import read_llm_settings, save_llm_settings
from backend.services.dashboard_cache import DashboardCache

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
async def get_llm_usage(request: Request, current_user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    resources = getattr(request.app.state, 'redis', None)
    cache = DashboardCache(resources.commands if resources else None,
                           resources.namespace if resources else '')
    user_id = current_user.id
    session_factory = sessionmaker(bind=db.get_bind())
    # Authentication opened a read transaction; release it before Redis waits.
    db.close()
    return await cache.usage_dashboard(user_id, session_factory)
