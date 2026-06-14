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
    store_and_extract_upload,
)
from backend.services.llm_validation import validate_resume_source_refs
from backend.services.progress import progress_hub

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _record(document_type: str, row) -> DocumentParseResult:
    return DocumentParseResult(
        id=f"{document_type}:{row.id}",
        type=document_type,
        filename=row.filename if document_type == "resume" else (row.filename or row.title),
        size=row.document_size,
        raw_text=row.raw_text,
        parsed_content=row.structured_data or {},
        parse_status=row.parse_status,
        created_at=row.created_at.isoformat(),
        vectorized=True,
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
        for chunk in chunks[:80]
    ]
    profile = harness.run_schema(
        task="document.parse_resume", prompt_name="parse_resume", schema=ResumeProfile,
        variables={"filename": filename, "chunks_json": payload},
    )
    validate_resume_source_refs(profile, chunks[:80])
    content = profile.model_dump(mode="json")
    content["name"] = profile.candidate_name
    return content


@router.post("", response_model=DocumentParseResponse)
def upload_documents(
    document_type: DocumentType = Form(...),
    files: list[UploadFile] = File(...),
    task_id: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task_id = task_id or progress_hub.create_task("task_parse")
    results = []
    for file in files:
        stored = None
        row = None
        try:
            progress_hub.publish(
                task_id,
                stage="upload",
                status="running",
                progress=5,
                message=f"Receiving {file.filename}",
                data={"document_type": document_type},
            )
            stored = anyio.from_thread.run(store_and_extract_upload, file)
            progress_hub.publish(
                task_id,
                stage="extract",
                status="running",
                progress=20,
                message=f"Extracted text from {stored.filename}",
                data={"filename": stored.filename, "size": stored.size},
            )
            if document_type == "resume":
                row = Resume(
                    user_id=current_user.id, filename=stored.filename, file_path=str(stored.path),
                    raw_text=stored.raw_text, structured_data={}, document_size=stored.size, parse_status="running",
                )
            else:
                row = JobDescription(
                    user_id=current_user.id, title=Path(stored.filename).stem, company="",
                    filename=stored.filename, file_path=str(stored.path), raw_text=stored.raw_text,
                    structured_data={}, document_size=stored.size, parse_status="running",
                )
            db.add(row)
            db.flush()
            chunks = chunk_pages(
                pages=stored.pages, run_id=0, candidate_id=row.id, document_type=document_type, filename=stored.filename,
            )
            progress_hub.publish(
                task_id,
                stage="llm_analyze",
                status="running",
                progress=45,
                message=f"Structuring {document_type} with LLM",
                data={"document_id": f"{document_type}:{row.id}"},
            )
            row.structured_data = _parse_profile(document_type, stored.filename, stored.raw_text, chunks)
            if document_type == "jd":
                row.title = str(row.structured_data.get("job_title") or row.structured_data.get("title") or row.title)
            rag_store = MilvusRagStore()
            progress_hub.publish(
                task_id,
                stage="embedding",
                status="running",
                progress=65,
                message=f"Generating embeddings for {stored.filename}",
                data={"chunk_count": len(chunks)},
            )
            rag_store.index_chunks(user_id=current_user.id, document_id=row.id, chunks=chunks)
            progress_hub.publish(
                task_id,
                stage="milvus_save",
                status="running",
                progress=78,
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
            row.parse_status = "success"
            progress_hub.publish(
                task_id,
                stage="local_save",
                status="running",
                progress=92,
                message=f"Saving {document_type} record to PostgreSQL",
                data={"document_id": f"{document_type}:{row.id}"},
            )
            db.commit()
            db.refresh(row)
            results.append(_record(document_type, row))
        except Exception as exc:
            db.rollback()
            if stored:
                delete_stored_file(stored.path)
            progress_hub.publish(
                task_id,
                stage="failed",
                status="failed",
                progress=100,
                message=f"{file.filename}: {exc}",
            )
            raise HTTPException(status_code=400, detail=f"{file.filename}: {exc}") from exc
    progress_hub.publish(
        task_id,
        stage="completed",
        status="success",
        progress=100,
        message="Document parsing completed",
        data={"documents": [item.model_dump(mode="json") for item in results]},
    )
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
        progress_hub.publish(task_id, stage="extract", status="running", progress=20, message=f"Re-extracting {row.filename}")
        pages = extract_stored_pages(Path(row.file_path), row.filename)
        chunks = chunk_pages(pages=pages, run_id=0, candidate_id=row.id, document_type=kind, filename=row.filename)
        row.raw_text = "\n\n".join(page.text for page in pages)
        progress_hub.publish(task_id, stage="llm_analyze", status="running", progress=45, message=f"Re-structuring {kind} with LLM")
        row.structured_data = _parse_profile(kind, row.filename, row.raw_text, chunks)
        rag_store = MilvusRagStore()
        rag_store.delete_document(user_id=current_user.id, document_type=kind, document_id=row.id)
        progress_hub.publish(task_id, stage="embedding", status="running", progress=65, message=f"Regenerating embeddings for {row.filename}")
        rag_store.index_chunks(user_id=current_user.id, document_id=row.id, chunks=chunks)
        progress_hub.publish(task_id, stage="milvus_save", status="running", progress=78, message=f"Replacing {kind} vectors in Milvus")
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
        row.parse_status = "success"
        progress_hub.publish(task_id, stage="local_save", status="running", progress=92, message=f"Saving {kind} record to PostgreSQL")
        db.commit()
        db.refresh(row)
        result = _record(kind, row)
        progress_hub.publish(
            task_id,
            stage="completed",
            status="success",
            progress=100,
            message="Document reparse completed",
            data={"document": result.model_dump(mode="json")},
        )
        return result
    except Exception as exc:
        db.rollback()
        progress_hub.publish(task_id, stage="failed", status="failed", progress=100, message=str(exc))
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
