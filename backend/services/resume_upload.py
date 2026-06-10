import logging
import os
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.agent.interview_tools import RESUME_PARSE_PROMPT, _get_llm, _invoke_llm, _parse_llm_json
from backend.db.models import Resume
from backend.rag.document_loader import DocumentLoader
from backend.services.pdf_ocr import extract_pdf_text_with_ocr, looks_like_scanned_pdf, ocr_enabled
from backend.vector import vector_store

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR.parent / "data"
RESUME_DIR = DATA_DIR / "resumes"
MAX_RESUME_SIZE = 10 * 1024 * 1024
SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".doc")

loader = DocumentLoader()


def _is_pdf(filename: str) -> bool:
    return filename.lower().endswith(".pdf")


def _safe_resume_filename(filename: str) -> str:
    if not filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    safe_name = os.path.basename(filename)
    if not safe_name or safe_name.startswith("."):
        raise HTTPException(status_code=400, detail="无效的文件名")

    if not safe_name.lower().endswith(SUPPORTED_EXTENSIONS):
        raise HTTPException(status_code=400, detail="仅支持 PDF 和 Word 格式的简历")

    return safe_name


def _dedupe_storage_path(directory: Path, filename: str) -> tuple[Path, str]:
    path = directory / filename
    if not path.exists():
        return path, filename

    stem = path.stem
    suffix = path.suffix
    counter = 1
    while True:
        candidate_name = f"{stem}_{counter}{suffix}"
        candidate_path = directory / candidate_name
        if not candidate_path.exists():
            return candidate_path, candidate_name
        counter += 1


def _parse_resume_text(raw_text: str) -> dict | None:
    llm = _get_llm()
    if not llm:
        logger.warning("Skip resume structured parsing because LLM is unavailable")
        return None

    try:
        prompt = RESUME_PARSE_PROMPT.format(text=raw_text[:5000])
        resp_content = _invoke_llm(
            llm,
            prompt,
            "service.resume_upload.parse_resume",
            {"raw_text_chars": len(raw_text)},
        )
        return _parse_llm_json(resp_content)
    except Exception as e:
        logger.warning("简历结构化解析失败: %s", e)
        return None


async def create_resume_from_upload(
    *,
    file: UploadFile,
    user_id: int,
    db: Session,
) -> Resume:
    """Persist one uploaded resume and write its profile vector."""

    filename = _safe_resume_filename(file.filename or "")
    logger.info("Resume upload start | user_id=%s filename=%s", user_id, filename)
    RESUME_DIR.mkdir(parents=True, exist_ok=True)

    content = await file.read(MAX_RESUME_SIZE + 1)
    logger.info("Resume upload read file | user_id=%s filename=%s bytes=%s", user_id, filename, len(content))
    if len(content) > MAX_RESUME_SIZE:
        raise HTTPException(status_code=413, detail="简历文件过大，最大支持 10MB")

    file_path, stored_filename = _dedupe_storage_path(RESUME_DIR, filename)
    with open(file_path, "wb") as f:
        f.write(content)
    logger.info("Resume file saved | user_id=%s filename=%s path=%s", user_id, stored_filename, file_path)

    try:
        docs = loader.load_document(str(file_path), stored_filename)
        raw_text = "\n".join(d.get("text", "") for d in docs)
        logger.info(
            "Resume text extracted | user_id=%s filename=%s docs=%s chars=%s",
            user_id,
            stored_filename,
            len(docs),
            len(raw_text),
        )
    except Exception as e:
        file_path.unlink(missing_ok=True)
        logger.exception("Resume text extraction failed | user_id=%s filename=%s", user_id, stored_filename)
        raise HTTPException(status_code=500, detail=f"简历文件解析失败: {e}") from e

    if _is_pdf(stored_filename) and looks_like_scanned_pdf(raw_text):
        if not ocr_enabled():
            file_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=422,
                detail="检测到扫描版或图片版 PDF，但 PDF OCR 当前未启用。请设置 PDF_OCR_ENABLED=true 或上传可复制文字的 PDF/Word。",
            )
        logger.info("检测到扫描版或图片版 PDF，开始 OCR: %s", stored_filename)
        try:
            ocr_result = extract_pdf_text_with_ocr(file_path)
            raw_text = ocr_result.text
            logger.info(
                "Resume OCR completed | user_id=%s filename=%s pages=%s ocr_pages=%s chars=%s",
                user_id,
                stored_filename,
                ocr_result.page_count,
                ocr_result.ocr_page_count,
                len(raw_text),
            )
        except Exception as e:
            file_path.unlink(missing_ok=True)
            logger.exception("PDF OCR 识别失败: %s", e)
            raise HTTPException(status_code=500, detail=f"PDF OCR 识别失败: {e}") from e

    if not raw_text.strip():
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=422,
            detail="无法从简历中提取文本内容。请上传清晰的 PDF/Word；如果是扫描版或图片版 PDF，请确认图片清晰且 OCR 已启用。",
        )

    structured_data = _parse_resume_text(raw_text)
    logger.info(
        "Resume structured parsing completed | user_id=%s filename=%s parsed=%s",
        user_id,
        stored_filename,
        bool(structured_data),
    )

    try:
        resume = Resume(
            user_id=user_id,
            filename=stored_filename,
            file_path=str(file_path),
            raw_text=raw_text[:10000],
            structured_data=structured_data,
        )
        db.add(resume)
        db.flush()
        vector_store.upsert_resume(
            user_id=user_id,
            resume_id=resume.id,
            filename=stored_filename,
            structured_data=structured_data,
            raw_text=raw_text,
        )
        logger.info("Resume vector upsert completed | user_id=%s resume_id=%s filename=%s", user_id, resume.id, stored_filename)
        db.commit()
        db.refresh(resume)
        logger.info("Resume upload completed | user_id=%s resume_id=%s filename=%s", user_id, resume.id, stored_filename)
        return resume
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception("简历保存或向量入库失败: %s", e)
        raise HTTPException(status_code=500, detail=f"简历保存失败: {e}") from e
