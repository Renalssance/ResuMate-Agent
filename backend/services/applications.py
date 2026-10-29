"""Freeze the confirmed material attached to an application; callers own commit."""
from copy import deepcopy
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.career_models import ResumeVersion
from backend.db.models import JobApplication, JobDescription
from backend.schemas.resume_versions import VersionStatus


def attach_submission(
    db: Session, user_id: int, application_id: int, jd_id: int, version_id: str,
) -> JobApplication:
    row = db.scalar(select(JobApplication).where(
        JobApplication.id == application_id, JobApplication.user_id == user_id))
    if row is None:
        raise HTTPException(status_code=404, detail='application not found')
    job = db.scalar(select(JobDescription).where(
        JobDescription.id == jd_id, JobDescription.user_id == user_id))
    if job is None:
        raise HTTPException(status_code=404, detail='job description not found')
    version = db.scalar(select(ResumeVersion).where(
        ResumeVersion.id == version_id, ResumeVersion.user_id == user_id))
    if version is None:
        raise HTTPException(status_code=404, detail='resume version not found')
    if version.status != VersionStatus.CONFIRMED:
        raise HTTPException(status_code=409, detail='请先确认简历版本，再关联投递')
    if version.jd_id != jd_id:
        raise HTTPException(status_code=409, detail='简历版本与投递岗位不一致')

    now = datetime.now(timezone.utc)
    snapshot = {
        'resumeVersionId': version.id,
        'revision': version.revision,
        'jdId': jd_id,
        'structuredContent': deepcopy(version.structured_content),
        'factRefs': deepcopy(version.fact_refs),
        'submittedAt': now.isoformat().replace('+00:00', 'Z'),
    }
    result = db.execute(update(JobApplication).where(
        JobApplication.id == application_id,
        JobApplication.user_id == user_id,
        JobApplication.submitted_snapshot.is_(None),
    ).values(jd_id=jd_id, resume_version_id=version_id, submitted_snapshot=snapshot,
             resume_id=version.resume_id, updated_at=now).execution_options(synchronize_session=False))
    # A locking read sees the winning write under MySQL's repeatable-read isolation.
    db.refresh(row, with_for_update=result.rowcount != 1)
    if row.jd_id != jd_id or row.resume_version_id != version_id:
        raise HTTPException(status_code=409, detail='此投递已关联提交材料，不能替换版本')
    return row
