from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.middleware.rate_limit import require_run_capacity
from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.db.models import User
from backend.routes.agent_runs import RunRoute
from backend.schemas.resume_versions import ResumeVersionConfirm, ResumeVersionExport, ResumeVersionUpdate
from backend.schemas.agent_runs import RunAccepted, RunCreate
from backend.services.agent_runs import create_run
from backend.services.run_delivery import publish_run
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


@router.post('/{version_id}/export', status_code=202, response_model=RunAccepted, dependencies=[Depends(require_run_capacity)])
def export(version_id: str, request: ResumeVersionExport,
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = create_run(db, user.id, RunCreate(kind='resume_export', resume_version_id=version_id,
                                           request_id=request.request_id))
    if run.status == 'queued':
        publish_run(run.id)
    return RunAccepted(run_id=run.id, status=run.status)
