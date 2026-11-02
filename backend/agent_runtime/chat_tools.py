"""User-bound career tools; long work is accepted into the existing task queue."""
from datetime import datetime, time, timezone
from collections import Counter
from typing import Literal

from fastapi import HTTPException
from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from pydantic import ValidationError
from sqlalchemy import select

from backend.db.database import SessionLocal
from backend.db.agent_models import AgentRun, ToolOperation
from backend.db.models import JobApplication, JobDescription, Resume
from backend.schemas.agent_runs import RunCreate
from backend.services import agent_runs
from backend.services.run_delivery import publish_run
from backend.services.run_events import append_event


def career_tools(run_id: str, epoch: int):
    def execute(name, runtime, callback, *, write=False):
        key = runtime.tool_call_id or name
        try:
            with SessionLocal() as db:
                agent_runs.guard_execution(db, run_id, epoch)
                parent = db.get(AgentRun, run_id)
                operation = db.scalar(select(ToolOperation).where(
                    ToolOperation.run_id == run_id, ToolOperation.operation_key == key))
                if write and operation is not None and operation.status == 'succeeded':
                    return {'resultRef': operation.result_ref, 'replayed': True,
                            'instruction': 'Use get_task/get_interview/list_applications to read the current result.'}
                append_event(db, run_id, 'tool.started', {'tool_name': name, 'operation_key': key})
                if write and operation is None:
                    operation = ToolOperation(run_id=run_id, operation_key=key, tool_name=name, status='pending')
                    db.add(operation)
                    db.flush()
                # Stable SQL identity, also used by services which commit their own transactions.
                request_id = f'chat:{run_id}:{operation.id}' if write else ''
                if write:
                    db.commit()
                    agent_runs.guard_execution(db, run_id, epoch)
                result = callback(db, parent.user_id, request_id)
                ref = result.get('resultRef')
                # Some existing services commit. Refresh before appending the result.
                agent_runs.guard_execution(db, run_id, epoch)
                parent = db.get(AgentRun, run_id, populate_existing=True)
                if write:
                    operation.status, operation.result_ref = 'succeeded', ref
                refs = [ref] if ref else []
                if result.get('runId'):
                    refs.append('run:' + result['runId'])
                for reference_value in refs:
                    kind, _, identifier = reference_value.partition(':')
                    reference = {'type': kind, 'id': identifier}
                    if reference not in parent.output_refs:
                        parent.output_refs = [*parent.output_refs, reference]
                append_event(db, run_id, 'tool.completed', {
                    'tool_name': name, 'operation_key': key, 'result_ref': ref})
                db.commit()
            # All worker publication follows the committing transaction.
            if result.get('runId') and result.get('status') == 'queued':
                publish_run(result['runId'])
            return result
        except (agent_runs.RunError, HTTPException, ValidationError, ValueError) as error:
            if isinstance(error, agent_runs.RunError) and error.code in ('execution_lost', 'session_context_invalidated'):
                raise
            message = error.message if isinstance(error, agent_runs.RunError) else (
                str(error.detail) if isinstance(error, HTTPException) else '工具参数无效，请检查所选材料与字段')
            with SessionLocal() as db:
                agent_runs.guard_execution(db, run_id, epoch)
                append_event(db, run_id, 'tool.failed', {'tool_name': name, 'operation_key': key,
                    'error_code': error.code if isinstance(error, agent_runs.RunError) else 'invalid_tool_input',
                    'message': message})
                db.commit()
            return {'error': message}

    @tool
    def list_documents(runtime: ToolRuntime, offset: int = 0) -> dict:
        """List current user's resumes and job descriptions with IDs and parse status; 50 per type per page."""
        def read(db, user_id, _):
            if offset < 0:
                raise ValueError('offset')
            result = []
            more = False
            for kind, model in [('resume', Resume), ('jd', JobDescription)]:
                rows = list(db.scalars(select(model).where(model.user_id == user_id).order_by(
                    model.id.desc()).offset(offset).limit(51)))
                more = more or len(rows) > 50
                result.extend({'documentId': f'{kind}:{row.id}', 'id': row.id, 'type': kind,
                    'name': row.filename or getattr(row, 'title', ''), 'parseStatus': row.parse_status}
                    for row in rows[:50])
            return {'documents': result, 'hasMore': more, 'nextOffset': offset + 50}
        return execute('list_documents', runtime, read)

    @tool
    def read_document(document_id: str, runtime: ToolRuntime, offset: int = 0) -> dict:
        """Read an owned resume:N or jd:N, in 12000-character pages. Use real source text, never invent facts."""
        def read(db, user_id, _):
            import json
            from backend.routes.documents import _find_document
            kind, row = _find_document(db, user_id, document_id)
            if offset < 0:
                raise ValueError('offset')
            content = json.dumps({'rawText': row.raw_text, 'structuredData': row.structured_data}, ensure_ascii=False)
            return {'documentId': document_id, 'parseStatus': row.parse_status,
                    'content': content[offset:offset + 12000], 'nextOffset': offset + 12000,
                    'hasMore': offset + 12000 < len(content)}
        return execute('read_document', runtime, read)

    @tool
    def start_task(kind: Literal['document_parse', 'match_analysis', 'tailoring', 'question_generation', 'resume_export'],
                   runtime: ToolRuntime, resume_id: int | None = None, jd_id: int | None = None,
                   document_id: str | None = None, analysis_job_id: int | None = None,
                   candidate_id: int | None = None, resume_version_id: str | None = None,
                   question_count: int = 5) -> dict:
        """Queue parsing, scored matching, resume drafting, questions or confirmed-version PDF export.

        document_parse needs document_id; match_analysis/tailoring need resume_id and jd_id.
        question_generation needs analysis_job_id and candidate_id from a completed match.
        resume_export needs a user-confirmed resume_version_id. Queued does NOT mean completed.
        Return control to the user after queuing: a single worker must finish this chat before doing the task.
        """
        def submit(db, user_id, request_id):
            args = {'kind': kind, 'requestId': request_id}
            if kind == 'document_parse':
                from backend.routes.documents import _find_document
                doc_kind, row = _find_document(db, user_id, document_id or '')
                args.update(documentId=document_id, parseMode='saved_job' if doc_kind == 'jd' and not row.file_path else 'reparse')
            elif kind == 'match_analysis':
                args.update(jdId=jd_id, resumeIds=[resume_id])
            elif kind == 'tailoring':
                args.update(jdId=jd_id, resumeId=resume_id)
            elif kind == 'question_generation':
                args.update(analysisJobId=analysis_job_id, candidateId=candidate_id, questionCount=question_count)
            else:
                args.update(resumeVersionId=resume_version_id)
            child = agent_runs.create_run_in_transaction(db, user_id, RunCreate(**args))
            return {'resultRef': 'run:' + child.id, 'runId': child.id, 'kind': kind,
                    'status': child.status, 'message': '任务已受理；完成后读取真实结果再继续。'}
        return execute('start_task', runtime, submit, write=True)

    @tool
    def get_task(task_id: str, runtime: ToolRuntime) -> dict:
        """Read a real task's status/result, pending clarification questions and resume artifact IDs."""
        def read(db, user_id, _):
            snapshot = agent_runs.run_snapshot(db, user_id, task_id)
            return {**snapshot, 'artifacts': agent_runs.run_artifacts(db, user_id, task_id),
                    'resultRef': 'run:' + task_id}
        return execute('get_task', runtime, read)

    @tool
    def answer_task(task_id: str, action_id: str, answers: dict[str, str], runtime: ToolRuntime) -> dict:
        """Submit the user's actual answer to a pending input action from get_task. Do not invent answers."""
        def respond(db, user_id, _):
            from backend.schemas.agent_runs import ActionResponse
            child = agent_runs.answer_action(db, user_id, task_id, action_id,
                ActionResponse(decision='submit', answers=answers, expectedRevision=1))
            return {'resultRef': 'run:' + child.id, 'runId': child.id, 'status': child.status}
        return execute('answer_task', runtime, respond, write=True)

    @tool
    def save_job(title: str, company: str, text: str, runtime: ToolRuntime, source_url: str | None = None) -> dict:
        """Save a pasted job description. Use only supplied text; saving does not parse or match it."""
        def save(db, user_id, _):
            from backend.services import jobs
            from backend.schemas.jobs import JobCreate
            row, created = jobs.capture_job(db, user_id, JobCreate(title=title, company=company, text=text, sourceUrl=source_url))
            return {'resultRef': f'jd:{row.id}', 'jdId': row.id, 'created': created}
        return execute('save_job', runtime, save, write=True)

    @tool
    def list_applications(runtime: ToolRuntime, application_id: int | None = None) -> dict:
        """Read application counts by company, position and status plus compact records.

        Counts describe applications, not unique companies. For notes, schedules or submitted
        materials of one record, pass its application_id. IDs can also start an interview.
        """
        def read(db, user_id, _):
            if application_id is not None:
                from backend.routes.applications import _record, _find_application
                return {'application': _record(_find_application(db, user_id, application_id)).model_dump(mode='json')}
            rows = db.execute(select(JobApplication.id, JobApplication.company, JobApplication.position,
                JobApplication.applied_date, JobApplication.status).where(
                JobApplication.user_id == user_id).order_by(JobApplication.updated_at.desc())).all()
            return {
                'total': len(rows),
                'by_company': dict(Counter(row.company for row in rows)),
                'by_position': dict(Counter(row.position for row in rows)),
                'by_status': dict(Counter(row.status for row in rows)),
                'applications': [dict(row._mapping, applied_date=row.applied_date.isoformat()) for row in rows],
            }
        return execute('list_applications', runtime, read)

    @tool
    def record_application(company: str, position: str, applied_date: str, runtime: ToolRuntime,
                           resume_id: int | None = None, jd_id: int | None = None,
                           resume_version_id: str | None = None, notes: str = '') -> dict:
        """Record an application the user says they made (YYYY-MM-DD). Does not submit any external form.

        Optional jd_id and resume_version_id must be supplied together and reference a confirmed version.
        Never treat a pending draft as submitted material.
        """
        def create(db, user_id, _):
            from backend.schemas.applications import ApplicationCreate
            from backend.routes.applications import _find_resume, _append_status_event
            from backend.services.applications import attach_submission
            request = ApplicationCreate(company=company, position=position, applied_date=applied_date,
                resume_id=resume_id, jd_id=jd_id, resume_version_id=resume_version_id, notes=notes)
            _find_resume(db, user_id, resume_id)
            row = JobApplication(user_id=user_id, **request.model_dump(exclude={'jd_id', 'resume_version_id'}))
            db.add(row)
            db.flush()
            if jd_id is not None:
                row = attach_submission(db, user_id, row.id, jd_id, resume_version_id)
            _append_status_event(db, row, 'applied',
                changed_at=datetime.combine(request.applied_date, time(), timezone.utc), touch_application=False)
            return {'resultRef': f'application:{row.id}', 'applicationId': row.id, 'status': row.status}
        return execute('record_application', runtime, create, write=True)

    @tool
    def update_application_status(application_id: int, status: str, runtime: ToolRuntime, note: str = '') -> dict:
        """Update an application when the user reports progress. Status values follow the application's schema:
        applied, assessment, written_test, interviewing, first_interview, second_interview, third_interview,
        hr_interview, offer, resume_rejected, assessment_rejected, written_test_rejected, interview_rejected,
        passed, withdrawn. Do not infer a changed status without the user's report.
        """
        def update(db, user_id, _):
            from backend.schemas.applications import ApplicationStatusEventCreate
            from backend.routes.applications import _find_application, _append_status_event
            request = ApplicationStatusEventCreate(status=status, note=note)
            row = _find_application(db, user_id, application_id)
            _append_status_event(db, row, request.status, note=note)
            return {'resultRef': f'application:{row.id}', 'applicationId': row.id, 'status': row.status}
        return execute('update_application_status', runtime, update, write=True)

    @tool
    def start_interview(application_id: int, runtime: ToolRuntime) -> dict:
        """Start a persisted mock interview from an application with confirmed submission materials.
        First question is generated asynchronously; use get_interview after the task completes.
        """
        def create(db, user_id, request_id):
            from backend.schemas.interviews import InterviewCreate
            from backend.services import interviews
            result = interviews.create_interview(db, user_id, InterviewCreate(applicationId=application_id, requestId=request_id))
            child = agent_runs.get_run(db, user_id, result['runId'])
            return {**result, 'status': child.status, 'resultRef': 'interview:' + result['interviewId']}
        return execute('start_interview', runtime, create, write=True)

    @tool
    def get_interview(interview_id: str, runtime: ToolRuntime) -> dict:
        """Read the frozen materials, generated interview questions, user answers and feedback."""
        def read(db, user_id, _):
            from backend.services.interviews import interview_snapshot
            return {**interview_snapshot(db, user_id, interview_id), 'resultRef': 'interview:' + interview_id}
        return execute('get_interview', runtime, read)

    @tool
    def answer_interview(interview_id: str, expected_turn: int, answer: str, runtime: ToolRuntime) -> dict:
        """Submit the user's verbatim interview answer for the current turn; queues feedback/next question."""
        def respond(db, user_id, request_id):
            from backend.schemas.interviews import AnswerCommand, AnswerPayload
            from backend.services.interview_commands import handle_command
            result = handle_command(db, user_id, interview_id, AnswerCommand(type='answer.submit',
                clientMessageId=request_id, expectedTurn=expected_turn, payload=AnswerPayload(text=answer)))
            child = agent_runs.get_run(db, user_id, result['resultRef'])
            return {'resultRef': 'interview:' + interview_id, 'runId': child.id, 'status': child.status}
        return execute('answer_interview', runtime, respond, write=True)

    return [list_documents, read_document, start_task, get_task, answer_task, save_job,
            list_applications, record_application, update_application_status,
            start_interview, get_interview, answer_interview]
