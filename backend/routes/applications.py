from datetime import datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.db.models import JobApplication, JobApplicationSchedule, JobApplicationStatusEvent, Resume, User
from backend.schemas.applications import (
    ApplicationCreate,
    ApplicationRecord,
    ApplicationScheduleCreate,
    ApplicationStatusEventCreate,
    ApplicationUpdate,
)

router = APIRouter(prefix="/api/applications", tags=["applications"])


def _find_application(db: Session, user_id: int, application_id: int) -> JobApplication:
    row = (
        db.query(JobApplication)
        .filter(JobApplication.id == application_id, JobApplication.user_id == user_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="application not found")
    return row


def _find_resume(db: Session, user_id: int, resume_id: int | None) -> Resume | None:
    if resume_id is None:
        return None
    row = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="resume not found")
    return row


def _record(row: JobApplication) -> ApplicationRecord:
    status_events = sorted(row.status_events, key=lambda event: _as_utc(event.changed_at), reverse=True)
    schedules = sorted(row.schedules, key=lambda schedule: _as_utc(schedule.starts_at))
    return ApplicationRecord(
        id=row.id,
        company=row.company,
        position=row.position,
        applied_date=row.applied_date,
        resume_id=row.resume_id,
        resume_filename=row.resume.filename if row.resume else "",
        status=row.status,
        job_url=row.job_url,
        source=row.source,
        notes=row.notes,
        status_events=status_events,
        schedules=schedules,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _append_status_event(
    db: Session,
    row: JobApplication,
    status: str,
    *,
    changed_at: datetime | None = None,
    note: str = "",
    touch_application: bool = True,
) -> None:
    changed_at = changed_at or datetime.now(timezone.utc)
    row.status = status
    if touch_application:
        row.updated_at = changed_at
    db.add(JobApplicationStatusEvent(application_id=row.id, status=status, changed_at=changed_at, note=note))


def _archive_finished_schedules(db: Session, user_id: int, now: datetime) -> bool:
    schedules = (
        db.query(JobApplicationSchedule)
        .join(JobApplication)
        .filter(
            JobApplication.user_id == user_id,
            JobApplicationSchedule.completed_event_id.is_(None),
        )
        .all()
    )
    changed = False
    now = _as_utc(now)
    for schedule in schedules:
        if _as_utc(schedule.ends_at) > now:
            continue
        note = f"日程完成：{schedule.title}"
        if schedule.note:
            note = f"{note}（{schedule.note}）"
        event = JobApplicationStatusEvent(
            application_id=schedule.application_id,
            status=schedule.status,
            changed_at=schedule.ends_at,
            note=note,
        )
        schedule.application.status = schedule.status
        schedule.application.updated_at = now
        schedule.updated_at = now
        db.add(event)
        db.flush()
        schedule.completed_event_id = event.id
        changed = True
    return changed


def _sync_applied_applications_with_schedules(db: Session, user_id: int, now: datetime) -> bool:
    schedules = (
        db.query(JobApplicationSchedule)
        .join(JobApplication)
        .filter(
            JobApplication.user_id == user_id,
            JobApplication.status == "applied",
            JobApplicationSchedule.completed_event_id.is_(None),
        )
        .order_by(JobApplicationSchedule.starts_at.asc(), JobApplicationSchedule.id.asc())
        .all()
    )
    changed = False
    seen_application_ids: set[int] = set()
    for schedule in schedules:
        if schedule.application_id in seen_application_ids:
            continue
        schedule.application.status = schedule.status
        schedule.application.updated_at = now
        seen_application_ids.add(schedule.application_id)
        changed = True
    return changed


@router.get("", response_model=list[ApplicationRecord])
def list_applications(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    schedules_archived = _archive_finished_schedules(db, current_user.id, now)
    schedules_synced = _sync_applied_applications_with_schedules(db, current_user.id, now)
    if schedules_archived or schedules_synced:
        db.commit()
    rows = (
        db.query(JobApplication)
        .filter(JobApplication.user_id == current_user.id)
        .order_by(JobApplication.applied_date.desc(), JobApplication.created_at.desc())
        .all()
    )
    return [_record(row) for row in rows]


@router.post("", response_model=ApplicationRecord)
def create_application(
    request: ApplicationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _find_resume(db, current_user.id, request.resume_id)
    row = JobApplication(user_id=current_user.id, **request.model_dump())
    db.add(row)
    db.flush()
    _append_status_event(
        db,
        row,
        request.status,
        changed_at=datetime.combine(request.applied_date, time(), timezone.utc),
        touch_application=False,
    )
    db.commit()
    db.refresh(row)
    return _record(row)


@router.patch("/{application_id}", response_model=ApplicationRecord)
def update_application(
    application_id: int,
    request: ApplicationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _find_application(db, current_user.id, application_id)
    data = request.model_dump(exclude_unset=True)
    if "resume_id" in data:
        _find_resume(db, current_user.id, data["resume_id"])
    status = data.pop("status", None)
    for field, value in data.items():
        setattr(row, field, value)
    if status and status != row.status:
        _append_status_event(db, row, status)
    else:
        row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _record(row)


@router.post("/{application_id}/status-events", response_model=ApplicationRecord)
def create_status_event(
    application_id: int,
    request: ApplicationStatusEventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _find_application(db, current_user.id, application_id)
    _append_status_event(db, row, request.status, changed_at=request.changed_at, note=request.note)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _record(row)


@router.post("/{application_id}/schedules", response_model=ApplicationRecord)
def create_schedule(
    application_id: int,
    request: ApplicationScheduleCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _find_application(db, current_user.id, application_id)
    schedule = JobApplicationSchedule(application_id=row.id, **request.model_dump())
    db.add(schedule)
    row.status = request.status
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _record(row)


@router.delete("/{application_id}")
def delete_application(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _find_application(db, current_user.id, application_id)
    db.delete(row)
    db.commit()
    return {"id": application_id}
