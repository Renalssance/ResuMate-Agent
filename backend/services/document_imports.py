"""Accept internal document imports in the caller's transaction."""
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.agent_models import AgentRun, AgentSession
from backend.services.agent_runs import RunError, claim_session
from backend.services.documents import StoredUpload, persisted_upload_path
from backend.services.run_events import append_event


def find_document_import_run(db: Session, user_id: int, request_id: str) -> AgentRun | None:
    run = db.scalar(select(AgentRun).where(AgentRun.user_id == user_id, AgentRun.request_id == request_id))
    if run is not None and run.kind != 'document_import':
        raise RunError(409, 'request_conflict', '该 requestId 已用于另一项请求')
    return run


def create_document_import_run(db: Session, user_id: int, stored: StoredUpload, request_id: str) -> AgentRun:
    existing = find_document_import_run(db, user_id, request_id)
    if existing is not None:
        return existing
    session = AgentSession(id=str(uuid4()), user_id=user_id, purpose='document_import')
    run = AgentRun(id=str(uuid4()), user_id=user_id, session_id=session.id,
        request_id=request_id, kind='document_import', input_json={
            'filename': stored.filename,
            'sourcePath': persisted_upload_path(stored),
            'contentHash': stored.content_hash,
            'documentSize': stored.size,
        }, input_versions={})
    db.add(session)
    db.flush()
    db.add(run)
    db.flush()
    claim_session(db, user_id, session.id, run.id, kind=run.kind)
    append_event(db, run.id, 'run.status', {'status': run.status})
    return run
