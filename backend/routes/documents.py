from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import anyio
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from backend.middleware.rate_limit import require_run_capacity
from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.db.models import JobDescription, Resume, User
from backend.rag import get_rag_store
from backend.schemas.agent_runs import RunCreate
from backend.schemas.document_import import DocumentImportAccepted
from backend.schemas.workflow import (DocumentParseResponse, DocumentParseResult, DocumentType,
    FollowUpAnalysisRequest, FollowUpAnalysisResponse, StructuredDataUpdate)
from backend.services.analysis import parse_document_id
from backend.services.agent_runs import RunError, find_upload_run
from backend.services.background_tasks import submit_task
from backend.services.document_imports import create_document_import_run, find_document_import_run
from backend.services.documents import (cleanup_upload_cache, delete_stored_file,
    document_record as _record, profile_parse_status as _parse_status, persisted_upload_path, store_upload)
from backend.services.run_delivery import publish_run

router = APIRouter(prefix="/api/documents", tags=["documents"])


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


@router.post("", response_model=DocumentParseResponse, dependencies=[Depends(require_run_capacity)])
def upload_documents(
    document_type: DocumentType = Form(...), files: list[UploadFile] = File(...), task_id: str = Form(""),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db), prefer: str = Header(""),
):
    if len(files) != 1:
        raise HTTPException(status_code=422, detail="exactly one file is required per document parsing task")
    request_id = task_id or str(uuid4())
    user_id = current_user.id
    try:
        existing = find_upload_run(db, user_id, request_id, document_type)
    except RunError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    if existing is not None:
        return submit_task(db, user_id, RunCreate(kind="document_parse", request_id=request_id,
            document_id=existing.input_json["documentId"], parse_mode="upload"), prefer=prefer)
    stored = None
    try:
        # Persist the original before request-owned UploadFile is closed.
        stored = anyio.from_thread.run(store_upload, files[0])
        fields = dict(user_id=user_id, filename=stored.filename, file_path=persisted_upload_path(stored),
            content_hash=stored.content_hash, raw_text="", structured_data={},
            document_size=stored.size, parse_status="pending")
        row = Resume(**fields) if document_type == "resume" else JobDescription(
            **fields, title=Path(stored.filename).stem, company="")
        db.add(row)
        db.flush()
        return submit_task(db, user_id, RunCreate(kind="document_parse", request_id=request_id,
            document_id=f"{document_type}:{row.id}", parse_mode="upload"), prefer=prefer)
    except Exception as exc:
        db.rollback()
        # A synchronous wait can fail after acceptance. Its original is still a retry input.
        accepted = find_upload_run(db, user_id, request_id, document_type)
        if stored is not None and accepted is None:
            delete_stored_file(persisted_upload_path(stored))
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=400, detail=f"{files[0].filename}: {exc}") from exc
    finally:
        if stored is not None:
            cleanup_upload_cache(stored)


@router.post("/import", response_model=DocumentImportAccepted, status_code=202,
    dependencies=[Depends(require_run_capacity)])
def import_document(file: list[UploadFile] = File(...), request_id: str = Form("", alias="requestId"),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    if len(file) != 1:
        raise HTTPException(status_code=422, detail="exactly one file is required")
    key = request_id or str(uuid4())
    try:
        existing = find_document_import_run(db, current_user.id, key)
    except RunError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    if existing is not None:
        return DocumentImportAccepted(runId=existing.id, status=existing.status)
    stored = None
    try:
        stored = anyio.from_thread.run(store_upload, file[0])
        run = create_document_import_run(db, current_user.id, stored, key)
        db.commit()
    except Exception as exc:
        db.rollback()
        if stored is not None:
            delete_stored_file(persisted_upload_path(stored))
        if isinstance(exc, RunError):
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
        raise
    finally:
        if stored is not None:
            cleanup_upload_cache(stored)
    publish_run(run.id)
    return DocumentImportAccepted(runId=run.id, status=run.status)


@router.get("", response_model=list[DocumentParseResult])
async def list_documents(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = [_record("jd", row) for row in db.query(JobDescription).filter(JobDescription.user_id == current_user.id).all()]
    rows += [_record("resume", row) for row in db.query(Resume).filter(Resume.user_id == current_user.id).all()]
    return sorted(rows, key=lambda item: item.created_at, reverse=True)


@router.get("/{document_id}", response_model=DocumentParseResult)
async def get_document(document_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kind, row = _find_document(db, current_user.id, document_id)
    return _record(kind, row)


@router.patch("/{document_id}/structured-data", response_model=DocumentParseResult)
def update_document_structured_data(
    document_id: str,
    request: StructuredDataUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    kind, row = _find_document(db, current_user.id, document_id)
    if kind != "resume":
        raise HTTPException(status_code=422, detail="only resume structured data can be edited")
    row.structured_data = request.structured_data
    row.updated_at = datetime.now(timezone.utc)
    row.parse_status = _parse_status(kind, row.structured_data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _record(kind, row)


@router.post("/{document_id}/parse", response_model=DocumentParseResult, dependencies=[Depends(require_run_capacity)])
def reparse_document(document_id: str, task_id: str = Query(""),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db), prefer: str = Header(""),
):
    kind, row = _find_document(db, current_user.id, document_id)
    mode = "saved_job" if kind == "jd" and not row.file_path else "reparse"
    return submit_task(db, current_user.id, RunCreate(kind="document_parse", request_id=task_id or str(uuid4()),
        document_id=document_id, parse_mode=mode), prefer=prefer)


@router.delete("/{document_id}")
async def delete_document(document_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kind, row = _find_document(db, current_user.id, document_id)
    get_rag_store().delete_document(user_id=current_user.id, document_type=kind, document_id=row.id)
    delete_stored_file(row.file_path)
    if kind == "resume":
        from uuid import uuid4
        from backend.db.career_models import ProfileFact
        from backend.db.models import utcnow
        from backend.services.profile_facts import latest_statement

        # SET NULL preserves history, but must not turn source-specific facts into global facts.
        facts = db.scalars(latest_statement(current_user.id).where(
            ProfileFact.source_document_id == row.id, ProfileFact.deleted_at.is_(None)))
        for fact in facts:
            db.add(ProfileFact(id=str(uuid4()), user_id=current_user.id, fact_key=fact.fact_key,
                               kind=fact.kind, content=fact.content, source_document_id=row.id,
                               revision=fact.revision + 1, deleted_at=utcnow()))
        # Persist the tombstones before the FK source disappears, in the same transaction.
        db.flush()
    db.delete(row)
    db.commit()
    return {"id": document_id}


followup_router = APIRouter(prefix="/api", tags=["followups"])


@followup_router.post("/followups/analyze", response_model=FollowUpAnalysisResponse, dependencies=[Depends(require_run_capacity)])
def analyze_followup(request: FollowUpAnalysisRequest,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
    task_id: str = Query(""), prefer: str = Header(""),
):
    return submit_task(db, current_user.id, RunCreate(kind="answer_followup", request_id=task_id or str(uuid4()),
        followup=request), prefer=prefer)
