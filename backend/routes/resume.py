import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from backend.middleware.rate_limit import rate_limit
from backend.auth.security import get_current_user
from backend.schemas import (
    ResumeDeleteResponse,
    ResumeDetailResponse,
    ResumeInfo,
    ResumeListResponse,
    ResumeUploadResponse,
)
from backend.db.database import SessionLocal
from backend.db.models import User, Resume
from backend.vector import vector_store
from backend.services.resume_upload import create_resume_from_upload

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/resume/upload", response_model=ResumeUploadResponse, dependencies=[Depends(rate_limit("upload", 5, 60))])
async def upload_resume(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    """上传简历文件并解析"""
    db = SessionLocal()
    try:
        resume = await create_resume_from_upload(file=file, user_id=current_user.id, db=db)
        return ResumeUploadResponse(id=resume.id, filename=resume.filename, message="简历上传、解析并写入向量库成功")
    finally:
        db.close()


@router.get("/resume", response_model=ResumeListResponse, dependencies=[Depends(rate_limit("read", 30, 60))])
async def list_resumes(current_user: User = Depends(get_current_user)):
    """获取当前用户的简历列表"""
    db = SessionLocal()
    try:
        resumes = (
            db.query(Resume)
            .filter(Resume.user_id == current_user.id)
            .order_by(Resume.created_at.desc())
            .all()
        )
        return ResumeListResponse(
            resumes=[
                ResumeInfo(
                    id=r.id,
                    filename=r.filename,
                    structured_data=r.structured_data,
                    created_at=r.created_at.isoformat(),
                    updated_at=r.updated_at.isoformat(),
                )
                for r in resumes
            ]
        )
    finally:
        db.close()


@router.get("/resume/{resume_id}", response_model=ResumeDetailResponse, dependencies=[Depends(rate_limit("read", 30, 60))])
async def get_resume(resume_id: int, current_user: User = Depends(get_current_user)):
    """获取简历详情"""
    db = SessionLocal()
    try:
        resume = (
            db.query(Resume)
            .filter(Resume.id == resume_id, Resume.user_id == current_user.id)
            .first()
        )
        if not resume:
            raise HTTPException(status_code=404, detail="简历不存在")
        return ResumeDetailResponse(
            id=resume.id,
            filename=resume.filename,
            raw_text=resume.raw_text,
            structured_data=resume.structured_data,
            created_at=resume.created_at.isoformat(),
            updated_at=resume.updated_at.isoformat(),
        )
    finally:
        db.close()


@router.delete("/resume/{resume_id}", response_model=ResumeDeleteResponse)
async def delete_resume(resume_id: int, current_user: User = Depends(get_current_user)):
    """删除简历"""
    db = SessionLocal()
    try:
        resume = (
            db.query(Resume)
            .filter(Resume.id == resume_id, Resume.user_id == current_user.id)
            .first()
        )
        if not resume:
            raise HTTPException(status_code=404, detail="简历不存在")
        try:
            vector_store.delete_profile(doc_type="resume", user_id=current_user.id, source_id=resume.id)
        except Exception as e:
            logger.warning("删除简历向量失败，继续删除数据库记录: %s", e)
        db.delete(resume)
        db.commit()
        return ResumeDeleteResponse(id=resume_id, message="简历已删除")
    finally:
        db.close()
