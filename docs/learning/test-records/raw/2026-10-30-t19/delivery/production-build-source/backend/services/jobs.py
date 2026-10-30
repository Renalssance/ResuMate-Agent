"""Saved jobs use the existing JD and matching records."""
from datetime import timezone

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import AnalysisJob, JobDescription, MatchResult, Resume, utcnow
from backend.schemas.jobs import JobCreate, JobUpdate


def find_job(db: Session, user_id: int, job_id: int) -> JobDescription:
    row = db.query(JobDescription).filter_by(id=job_id, user_id=user_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail='job not found')
    return row


def find_resume(db: Session, user_id: int, resume_id: int | None) -> Resume | None:
    if resume_id is None:
        return None
    row = db.query(Resume).filter_by(id=resume_id, user_id=user_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail='resume not found')
    return row


def _iso(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.isoformat()


def job_record(db: Session, row: JobDescription, *, detail=False) -> dict:
    result = {
        'id': row.id, 'title': row.title, 'company': row.company,
        'sourceUrl': row.source_url, 'sourceSite': row.source_site, 'sourceJobId': row.source_job_id,
        'capturedAt': _iso(row.captured_at), 'status': row.status,
        'primaryResumeId': row.primary_resume_id, 'parseStatus': row.parse_status,
        'createdAt': _iso(row.created_at), 'updatedAt': _iso(row.updated_at),
    }
    if detail:
        resume = find_resume(db, row.user_id, row.primary_resume_id)
        result.update(text=row.raw_text, structuredContent=row.structured_data,
                      primaryResume={'id': resume.id, 'filename': resume.filename} if resume else None)
    return result


def capture_job(db: Session, user_id: int, source: JobCreate) -> tuple[JobDescription, bool]:
    find_resume(db, user_id, source.primary_resume_id)
    query = db.query(JobDescription).filter(JobDescription.user_id == user_id)
    if source.source_site:
        query = query.filter_by(source_site=source.source_site, source_job_id=source.source_job_id)
    else:
        # MySQL's default collation may ignore case; pasted text dedup is exact.
        body = JobDescription.raw_text
        source_url = JobDescription.source_url
        if db.get_bind().dialect.name == 'mysql':
            body = body.collate('utf8mb4_bin')
            source_url = source_url.collate('utf8mb4_bin')
        query = query.filter(JobDescription.source_site.is_(None), JobDescription.source_job_id.is_(None),
                             source_url == source.source_url, body == source.text)
    existing = query.order_by(JobDescription.id).first()
    if existing:
        return existing, False
    row = JobDescription(user_id=user_id, title=source.title, company=source.company,
                         raw_text=source.text, source_url=source.source_url, source_site=source.source_site,
                         source_job_id=source.source_job_id, primary_resume_id=source.primary_resume_id,
                         captured_at=utcnow(), document_size=len(source.text.encode('utf-8')))
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # The existing unique source key also covers two simultaneous imports.
        existing = query.first() if source.source_site else None
        if existing is None:
            raise
        return existing, False
    db.refresh(row)
    return row, True


def capture_page_job(db: Session, user_id: int, source: JobCreate) -> tuple[JobDescription, bool]:
    """A page capture keeps the first saved posting when its visible text changes."""
    if source.source_site or not source.source_url:
        return capture_job(db, user_id, source)
    find_resume(db, user_id, source.primary_resume_id)
    source_url = JobDescription.source_url
    if db.get_bind().dialect.name == 'mysql':
        source_url = source_url.collate('utf8mb4_bin')
    existing = (db.query(JobDescription)
                .filter(JobDescription.user_id == user_id, source_url == source.source_url)
                .order_by(JobDescription.id).first())
    if existing:
        return existing, False
    return capture_job(db, user_id, source)


def list_jobs(db: Session, user_id: int, *, query: str, status: str | None, limit: int, offset: int):
    rows = db.query(JobDescription).filter(JobDescription.user_id == user_id)
    if query.strip():
        rows = rows.filter(or_(JobDescription.title.contains(query.strip(), autoescape=True),
                               JobDescription.company.contains(query.strip(), autoescape=True)))
    if status:
        rows = rows.filter(JobDescription.status == status)
    items = rows.order_by(func.coalesce(JobDescription.captured_at, JobDescription.created_at).desc(),
                          JobDescription.id.desc()).offset(offset).limit(limit + 1).all()
    return {'items': [job_record(db, row) for row in items[:limit]], 'hasMore': len(items) > limit}


def update_job(db: Session, user_id: int, job_id: int, request: JobUpdate):
    row = find_job(db, user_id, job_id)
    if 'primary_resume_id' in request.model_fields_set:
        find_resume(db, user_id, request.primary_resume_id)
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def list_matches(db: Session, user_id: int, job_id: int, *, limit: int, offset: int):
    find_job(db, user_id, job_id)
    items = (db.query(MatchResult).join(AnalysisJob, AnalysisJob.id == MatchResult.job_id)
             .filter(MatchResult.jd_id == job_id, AnalysisJob.user_id == user_id)
             .order_by(MatchResult.created_at.desc(), MatchResult.id.desc()).offset(offset).limit(limit + 1).all())
    return {'items': [{'runId': row.job_id, 'candidateId': row.candidate_id, 'resumeId': row.resume_id,
                       'score': row.overall_score, 'createdAt': _iso(row.created_at)} for row in items[:limit]],
            'hasMore': len(items) > limit}
