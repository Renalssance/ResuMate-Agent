"""Resolve a sent attachment before the conversational model answers."""
from typing import Literal
from urllib.parse import quote

from pydantic import BaseModel
from sqlalchemy import select

from backend.agents.harness import AgentHarness
from backend.db.agent_models import AgentRun
from backend.db.database import SessionLocal
from backend.db.models import Resume, JobDescription
from backend.services.agent_runs import guard_execution, RunError
from backend.services.document_tasks import _parse_profile
from backend.services.documents import extract_stored_pages, chunk_pages, profile_parse_status, delete_stored_file
from backend.services.run_events import append_event
from backend.services.progress import TaskProgress, append_progress


class AttachmentClassification(BaseModel):
    document_type: Literal['resume', 'jd', 'other']


def classify_attachment(text, user_id, guard, progress_callback=None):
    result = AgentHarness(user_id=user_id, guard=guard, progress_callback=progress_callback).run_schema(
        task='document.classify', prompt_name='classify_chat_attachment', schema=AttachmentClassification,
        variables={'document_text': text[:24000]}, progress_stage='classify', progress=35)
    return result.document_type


def _guard(run_id, epoch):
    with SessionLocal() as db:
        guard_execution(db, run_id, epoch)
        db.commit()


def _say(run_id, epoch, text):
    with SessionLocal() as db:
        guard_execution(db, run_id, epoch)
        append_event(db, run_id, 'assistant.delta', {'text': text + '\n\n'})
        db.commit()


def _link(document_id):
    return f'[查看文件](/documents?document={quote(document_id, safe="")})'


def _resolve(db, run, result, epoch):
    run.input_json = {**run.input_json, 'attachmentContext': result}
    append_progress(db, run.id, epoch, stage='complete', progress=100,
        message='文件已准备好，接下来结合你的问题继续分析。',
        filename=run.input_json['attachment']['filename'], document_id=result['documentId'],
        data={'scope': 'attachment', 'kind': result['type']})
    append_event(db, run.id, 'assistant.delta', {'text': result['notice'] + '\n\n'})
    db.commit()
    return result


def prepare_attachment(run_id: str, epoch: int) -> dict | None:
    with SessionLocal() as db:
        guard_execution(db, run_id, epoch)
        run = db.get(AgentRun, run_id)
        if not run.input_json.get('attachment'):
            db.commit()
            return None
        if run.input_json.get('attachmentContext'):
            result = run.input_json['attachmentContext']
            db.commit()
            return result
        attachment = run.input_json['attachment']
        user_id = run.user_id
        pending = run.input_json.get('attachmentParsed')
        incomplete = None
        if pending:
            db.commit()
        for kind, model in (() if pending else (('resume', Resume), ('jd', JobDescription))):
            row = db.scalar(select(model).where(model.user_id == user_id,
                model.content_hash == attachment['contentHash']).order_by(model.id).limit(1))
            if row is not None:
                document_id = f'{kind}:{row.id}'
                if not row.raw_text and not row.structured_data:
                    incomplete = (kind, row.id)
                    break
                result = _resolve(db, run, {'documentId': document_id, 'type': kind,
                    'text': row.raw_text or '', 'structured': row.structured_data or {},
                    'notice': f'资料库中已有文件：{row.filename or row.title}。{_link(document_id)}'}, epoch)
                delete_stored_file(attachment['sourcePath'])
                return result
        db.commit()
    progress = TaskProgress(run_id, epoch, session_factory=SessionLocal)
    kind = incomplete[0] if incomplete else None

    def publish(**event):
        data = event.get('data') or {}
        agent = data.get('agent', {})
        if agent:
            phase, attempt = agent['phase'], agent['attempt']
            waiting = ('正在判断文件是简历、岗位描述还是其他资料。' if event['stage'] == 'classify' else
                       '正在梳理教育背景、工作与项目经历，提取技能和成果。' if kind == 'resume' else
                       '正在提取岗位职责、任职要求和核心能力。')
            event['message'] = {
                'prompt_uploading': '正在整理文件内容，准备分析。',
                'waiting_response': waiting if attempt == 1 else f'正在重新分析，第 {attempt} 次尝试。',
                'receiving_response': event['message'],
                'validating_response': '已收到分析结果，正在检查内容格式与完整性。',
                'reflecting': (f'解析结果较长，正在增加输出额度并重新生成完整结果（第 {attempt + 1} 次）。'
                    if event['message'].startswith('LLM response was truncated') else
                    f'本次分析未通过，正在重新尝试（第 {attempt + 1} 次）。'),
                'completed': '本阶段分析结果已通过格式检查。',
                'failed': '本阶段分析未完成，请重试。',
            }.get(phase, '正在分析文件内容。')
        progress.publish(**{**event, 'filename': attachment['filename'],
                            'data': {**data, 'scope': 'attachment', 'kind': kind}})

    try:
        if pending:
            return _finish_saved(run_id, epoch, attachment, pending)
        if incomplete:
            _say(run_id, epoch, '资料库中已有此文件，但尚无可用解析结果，正在补充解析。')
        publish(stage='extract', progress=10, message='正在读取文件内容。', data={'reset': True})
        pages = extract_stored_pages(attachment['sourcePath'], attachment['filename'],
            progress_callback=lambda current, total: publish(stage='extract', progress=25,
                current=current, total=total, message=f'已读取 {current}/{total} 页。'))
        raw_text = '\n'.join(page.text for page in pages).strip()
        publish(stage='classify', progress=30, message='正在识别文件类型。')
        kind = incomplete[0] if incomplete else classify_attachment(raw_text, user_id, lambda: _guard(run_id, epoch), publish)
        label = {'resume': '简历', 'jd': '岗位', 'other': '其他文件'}[kind]
        publish(stage='classify', progress=35, message=f'已识别为{label}。')
        content = {}
        if kind != 'other':
            chunks = chunk_pages(pages=pages, run_id=run_id, candidate_id=0,
                document_type=kind, filename=attachment['filename'])
            content = _parse_profile(kind, attachment['filename'], raw_text, chunks, run_id, user_id,
                guard=lambda: _guard(run_id, epoch), progress_callback=publish)
            publish(stage='save', progress=90, message='解析与校验已完成，正在保存到资料库。')
        with SessionLocal() as db:
            guard_execution(db, run_id, epoch)
            run = db.get(AgentRun, run_id)
            document_id = None
            if kind != 'other':
                fields = dict(user_id=user_id, filename=attachment['filename'],
                    file_path=attachment['sourcePath'], content_hash=attachment['contentHash'],
                    document_size=attachment['size'], raw_text=raw_text, structured_data=content,
                    parse_status='running')
                if incomplete:
                    row = db.get(Resume if kind == 'resume' else JobDescription, incomplete[1])
                    if row is None:
                        raise RunError(404, 'source_missing', '文档已删除')
                    row.raw_text, row.structured_data, row.parse_status = raw_text, content, 'running'
                    if not row.file_path:
                        row.file_path = attachment['sourcePath']
                else:
                    row = Resume(**fields) if kind == 'resume' else JobDescription(**fields,
                        title=str(content.get('job_title') or content.get('title') or attachment['filename']),
                        company=str(content.get('company') or ''))
                db.add(row)
                db.flush()
                document_id = f'{kind}:{row.id}'
                notice = f'已解析为{label}，已保存到资料库：{attachment["filename"]}。{_link(document_id)}'
            else:
                notice = f'已识别为其他文件：{attachment["filename"]}，仅用于本次对话，不保存到资料库。'
            result = {'documentId': document_id, 'type': kind,
                'text': raw_text, 'structured': content, 'notice': notice}
            if kind != 'other':
                run.input_json = {**run.input_json, 'attachmentParsed': result}
                db.commit()
            else:
                _resolve(db, run, result, epoch)
        if kind != 'other':
            return _finish_saved(run_id, epoch, attachment, result)
        if kind == 'other':
            delete_stored_file(attachment['sourcePath'])
        return result
    except RunError:
        raise
    except Exception as exc:
        _say(run_id, epoch, '文件解析未完成，请检查文件内容或模型设置后重试。')
        raise RunError(502, 'chat_attachment_failed', '附件解析失败') from exc


def _finish_saved(run_id, epoch, attachment, result):
    kind, identifier = result['documentId'].split(':')
    record_id = int(identifier)
    with SessionLocal() as db:
        guard_execution(db, run_id, epoch)
        row = db.get(Resume if kind == 'resume' else JobDescription, record_id)
        if row is None:
            raise RunError(404, 'source_missing', '文档已删除')
        row.parse_status = profile_parse_status(kind, result['structured'])
        row.structured_data = {**row.structured_data, '_vectorized': False}
        original_path = row.file_path
        saved = _resolve(db, db.get(AgentRun, run_id), result, epoch)
    if original_path != attachment['sourcePath']:
        delete_stored_file(attachment['sourcePath'])
    return saved
