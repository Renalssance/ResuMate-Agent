from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.middleware.rate_limit import require_run_capacity
from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.db.models import User
from backend.schemas.agent_runs import RunCreate
from backend.schemas.jobs import JobCreate, JobStatus, JobUpdate
from backend.services import jobs
from backend.services.background_tasks import submit_task

router = APIRouter(prefix='/api/jobs', tags=['jobs'])


@router.post('')
def capture_job(request: JobCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row, created = jobs.capture_job(db, current_user.id, request)
    return {'job': jobs.job_record(db, row, detail=True), 'created': created}


@router.post('/capture')
def capture_page_job(request: JobCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row, created = jobs.capture_page_job(db, current_user.id, request)
    return {'job': jobs.job_record(db, row, detail=True), 'created': created}


@router.get('')
def list_jobs(query: str = '', status: JobStatus | None = None, limit: int = Query(20, ge=1, le=100),
              offset: int = Query(0, ge=0), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return jobs.list_jobs(db, current_user.id, query=query, status=status, limit=limit, offset=offset)


@router.get('/{job_id}')
def get_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return jobs.job_record(db, jobs.find_job(db, current_user.id, job_id), detail=True)


@router.patch('/{job_id}')
def update_job(job_id: int, request: JobUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return jobs.job_record(db, jobs.update_job(db, current_user.id, job_id, request), detail=True)


@router.get('/{job_id}/matches')
def list_matches(job_id: int, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                 current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return jobs.list_matches(db, current_user.id, job_id, limit=limit, offset=offset)


@router.post('/{job_id}/parse', status_code=202, dependencies=[Depends(require_run_capacity)])
def parse_job(job_id: int, task_id: str = Query(''),
              current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    jobs.find_job(db, current_user.id, job_id)
    return submit_task(db, current_user.id, RunCreate(kind='document_parse', request_id=task_id or str(uuid4()),
        document_id=f'jd:{job_id}', parse_mode='saved_job'), prefer='respond-async')
