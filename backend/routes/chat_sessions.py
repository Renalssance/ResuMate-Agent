"""Chat transport delegates admission and streaming to the existing Run lifecycle."""
import anyio
from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.db.models import User
from backend.middleware.rate_limit import require_chat_capacity
from backend.routes.agent_runs import RunRoute
from backend.schemas.agent_runs import RunAccepted, RunCreate
from backend.services import agent_runs, chat
from backend.services.run_delivery import publish_run

router = APIRouter(prefix='/api/chat/sessions', tags=['chat'], route_class=RunRoute)


class ChatTurnCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', populate_by_name=True, str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=16000)
    request_id: str = Field(alias='requestId', min_length=1, max_length=100)
    resume_id: int | None = Field(default=None, alias='resumeId', gt=0)
    jd_id: int | None = Field(default=None, alias='jdId', gt=0)


@router.get('')
def list_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return chat.list_sessions(db, user.id)


@router.post('', status_code=201)
def create_session(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return chat.create_session(db, user.id)


@router.get('/{session_id}')
def session_detail(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return chat.session_detail(db, user.id, session_id)


@router.post('/{session_id}/messages', status_code=202, response_model=RunAccepted,
             dependencies=[Depends(require_chat_capacity)])
def send_message(session_id: str, body: ChatTurnCreate,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chat.owned_session(db, user.id, session_id)
    run = agent_runs.create_run(db, user.id, RunCreate(kind='chat', session_id=session_id,
        **body.model_dump(exclude_none=True)))
    if run.status == 'queued':
        publish_run(run.id)
    return RunAccepted(run_id=run.id, status=run.status)


@router.post('/{session_id}/messages/upload', status_code=202, response_model=RunAccepted,
             dependencies=[Depends(require_chat_capacity)])
def send_attachment(session_id: str, message: str = Form(..., min_length=1, max_length=16000),
                    requestId: str = Form(..., min_length=1, max_length=100),
                    file: UploadFile = File(...), resumeId: int | None = Form(None, gt=0),
                    jdId: int | None = Form(None, gt=0),
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from backend.services.documents import (store_upload, persisted_upload_path,
        delete_stored_file, cleanup_upload_cache, UnsupportedDocumentError)
    chat.owned_session(db, user.id, session_id)
    if not message.strip():
        raise HTTPException(422, detail='请输入问题')
    request = RunCreate(kind='chat', session_id=session_id, message=message,
        requestId=requestId, resumeId=resumeId, jdId=jdId)
    stored = None
    committed = False
    try:
        run = agent_runs.create_run_in_transaction(db, user.id, request)
        if not run.input_json.get('attachment'):
            stored = anyio.from_thread.run(store_upload, file)
            run.input_json = {**run.input_json, 'attachment': {
                'filename': stored.filename, 'sourcePath': persisted_upload_path(stored),
                'contentHash': stored.content_hash, 'size': stored.size}}
        db.commit()
        committed = True
    except Exception as exc:
        db.rollback()
        if stored is not None and not committed:
            delete_stored_file(persisted_upload_path(stored))
        if isinstance(exc, UnsupportedDocumentError):
            raise HTTPException(400, detail=str(exc)) from exc
        raise
    finally:
        if stored is not None:
            cleanup_upload_cache(stored)
    if run.status == 'queued':
        publish_run(run.id)
    return RunAccepted(run_id=run.id, status=run.status)
