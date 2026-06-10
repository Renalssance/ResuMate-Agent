import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.db.models import AnalysisCandidate, AnalysisJob, JobDescription, Resume, User
from backend.middleware.rate_limit import rate_limit
from backend.schemas import (
    AnalysisCandidateAddRequest,
    AnalysisCandidateAddResponse,
    AnalysisCandidateDeleteResponse,
    AnalysisCandidateInfo,
    AnalysisJobCreateRequest,
    AnalysisJobCreateResponse,
    AnalysisJobDeleteResponse,
    AnalysisJobDetailResponse,
    AnalysisJobInfo,
    AnalysisJobListResponse,
    AnalysisJobUpdateRequest,
    AnalysisResumeBatchUploadResponse,
    AnalysisResumeUploadResult,
)
from backend.services.resume_upload import create_resume_from_upload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["analysis"])

MAX_BATCH_RESUME_FILES = 20


def _candidate_name(resume: Resume | None) -> str:
    if not resume or not resume.structured_data:
        return ""
    return str(resume.structured_data.get("name") or "")


def _candidate_info(candidate: AnalysisCandidate) -> AnalysisCandidateInfo:
    resume = candidate.resume
    return AnalysisCandidateInfo(
        id=candidate.id,
        resume_id=candidate.resume_id,
        filename=resume.filename if resume else "",
        candidate_name=_candidate_name(resume),
        status=candidate.status,
        note=candidate.note,
        created_at=candidate.created_at.isoformat(),
        updated_at=candidate.updated_at.isoformat(),
    )


def _job_info(job: AnalysisJob) -> AnalysisJobInfo:
    return AnalysisJobInfo(
        id=job.id,
        title=job.title,
        jd_id=job.jd_id,
        jd_title=job.jd.title if job.jd else "",
        status=job.status,
        summary=job.summary,
        candidate_count=len(job.candidates or []),
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
    )


def _get_user_job(db: Session, job_id: int, user_id: int) -> AnalysisJob:
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id, AnalysisJob.user_id == user_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="分析任务不存在")
    return job


def _ensure_user_jd(db: Session, jd_id: int | None, user_id: int) -> JobDescription | None:
    if jd_id is None:
        return None
    jd = db.query(JobDescription).filter(JobDescription.id == jd_id, JobDescription.user_id == user_id).first()
    if not jd:
        raise HTTPException(status_code=404, detail="JD 不存在")
    return jd


def _error_detail(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    return str(exc)


@router.post(
    "/jobs",
    response_model=AnalysisJobCreateResponse,
    dependencies=[Depends(rate_limit("upload", 20, 60))],
)
async def create_analysis_job(
    request: AnalysisJobCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    logger.info(
        "Analysis job create start | user_id=%s title=%s jd_id=%s",
        current_user.id,
        request.title,
        request.jd_id,
    )
    jd = _ensure_user_jd(db, request.jd_id, current_user.id)
    title = (request.title or "").strip()
    if not title:
        title = f"{jd.title} 分析任务" if jd else "未命名分析任务"

    job = AnalysisJob(
        user_id=current_user.id,
        jd_id=request.jd_id,
        title=title,
        summary=(request.summary or "").strip(),
        config_json=request.config or {},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info("Analysis job created | user_id=%s job_id=%s title=%s jd_id=%s", current_user.id, job.id, job.title, job.jd_id)
    return AnalysisJobCreateResponse(id=job.id, title=job.title, jd_id=job.jd_id, message="分析任务创建成功")


@router.get(
    "/jobs",
    response_model=AnalysisJobListResponse,
    dependencies=[Depends(rate_limit("read", 60, 60))],
)
async def list_analysis_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    jobs = (
        db.query(AnalysisJob)
        .filter(AnalysisJob.user_id == current_user.id)
        .order_by(AnalysisJob.created_at.desc())
        .all()
    )
    return AnalysisJobListResponse(jobs=[_job_info(job) for job in jobs])


@router.get(
    "/jobs/{job_id}",
    response_model=AnalysisJobDetailResponse,
    dependencies=[Depends(rate_limit("read", 60, 60))],
)
async def get_analysis_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = _get_user_job(db, job_id, current_user.id)
    info = _job_info(job)
    return AnalysisJobDetailResponse(
        **info.model_dump(),
        config=job.config_json or {},
        candidates=[_candidate_info(candidate) for candidate in job.candidates],
    )


@router.patch(
    "/jobs/{job_id}",
    response_model=AnalysisJobDetailResponse,
    dependencies=[Depends(rate_limit("upload", 30, 60))],
)
async def update_analysis_job(
    job_id: int,
    request: AnalysisJobUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = _get_user_job(db, job_id, current_user.id)
    if request.jd_id is not None:
        _ensure_user_jd(db, request.jd_id, current_user.id)
        job.jd_id = request.jd_id
    if request.title is not None:
        title = request.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="任务标题不能为空")
        job.title = title
    if request.status is not None:
        job.status = request.status.strip() or job.status
    if request.summary is not None:
        job.summary = request.summary.strip()
    if request.config is not None:
        job.config_json = request.config

    db.commit()
    db.refresh(job)
    info = _job_info(job)
    return AnalysisJobDetailResponse(
        **info.model_dump(),
        config=job.config_json or {},
        candidates=[_candidate_info(candidate) for candidate in job.candidates],
    )


@router.delete("/jobs/{job_id}", response_model=AnalysisJobDeleteResponse)
async def delete_analysis_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = _get_user_job(db, job_id, current_user.id)
    db.delete(job)
    db.commit()
    return AnalysisJobDeleteResponse(id=job_id, message="分析任务已删除")


@router.post(
    "/jobs/{job_id}/candidates",
    response_model=AnalysisCandidateAddResponse,
    dependencies=[Depends(rate_limit("upload", 30, 60))],
)
async def add_analysis_candidates(
    job_id: int,
    request: AnalysisCandidateAddRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = _get_user_job(db, job_id, current_user.id)
    unique_resume_ids = list(dict.fromkeys(request.resume_ids))
    resumes = (
        db.query(Resume)
        .filter(Resume.user_id == current_user.id, Resume.id.in_(unique_resume_ids))
        .all()
    )
    resumes_by_id = {resume.id: resume for resume in resumes}
    missing_ids = [resume_id for resume_id in unique_resume_ids if resume_id not in resumes_by_id]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"简历不存在: {missing_ids}")

    existing_resume_ids = {
        resume_id
        for (resume_id,) in db.query(AnalysisCandidate.resume_id)
        .filter(AnalysisCandidate.job_id == job.id, AnalysisCandidate.resume_id.in_(unique_resume_ids))
        .all()
    }

    added: list[AnalysisCandidate] = []
    for resume_id in unique_resume_ids:
        if resume_id in existing_resume_ids:
            continue
        candidate = AnalysisCandidate(job_id=job.id, resume_id=resume_id)
        db.add(candidate)
        added.append(candidate)

    db.commit()
    for candidate in added:
        db.refresh(candidate)

    db.refresh(job)
    return AnalysisCandidateAddResponse(
        job_id=job.id,
        added_count=len(added),
        skipped_count=len(unique_resume_ids) - len(added),
        candidates=[_candidate_info(candidate) for candidate in job.candidates],
        message="候选人已加入分析任务",
    )


@router.post(
    "/jobs/{job_id}/resumes/upload",
    response_model=AnalysisResumeBatchUploadResponse,
    dependencies=[Depends(rate_limit("upload", 10, 60))],
)
async def upload_analysis_resumes(
    job_id: int,
    files: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload multiple resumes into one analysis job and attach them as candidates."""

    job = _get_user_job(db, job_id, current_user.id)
    logger.info(
        "Analysis batch resume upload start | user_id=%s job_id=%s files=%s",
        current_user.id,
        job_id,
        len(files) if files else 0,
    )
    if not files:
        raise HTTPException(status_code=400, detail="请至少上传一份简历")
    if len(files) > MAX_BATCH_RESUME_FILES:
        raise HTTPException(status_code=400, detail=f"单次最多上传 {MAX_BATCH_RESUME_FILES} 份简历")

    uploaded_count = 0
    failed_count = 0
    added_count = 0
    skipped_count = 0
    results: list[AnalysisResumeUploadResult] = []

    for file in files:
        original_filename = file.filename or ""
        logger.info("Analysis batch file start | user_id=%s job_id=%s filename=%s", current_user.id, job_id, original_filename)
        try:
            resume = await create_resume_from_upload(file=file, user_id=current_user.id, db=db)
            uploaded_count += 1
            logger.info(
                "Analysis batch file uploaded | user_id=%s job_id=%s resume_id=%s filename=%s",
                current_user.id,
                job_id,
                resume.id,
                resume.filename,
            )
        except Exception as exc:
            db.rollback()
            failed_count += 1
            logger.exception("Analysis batch file failed | user_id=%s job_id=%s filename=%s", current_user.id, job_id, original_filename)
            results.append(
                AnalysisResumeUploadResult(
                    filename=original_filename,
                    status="failed",
                    error=_error_detail(exc),
                )
            )
            continue

        existing_candidate = (
            db.query(AnalysisCandidate)
            .filter(AnalysisCandidate.job_id == job.id, AnalysisCandidate.resume_id == resume.id)
            .first()
        )
        if existing_candidate:
            skipped_count += 1
            results.append(
                AnalysisResumeUploadResult(
                    filename=resume.filename,
                    status="skipped",
                    resume_id=resume.id,
                    candidate_id=existing_candidate.id,
                    candidate_name=_candidate_name(resume),
                    error="候选人已在分析任务中",
                )
            )
            continue

        try:
            candidate = AnalysisCandidate(job_id=job.id, resume_id=resume.id)
            db.add(candidate)
            db.commit()
            db.refresh(candidate)
            added_count += 1
            logger.info(
                "Analysis candidate attached | user_id=%s job_id=%s candidate_id=%s resume_id=%s",
                current_user.id,
                job_id,
                candidate.id,
                resume.id,
            )
            results.append(
                AnalysisResumeUploadResult(
                    filename=resume.filename,
                    status="uploaded",
                    resume_id=resume.id,
                    candidate_id=candidate.id,
                    candidate_name=_candidate_name(resume),
                )
            )
        except Exception as exc:
            db.rollback()
            failed_count += 1
            results.append(
                AnalysisResumeUploadResult(
                    filename=resume.filename,
                    status="uploaded_attach_failed",
                    resume_id=resume.id,
                    candidate_name=_candidate_name(resume),
                    error=_error_detail(exc),
                )
            )

    db.refresh(job)
    logger.info(
        "Analysis batch resume upload completed | user_id=%s job_id=%s uploaded=%s failed=%s added=%s skipped=%s",
        current_user.id,
        job_id,
        uploaded_count,
        failed_count,
        added_count,
        skipped_count,
    )
    return AnalysisResumeBatchUploadResponse(
        job_id=job.id,
        uploaded_count=uploaded_count,
        failed_count=failed_count,
        added_count=added_count,
        skipped_count=skipped_count,
        results=results,
        candidates=[_candidate_info(candidate) for candidate in job.candidates],
        message="批量简历上传完成",
    )


@router.delete(
    "/jobs/{job_id}/candidates/{candidate_id}",
    response_model=AnalysisCandidateDeleteResponse,
)
async def delete_analysis_candidate(
    job_id: int,
    candidate_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = _get_user_job(db, job_id, current_user.id)
    candidate = (
        db.query(AnalysisCandidate)
        .filter(AnalysisCandidate.id == candidate_id, AnalysisCandidate.job_id == job.id)
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="候选人不存在")
    db.delete(candidate)
    db.commit()
    return AnalysisCandidateDeleteResponse(id=candidate_id, message="候选人已从分析任务移除")
