from __future__ import annotations

from pathlib import Path

import anyio
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from backend.agents.harness import AgentHarness
from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.db.models import JobDescription, Resume, User
from backend.rag.milvus import MilvusRagStore
from backend.schemas.workflow import (
    DocumentParseResponse,
    DocumentParseResult,
    DocumentType,
    FollowUpAnalysisRequest,
    FollowUpAnalysisResponse,
    JobProfile,
    ResumeProfile,
)
from backend.services.analysis import parse_document_id
from backend.services.documents import (
    chunk_pages,
    delete_stored_file,
    detect_multiple_positions,
    extract_stored_pages,
    store_upload,
)
from backend.services.llm_validation import validate_resume_source_refs
from backend.services.progress import progress_hub
from backend.services.resume_postprocess import postprocess_resume_profile

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _record(document_type: str, row) -> DocumentParseResult:
    succeeded = str(row.parse_status or "") in {"success", "success_with_warnings"}
    return DocumentParseResult(
        id=f"{document_type}:{row.id}",
        type=document_type,
        filename=row.filename if document_type == "resume" else (row.filename or row.title),
        size=row.document_size,
        raw_text=row.raw_text,
        parsed_content=row.structured_data or {},
        parse_status=row.parse_status,
        created_at=row.created_at.isoformat(),
        vectorized=succeeded,
        local_stored=bool(row.file_path),
    )


def _find_document(db: Session, user_id: int, document_id: str):
    kind = document_id.partition(":")[0]
    record_id = parse_document_id(document_id, kind)
    model = Resume if kind == "resume" else JobDescription if kind == "jd" else None
    if model is None:
        raise ValueError("invalid document id")
    row = db.query(model).filter(model.id == record_id, model.user_id == user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="document not found")
    return kind, row


def _parse_profile(kind: DocumentType, filename: str, raw_text: str, chunks):
    harness = AgentHarness()
    if kind == "jd":
        if detect_multiple_positions(raw_text):
            raise ValueError("MULTIPLE_POSITIONS_DETECTED: please split the JD before parsing")
        profile = harness.run_schema(
            task="document.parse_jd", prompt_name="parse_jd", schema=JobProfile,
            variables={"jd_text": raw_text[:24000]},
        )
        content = profile.model_dump(mode="json")
        content["title"] = profile.job_title
        return content
    payload = [
        {"chunk_id": chunk.id, "page_number": chunk.page_number, "section": chunk.section, "text": chunk.text}
        for chunk in chunks
    ]
    profile = harness.run_schema(
        task="document.parse_resume", prompt_name="parse_resume", schema=ResumeProfile,
        variables={"filename": filename, "chunks_json": payload},
    )
    profile = postprocess_resume_profile(profile, chunks)
    validate_resume_source_refs(profile, chunks)
    content = profile.model_dump(mode="json")
    content["name"] = profile.candidate_name
    return content


def _parse_status(kind: DocumentType, content: dict) -> str:
    if kind != "resume":
        return "success"
    quality = content.get("quality") if isinstance(content, dict) else {}
    status = quality.get("status") if isinstance(quality, dict) else ""
    return str(status or "success")


@router.post("", response_model=DocumentParseResponse)
def upload_documents(
    document_type: DocumentType = Form(...),
    files: list[UploadFile] = File(...),
    task_id: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if len(files) != 1:
        raise HTTPException(status_code=422, detail="exactly one file is required per document parsing task")
    task_id = task_id or progress_hub.create_task("task_parse")
    results = []
    for file in files:
        stored = None
        row = None
        rag_store = None
        try:
            stored = anyio.from_thread.run(store_upload, file)
            progress_hub.publish(
                task_id,
                stage="server_save",
                status="running",
                progress=12,
                filename=stored.filename,
                message=f"Saved {stored.filename} on server",
                data={"filename": stored.filename, "size": stored.size},
            )
            pages = extract_stored_pages(
                stored.path,
                stored.filename,
                progress_callback=lambda current, total: progress_hub.publish(
                    task_id,
                    stage="extract",
                    status="running",
                    progress=12 + round((current / max(total, 1)) * 20),
                    stage_progress=round((current / max(total, 1)) * 100),
                    current=current,
                    total=total,
                    filename=stored.filename if stored else None,
                    message=f"Extracting text page {current}/{total}",
                ),
            )
            raw_text = "\n".join(page.text for page in pages).strip()
            if document_type == "resume":
                row = Resume(
                    user_id=current_user.id, filename=stored.filename, file_path=str(stored.path),
                    raw_text=raw_text, structured_data={}, document_size=stored.size, parse_status="running",
                )
            else:
                row = JobDescription(
                    user_id=current_user.id, title=Path(stored.filename).stem, company="",
                    filename=stored.filename, file_path=str(stored.path), raw_text=raw_text,
                    structured_data={}, document_size=stored.size, parse_status="running",
                )
            db.add(row)
            db.flush()
            chunks = chunk_pages(
                pages=pages, run_id=0, candidate_id=row.id, document_type=document_type, filename=stored.filename,
            )
            progress_hub.publish(
                task_id,
                stage="llm_analyze",
                status="running",
                progress=45,
                document_id=f"{document_type}:{row.id}",
                filename=stored.filename,
                message=f"Structuring {document_type} with LLM",
                data={"document_id": f"{document_type}:{row.id}"},
            )
            row.structured_data = _parse_profile(document_type, stored.filename, raw_text, chunks)
            if document_type == "jd":
                row.title = str(row.structured_data.get("job_title") or row.structured_data.get("title") or row.title)
            rag_store = MilvusRagStore()
            progress_hub.publish(
                task_id,
                stage="embedding",
                status="running",
                progress=65,
                document_id=f"{document_type}:{row.id}",
                filename=stored.filename,
                message=f"Generating embeddings for {stored.filename}",
                data={"chunk_count": len(chunks)},
            )
            rag_store.index_chunks(user_id=current_user.id, document_id=row.id, chunks=chunks)
            progress_hub.publish(
                task_id,
                stage="milvus_save",
                status="running",
                progress=78,
                document_id=f"{document_type}:{row.id}",
                filename=stored.filename,
                message=f"Saving {document_type} vectors to Milvus",
                data={"document_id": f"{document_type}:{row.id}"},
            )
            rag_store.persist_document_profile(
                user_id=current_user.id,
                document_type=document_type,
                document_id=row.id,
                summary=(
                    str(row.structured_data.get("job_title") or row.title)
                    if document_type == "jd"
                    else str(row.structured_data.get("candidate_name") or row.filename)
                ),
                content=row.structured_data,
            )
            row.parse_status = _parse_status(document_type, row.structured_data)
            progress_hub.publish(
                task_id,
                stage="local_save",
                status="running",
                progress=92,
                document_id=f"{document_type}:{row.id}",
                filename=stored.filename,
                message=f"Saving {document_type} record to PostgreSQL",
                data={"document_id": f"{document_type}:{row.id}"},
            )
            db.commit()
            db.refresh(row)
            result = _record(document_type, row)
            results.append(result)
            progress_hub.publish(
                task_id,
                stage="completed",
                status="success",
                progress=100,
                document_id=result.id,
                filename=result.filename,
                message="Document parsing completed",
                data={"documents": [result.model_dump(mode="json")]},
            )
        except Exception as exc:
            db.rollback()
            if rag_store is not None and row is not None and row.id is not None:
                try:
                    rag_store.delete_document(user_id=current_user.id, document_type=document_type, document_id=row.id)
                except Exception:
                    pass
            if stored:
                delete_stored_file(stored.path)
            progress_hub.publish(
                task_id,
                stage="failed",
                status="failed",
                progress=100,
                filename=file.filename,
                message=f"{file.filename}: {exc}",
            )
            raise HTTPException(status_code=400, detail=f"{file.filename}: {exc}") from exc
    return DocumentParseResponse(documents=results, task_id=task_id)


@router.get("", response_model=list[DocumentParseResult])
async def list_documents(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = [_record("jd", row) for row in db.query(JobDescription).filter(JobDescription.user_id == current_user.id).all()]
    rows += [_record("resume", row) for row in db.query(Resume).filter(Resume.user_id == current_user.id).all()]
    return sorted(rows, key=lambda item: item.created_at, reverse=True)


@router.get("/{document_id}", response_model=DocumentParseResult)
async def get_document(document_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kind, row = _find_document(db, current_user.id, document_id)
    return _record(kind, row)


@router.post("/{document_id}/parse", response_model=DocumentParseResult)
def reparse_document(
    document_id: str,
    task_id: str = Query(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    kind, row = _find_document(db, current_user.id, document_id)
    task_id = task_id or progress_hub.create_task("task_parse")
    try:
        pages = extract_stored_pages(
            Path(row.file_path),
            row.filename,
            progress_callback=lambda current, total: progress_hub.publish(
                task_id,
                stage="extract",
                status="running",
                progress=12 + round((current / max(total, 1)) * 20),
                document_id=document_id,
                filename=row.filename,
                stage_progress=round((current / max(total, 1)) * 100),
                current=current,
                total=total,
                message=f"Re-extracting page {current}/{total}",
            ),
        )
        chunks = chunk_pages(pages=pages, run_id=0, candidate_id=row.id, document_type=kind, filename=row.filename)
        row.raw_text = "\n\n".join(page.text for page in pages)
        progress_hub.publish(
            task_id,
            stage="llm_analyze",
            status="running",
            progress=45,
            document_id=document_id,
            filename=row.filename,
            message=f"Re-structuring {kind} with LLM",
        )
        row.structured_data = _parse_profile(kind, row.filename, row.raw_text, chunks)
        rag_store = MilvusRagStore()
        rag_store.delete_document(user_id=current_user.id, document_type=kind, document_id=row.id)
        progress_hub.publish(
            task_id,
            stage="embedding",
            status="running",
            progress=65,
            document_id=document_id,
            filename=row.filename,
            message=f"Regenerating embeddings for {row.filename}",
        )
        rag_store.index_chunks(user_id=current_user.id, document_id=row.id, chunks=chunks)
        progress_hub.publish(
            task_id,
            stage="milvus_save",
            status="running",
            progress=78,
            document_id=document_id,
            filename=row.filename,
            message=f"Replacing {kind} vectors in Milvus",
        )
        rag_store.persist_document_profile(
            user_id=current_user.id,
            document_type=kind,
            document_id=row.id,
            summary=(
                str(row.structured_data.get("job_title") or row.title)
                if kind == "jd"
                else str(row.structured_data.get("candidate_name") or row.filename)
            ),
            content=row.structured_data,
        )
        row.parse_status = _parse_status(kind, row.structured_data)
        progress_hub.publish(
            task_id,
            stage="local_save",
            status="running",
            progress=92,
            document_id=document_id,
            filename=row.filename,
            message=f"Saving {kind} record to PostgreSQL",
        )
        db.commit()
        db.refresh(row)
        result = _record(kind, row)
        progress_hub.publish(
            task_id,
            stage="completed",
            status="success",
            progress=100,
            document_id=result.id,
            filename=result.filename,
            message="Document reparse completed",
            data={"document": result.model_dump(mode="json")},
        )
        return result
    except Exception as exc:
        db.rollback()
        row.parse_status = "failed"
        try:
            db.add(row)
            db.commit()
        except Exception:
            db.rollback()
        progress_hub.publish(
            task_id,
            stage="failed",
            status="failed",
            progress=100,
            document_id=document_id,
            filename=row.filename,
            message=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{document_id}")
async def delete_document(document_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kind, row = _find_document(db, current_user.id, document_id)
    MilvusRagStore().delete_document(user_id=current_user.id, document_type=kind, document_id=row.id)
    delete_stored_file(row.file_path)
    db.delete(row)
    db.commit()
    return {"id": document_id}


followup_router = APIRouter(prefix="/api", tags=["followups"])


@followup_router.post("/followups/analyze", response_model=FollowUpAnalysisResponse)
async def analyze_followup(request: FollowUpAnalysisRequest, current_user: User = Depends(get_current_user)):
    try:
        return AgentHarness().run_schema(
            task="followup.analyze_answer", prompt_name="generate_followup",
            schema=FollowUpAnalysisResponse, variables=request.model_dump(mode="json"),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
