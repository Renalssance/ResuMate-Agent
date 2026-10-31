"""Accept and execute content-classified imports from one stored original."""
from typing import Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.agent_models import AgentAction, AgentRun, AgentSession
from backend.db.database import SessionLocal
from backend.db.models import JobDescription, Resume
from backend.schemas.agent_runs import RunStatus
from backend.schemas.document_import import DocumentClassification
from backend.services.agent_runs import RunError, claim_session, finish_run, guard_execution, require_task_sources
from backend.services.document_classifier import classify_document
from backend.services.document_tasks import parse_document_record
from backend.services.documents import StoredUpload, delete_stored_file, extract_stored_pages, persisted_upload_path
from backend.services.run_events import append_event

DOCUMENT_TYPE_INTERRUPT_ID = 'document-type'


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


def guarded_import_run(db: Session, run_id: str, epoch: int) -> AgentRun:
    guard_execution(db, run_id, epoch)
    run = db.get(AgentRun, run_id, populate_existing=True)
    require_task_sources(db, run)
    return run


def guard_import(run_id: str, epoch: int) -> None:
    with SessionLocal() as db:
        guarded_import_run(db, run_id, epoch)
        db.commit()


def adopt_import(db: Session, run: AgentRun, document_type: Literal['resume', 'jd']):
    """Caller holds the Run fence; commit the row and its stable identity together."""
    existing_id = run.input_json.get('documentId')
    if existing_id:
        require_task_sources(db, run)
        kind, identifier = existing_id.split(':')
        return db.get(Resume if kind == 'resume' else JobDescription, int(identifier))
    common = dict(user_id=run.user_id, filename=run.input_json['filename'],
        file_path=run.input_json['sourcePath'], content_hash=run.input_json['contentHash'],
        document_size=run.input_json['documentSize'], raw_text='', structured_data={}, parse_status='running')
    row = Resume(**common) if document_type == 'resume' else JobDescription(**common, title='待解析岗位', company='')
    db.add(row)
    db.flush()
    run.input_json = {**run.input_json, 'documentId': f'{document_type}:{row.id}', 'detectedType': document_type}
    db.commit()
    return row


def pause_for_document_type(db: Session, run: AgentRun, epoch: int,
                            classification: DocumentClassification) -> None:
    action = db.scalar(select(AgentAction).where(
        AgentAction.run_id == run.id, AgentAction.interrupt_id == DOCUMENT_TYPE_INTERRUPT_ID))
    if action is None:
        action = AgentAction(run_id=run.id, interrupt_id=DOCUMENT_TYPE_INTERRUPT_ID, kind='input', payload={
            'question': '这份文件属于哪一类？', 'filename': run.input_json['filename'],
            'reason': classification.reason,
            'choices': [{'value': 'resume', 'label': '简历'}, {'value': 'jd', 'label': '岗位'}],
        })
        db.add(action)
        db.flush()
        append_event(db, run.id, 'action.required', {'action_id': action.id, 'kind': 'input'})
    finish_run(db, run.id, epoch, RunStatus.WAITING_INPUT)


def answered_document_type(db: Session, run: AgentRun) -> Literal['resume', 'jd'] | None:
    action = db.scalar(select(AgentAction).where(
        AgentAction.run_id == run.id, AgentAction.interrupt_id == DOCUMENT_TYPE_INTERRUPT_ID,
        AgentAction.status == 'answered'))
    value = (action.response or {}).get('answers', {}).get('documentType') if action else None
    return value if value in ('resume', 'jd') else None


def cleanup_unadopted_import(db: Session, run: AgentRun) -> None:
    if (run.kind == 'document_import' and run.status in (RunStatus.FAILED, RunStatus.CANCELLED)
            and (run.status == RunStatus.CANCELLED or run.error_code != 'document_classification_failed')
            and not run.input_json.get('documentId') and run.input_json.get('sourcePath')):
        delete_stored_file(run.input_json['sourcePath'])
        run.input_json = {**run.input_json, 'sourcePath': ''}
        db.commit()


def run_document_import(run_id: str, epoch: int) -> None:
    try:
        with SessionLocal() as db:
            run = db.get(AgentRun, run_id)
            if run is None or run.status == RunStatus.SUCCEEDED:
                return
            run = guarded_import_run(db, run_id, epoch)
            source_path, filename, user_id = run.input_json['sourcePath'], run.input_json['filename'], run.user_id
            document_id = run.input_json.get('documentId')
            if not document_id:
                confirmed_type = answered_document_type(db, run)
                if confirmed_type:
                    adopt_import(db, run, confirmed_type)
                    document_id = run.input_json['documentId']
            db.commit()
        pages = None
        if not document_id:
            pages = extract_stored_pages(source_path, filename)
            try:
                classification = classify_document('\n'.join(page.text for page in pages).strip(),
                    user_id=user_id, guard=lambda: guard_import(run_id, epoch))
            except RunError:
                raise
            except Exception as exc:
                raise RunError(502, 'document_classification_failed', '文件分类未完成，请检查模型设置后重试') from exc
            with SessionLocal() as db:
                run = guarded_import_run(db, run_id, epoch)
                if classification.document_type == 'ambiguous' or classification.confidence != 'high':
                    pause_for_document_type(db, run, epoch, classification)
                    return
                adopt_import(db, run, classification.document_type)
                document_id = run.input_json['documentId']
        parse_document_record(run_id, epoch, document_id=document_id, pages=pages)
    except Exception as exc:
        with SessionLocal() as db:
            run = db.get(AgentRun, run_id)
            if run is not None and run.status == RunStatus.RUNNING and run.execution_epoch == epoch:
                finish_run(db, run_id, epoch, RunStatus.FAILED,
                    error_code=exc.code if isinstance(exc, RunError) else 'document_import_failed')
            elif run is not None:
                cleanup_unadopted_import(db, run)
