from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.db.models import User
from backend.routes.agent_runs import RunRoute
from backend.schemas.resume_versions import ResumeVersionConfirm, ResumeVersionUpdate
from backend.services.resume_versions import confirm_version, get_version, update_version

router = APIRouter(prefix='/api/resume-versions', tags=['resume-versions'], route_class=RunRoute)


@router.get('/{version_id}')
def detail(version_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_version(db, user.id, version_id)


@router.patch('/{version_id}')
def update(version_id: str, request: ResumeVersionUpdate,
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return update_version(db, user.id, version_id, request)


@router.post('/{version_id}/confirm')
def confirm(version_id: str, request: ResumeVersionConfirm,
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return confirm_version(db, user.id, version_id, request)
