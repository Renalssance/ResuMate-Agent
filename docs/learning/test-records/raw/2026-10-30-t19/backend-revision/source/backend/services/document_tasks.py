"""Recoverable document parsing. SQL results, operation and completion commit together."""
from __future__ import annotations

import copy
from datetime import datetime, timezone

from sqlalchemy import select

from backend.agents.harness import AgentHarness
from backend.db.agent_models import AgentRun, ToolOperation
from backend.db.database import SessionLocal
from backend.db.models import JobDescription, Resume
from backend.rag import get_rag_store
from backend.schemas.agent_runs import RunStatus
from backend.schemas.workflow import DocumentParseResponse, DocumentType, JobProfile, ResumeProfile
from backend.services.agent_runs import RunError, finish_run, guard_execution, require_task_sources
from backend.services.documents import (chunk_pages, detect_multiple_positions, document_record,
    extract_stored_pages, profile_parse_status)
from backend.services.llm_validation import validate_resume_source_refs
from backend.services.progress import TaskProgress
from backend.services.resume_postprocess import postprocess_resume_profile
from backend.services.run_events import append_event


def _parse_profile(kind: DocumentType, filename: str, raw_text: str, chunks, task_id: str = "",
                   user_id: int | None = None, *, guard=None, progress_callback=None):
    harness = AgentHarness(user_id=user_id, guard=guard, progress_callback=progress_callback)
    if kind == 'jd':
        if detect_multiple_positions(raw_text):
            raise ValueError('MULTIPLE_POSITIONS_DETECTED: please split the JD before parsing')
        profile = harness.run_schema(task='document.parse_jd', prompt_name='parse_jd', schema=JobProfile,
            variables={'jd_text': raw_text[:24000]}, task_id=task_id, progress_stage='llm_analyze', progress=45)
        content = profile.model_dump(mode='json')
        content['title'] = profile.job_title
        return content
    payload = [{'chunk_id': chunk.id, 'page_number': chunk.page_number, 'section': chunk.section, 'text': chunk.text}
               for chunk in chunks]
    profile = harness.run_schema(task='document.parse_resume', prompt_name='parse_resume', schema=ResumeProfile,
        variables={'filename': filename, 'chunks_json': payload}, task_id=task_id, progress_stage='llm_analyze', progress=45)
    profile = postprocess_resume_profile(profile, chunks)
    validate_resume_source_refs(profile, chunks)
    content = profile.model_dump(mode='json')
    content['name'] = profile.candidate_name
    return content


def _cached_structured_data(db, model, *, user_id, content_hash):
    if not content_hash:
        return None
    rows = db.scalars(select(model).where(model.user_id == user_id, model.content_hash == content_hash,
        model.parse_status.in_(('success', 'success_with_warnings')), model.structured_data.is_not(None))
        .order_by(model.created_at.desc()))
    for row in rows:
        if isinstance(row.structured_data, dict) and row.structured_data:
            return copy.deepcopy(row.structured_data)
    return None


def _owned_document(db, run):
    kind, _, record_id = run.input_json['documentId'].partition(':')
    model = Resume if kind == 'resume' else JobDescription
    row = db.scalar(select(model).where(model.id == int(record_id), model.user_id == run.user_id))
    if row is None:
        raise RunError(404, 'source_missing', '文档不存在或已不属于当前用户')
    return kind, row


def _guard(run_id, epoch):
    with SessionLocal() as db:
        guard_execution(db, run_id, epoch)
        require_task_sources(db, db.get(AgentRun, run_id))
        db.commit()


def run_document_parse(run_id: str, epoch: int) -> None:
    progress = TaskProgress(run_id, epoch, session_factory=SessionLocal)
    try:
        with SessionLocal() as db:
            run = db.get(AgentRun, run_id)
            if run is None or run.status == RunStatus.SUCCEEDED:
                return
            guard_execution(db, run_id, epoch)
            require_task_sources(db, run)
            kind, row = _owned_document(db, run)
            document_id, mode, user_id = run.input_json['documentId'], run.input_json['parseMode'], run.user_id
            filename, source_path, record_id = row.filename or row.title, row.file_path, row.id
            raw_text = row.raw_text or ''
            cached = _cached_structured_data(db, type(row), user_id=user_id, content_hash=row.content_hash) if mode == 'upload' else None
            row.parse_status = 'running'
            db.commit()

        progress.publish(stage='server_save', status='running', progress=12, document_id=document_id,
                         filename=filename, message='正在读取已保存的原件')
        chunks = []
        if mode != 'saved_job':
            pages = extract_stored_pages(source_path, filename, progress_callback=lambda current, total:
                progress.publish(stage='extract', status='running', progress=12 + round(current / max(total, 1) * 20),
                    stage_progress=round(current / max(total, 1) * 100), current=current, total=total,
                    document_id=document_id, filename=filename, message=f'正在提取第 {current}/{total} 页'))
            raw_text = '\n'.join(page.text for page in pages).strip()
            chunks = chunk_pages(pages=pages, run_id=0, candidate_id=record_id, document_type=kind, filename=filename)
        progress.publish(stage='llm_analyze', status='running', progress=45, document_id=document_id,
            filename=filename, message='正在复用已有解析结果' if cached else '正在提取文档结构', data={'cached': bool(cached)})
        _guard(run_id, epoch)
        content = cached or _parse_profile(kind, filename, raw_text, chunks, run_id, user_id,
            guard=lambda: _guard(run_id, epoch), progress_callback=progress.publish)
        if mode != 'saved_job':
            _guard(run_id, epoch)
            progress.publish(stage='embedding', status='running', progress=65, document_id=document_id,
                filename=filename, message='正在生成文档索引', data={'chunk_count': len(chunks)})
            get_rag_store().replace_document_chunks(user_id=user_id, document_id=record_id, chunks=chunks,
                before_write=lambda: _guard(run_id, epoch))
        with SessionLocal() as db:
            guard_execution(db, run_id, epoch)
            run = db.get(AgentRun, run_id)
            require_task_sources(db, run)
            kind, row = _owned_document(db, run)
            row.raw_text, row.structured_data = raw_text, content
            row.parse_status = profile_parse_status(kind, content)
            row.updated_at = datetime.now(timezone.utc)
            if kind == 'jd' and mode == 'upload':
                row.title = str(content.get('job_title') or content.get('title') or row.title)
            result = document_record(kind, row)
            if mode == 'saved_job':
                result = result.model_copy(update={'vectorized': False})
            saved = (DocumentParseResponse(documents=[result], task_id=run_id).model_dump(mode='json', by_alias=True)
                     if mode == 'upload' else result.model_dump(mode='json'))
            db.add(ToolOperation(run_id=run_id, operation_key='parse:' + document_id,
                tool_name='document_parse', status='succeeded', result_ref=document_id))
            append_event(db, run_id, 'artifact.created', {'artifact_id': document_id, 'kind': 'document'})
            finish_run(db, run_id, epoch, RunStatus.SUCCEEDED, result_json=saved)
    except Exception as exc:
        with SessionLocal() as db:
            run = db.get(AgentRun, run_id)
            if run is None or run.status != RunStatus.RUNNING or run.execution_epoch != epoch:
                return
            finish_run(db, run_id, epoch, RunStatus.FAILED,
                error_code=exc.code if isinstance(exc, RunError) else 'document_parse_failed')
