"""Authoritative Run lifecycle. Does not execute models or publish queue messages."""
from datetime import timezone
from uuid import uuid4

from sqlalchemy import and_, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.agent_models import AgentAction, AgentRun, AgentRunEvent, AgentSession
from backend.db.career_models import ResumeVersion
from backend.db.models import JobDescription, Resume, utcnow
from backend.schemas.agent_runs import ActionResponse, RunCreate, RunStatus
from backend.services.run_events import append_event


class RunError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


def get_run(db: Session, user_id: int, run_id: str, *, lock=False) -> AgentRun:
    statement = select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user_id)
    if lock:
        statement = statement.with_for_update()
    run = db.scalar(statement)
    if run is None:
        raise RunError(404, 'not_found', '任务不存在')
    return run


def list_runs(db: Session, user_id: int, *, limit: int = 20, offset: int = 0) -> dict:
    runs = list(db.scalars(select(AgentRun).where(AgentRun.user_id == user_id)
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc()).offset(offset).limit(limit + 1)))
    # SQL stores UTC without timezone; keep the offset explicit for browser parsing.
    return {
        'items': [{
            'runId': run.id, 'sessionId': run.session_id, 'kind': run.kind,
            'status': run.status,
            'createdAt': run.created_at.replace(tzinfo=timezone.utc).isoformat(),
            'updatedAt': run.updated_at.replace(tzinfo=timezone.utc).isoformat(),
            'input': _public_input(run), 'errorCode': run.error_code,
        } for run in runs[:limit]],
        'hasMore': len(runs) > limit,
    }


def run_artifacts(db: Session, user_id: int, run_id: str) -> list[dict]:
    run = get_run(db, user_id, run_id)
    if run.kind == 'resume_export':
        from backend.services.resume_export import pdf_artifact
        artifact = pdf_artifact(run)
        return [artifact] if artifact else []
    versions = list(db.scalars(select(ResumeVersion).where(
        ResumeVersion.run_id == run_id, ResumeVersion.user_id == user_id,
    ).order_by(ResumeVersion.created_at.desc(), ResumeVersion.id.desc())))
    from backend.services.resume_versions import serialize_version
    from backend.agent_runtime.context import changed_inputs
    input_changes = changed_inputs(db, run) if versions else []
    return [{'kind': 'resume_version', **serialize_version(db, user_id, version, input_changes=input_changes)}
            for version in versions]


def _public_input(run: AgentRun) -> dict:
    keys = ('resumeVersionId',) if run.kind == 'resume_export' else ('jdId', 'resumeId')
    return {key: run.input_json.get(key) for key in keys}


def _input_versions(db: Session, user_id: int, jd_id: int, resume_id: int) -> dict:
    resume = db.scalar(select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id))
    jd = db.scalar(select(JobDescription).where(JobDescription.id == jd_id, JobDescription.user_id == user_id))
    if resume is None or jd is None:
        raise RunError(404, 'not_found', '简历或岗位不存在')
    # Existing document timestamps are stored as UTC without timezone in SQL.
    return {'resume': resume.updated_at.replace(tzinfo=None).isoformat(),
            'jd': jd.updated_at.replace(tzinfo=None).isoformat()}


def _request_input(request: RunCreate) -> dict:
    if request.kind == 'resume_export':
        return {'resumeVersionId': request.resume_version_id}
    return {'jdId': request.jd_id, 'resumeId': request.resume_id}


def _existing_request(db: Session, user_id: int, request: RunCreate) -> AgentRun | None:
    run = db.scalar(select(AgentRun).where(AgentRun.user_id == user_id, AgentRun.request_id == request.request_id))
    if run is not None and (
        run.kind != request.kind
        or _public_input(run) != _request_input(request)
        or (request.session_id is not None and run.session_id != request.session_id)
    ):
        raise RunError(409, 'request_conflict', '该 requestId 已用于另一项请求')
    return run


def _claim_session(db: Session, user_id: int, session_id: str, run_id: str) -> None:
    result = db.execute(update(AgentSession).where(
        AgentSession.id == session_id, AgentSession.user_id == user_id,
        AgentSession.active_run_id.is_(None),
    ).values(active_run_id=run_id))
    if result.rowcount != 1:
        raise RunError(409, 'session_busy', '当前会话已有活动任务')


def create_run(db: Session, user_id: int, request: RunCreate) -> AgentRun:
    existing = _existing_request(db, user_id, request)
    if existing is not None:
        return existing
    inputs = _request_input(request)
    if request.kind == 'resume_export':
        from backend.services.resume_export import read_confirmed_version
        version = read_confirmed_version(db, user_id, request.resume_version_id)
        versions = {'resumeVersion': version.revision}
    else:
        versions = _input_versions(db, user_id, request.jd_id, request.resume_id)
        from backend.services.profile_facts import latest_facts
        versions['facts'] = [{'factId': fact.id, 'revision': fact.revision} for fact in latest_facts(
            db, user_id, source_document_id=request.resume_id, confirmed_only=True)]
        from backend.agent_runtime.context import capture_context
        inputs['contextSnapshot'] = capture_context(db, user_id, request.jd_id, request.resume_id, versions)
    if request.session_id:
        session = db.scalar(select(AgentSession).where(AgentSession.id == request.session_id, AgentSession.user_id == user_id))
        if session is None:
            raise RunError(404, 'not_found', '会话不存在')
    else:
        session = AgentSession(id=str(uuid4()), user_id=user_id, purpose=request.kind)
        db.add(session)
    run = AgentRun(id=str(uuid4()), user_id=user_id, session_id=session.id,
                   request_id=request.request_id, kind=request.kind,
                   input_json=inputs,
                   input_versions=versions)
    try:
        # Flush session explicitly because these models intentionally have no ORM relationship.
        db.flush()
        db.add(run)
        db.flush()
        _claim_session(db, user_id, session.id, run.id)
        append_event(db, run.id, 'run.status', {'status': run.status})
        db.commit()
    except IntegrityError:
        db.rollback()
        # Another request may have committed the same user/request key while we waited.
        existing = _existing_request(db, user_id, request)
        if existing is not None:
            return existing
        raise
    except RunError:
        db.rollback()
        raise
    return run


def cancel_run(db: Session, user_id: int, run_id: str) -> AgentRun:
    run = get_run(db, user_id, run_id, lock=True)
    if run.status in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED):
        return run
    # Predicate writes also protect SQLite, where SELECT FOR UPDATE is ignored.
    db.execute(update(AgentRun).where(
        AgentRun.id == run.id,
        AgentRun.status.not_in((RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED)),
    ).values(cancel_requested_at=func.coalesce(AgentRun.cancel_requested_at, utcnow())))
    stopped = db.execute(update(AgentRun).where(
        AgentRun.id == run.id,
        AgentRun.status.in_((RunStatus.QUEUED, RunStatus.WAITING_INPUT, RunStatus.WAITING_APPROVAL)),
    ).values(status=RunStatus.CANCELLED))
    if stopped.rowcount == 1:
        db.execute(update(AgentSession).where(
            AgentSession.id == run.session_id, AgentSession.active_run_id == run.id,
        ).values(active_run_id=None))
    if stopped.rowcount == 1:
        append_event(db, run.id, 'run.status', {'status': RunStatus.CANCELLED})
    # A running call stops cooperatively in T04/T05. Do not claim it stopped here.
    db.commit()
    db.refresh(run)
    return run


def retry_run(db: Session, user_id: int, run_id: str) -> AgentRun:
    run = get_run(db, user_id, run_id, lock=True)
    if run.status != RunStatus.FAILED:
        raise RunError(409, 'invalid_state', '只有失败任务可以重试')
    if run.kind == 'resume_export':
        from backend.services.resume_export import read_confirmed_version
        read_confirmed_version(db, user_id, run.input_json['resumeVersionId'],
                               revision=run.input_versions['resumeVersion'])
    else:
        from backend.agent_runtime.context import read_context
        read_context(db, run)
    _claim_session(db, user_id, run.session_id, run.id)
    run.status = RunStatus.QUEUED
    run.attempt += 1
    run.error_code = None
    run.cancel_requested_at = None
    run.heartbeat_at = None
    append_event(db, run.id, 'run.status', {'status': run.status})
    db.commit()
    return run


def run_snapshot(db: Session, user_id: int, run_id: str) -> dict:
    # One SELECT keeps status, pending actions and cursor at the same point in
    # time, including SQLite's legacy SELECT transaction behavior.
    last_sequence = select(func.max(AgentRunEvent.seq)).where(
        AgentRunEvent.run_id == AgentRun.id).correlate(AgentRun).scalar_subquery()
    rows = db.execute(select(AgentRun, last_sequence, AgentAction).outerjoin(
        AgentAction, and_(AgentAction.run_id == AgentRun.id, AgentAction.status == 'pending'),
    ).where(AgentRun.id == run_id, AgentRun.user_id == user_id)
        .execution_options(populate_existing=True)).all()
    if not rows:
        raise RunError(404, 'not_found', '任务不存在')
    run, last_seq, _ = rows[0]
    last_seq = last_seq or 0
    actions = [row[2] for row in rows if row[2] is not None]
    return {
        'runId': run.id, 'sessionId': run.session_id, 'status': run.status,
        'kind': run.kind, 'input': _public_input(run), 'inputVersions': run.input_versions,
        'attempt': run.attempt, 'lastSeq': last_seq, 'errorCode': run.error_code,
        'cancelRequested': run.cancel_requested_at is not None,
        'outputRefs': run.output_refs,
        'actions': [{'actionId': a.id, 'kind': a.kind, 'payload': a.payload, 'revision': 1} for a in actions],
    }


def answer_action(db: Session, user_id: int, run_id: str, action_id: str, response: ActionResponse) -> AgentRun:
    run = get_run(db, user_id, run_id, lock=True)
    action = db.scalar(select(AgentAction).where(AgentAction.id == action_id, AgentAction.run_id == run.id).with_for_update())
    if action is None:
        raise RunError(404, 'not_found', '待处理动作不存在')
    answer = {'decision': response.decision, 'answers': response.answers}
    # Actions are immutable questions from one checkpoint. Answering is the only edit.
    if response.expected_revision != 1:
        raise RunError(409, 'action_conflict', '动作版本已变化')
    if action.status == 'answered':
        if action.response != answer:
            raise RunError(409, 'action_conflict', '该动作已提交不同回答')
        return run
    expected_status = RunStatus.WAITING_INPUT if action.kind == 'input' else RunStatus.WAITING_APPROVAL
    if run.status != expected_status:
        raise RunError(409, 'invalid_state', '任务当前不在等待该动作')
    if (action.kind == 'input' and response.decision != 'submit') or (action.kind == 'approval' and response.decision not in ('approve', 'reject')):
        raise RunError(409, 'invalid_decision', '回答类型与动作不匹配')
    if action.kind == 'input' and not response.answers:
        raise RunError(422, 'invalid_request', '请填写补充信息')
    changed = db.execute(update(AgentAction).where(
        AgentAction.id == action.id, AgentAction.status == 'pending',
    ).values(status='answered', response=answer, answered_at=utcnow()))
    if changed.rowcount != 1:
        db.rollback()
        # SQLite has no SELECT FOR UPDATE, so resolve a concurrently answered action.
        action = db.get(AgentAction, action_id)
        if action.response == answer:
            return get_run(db, user_id, run_id)
        raise RunError(409, 'action_conflict', '该动作已提交不同回答')
    next_status = RunStatus.CANCELLED if response.decision == 'reject' else RunStatus.QUEUED
    changed_run = db.execute(update(AgentRun).where(
        AgentRun.id == run.id, AgentRun.status == expected_status,
    ).values(status=next_status))
    if changed_run.rowcount != 1:
        db.rollback()
        raise RunError(409, 'invalid_state', '任务状态已变化，请刷新后查看')
    if next_status == RunStatus.CANCELLED:
        run.cancel_requested_at = utcnow()
        db.execute(update(AgentSession).where(
            AgentSession.id == run.session_id, AgentSession.active_run_id == run.id,
        ).values(active_run_id=None))
    append_event(db, run.id, 'run.status', {'status': next_status})
    db.commit()
    return run


def claim_run(db: Session, run_id: str) -> int | None:
    """Only one delivery changes queued -> running; duplicates are harmless."""
    claimed = db.execute(update(AgentRun).where(
        AgentRun.id == run_id, AgentRun.status == RunStatus.QUEUED,
        AgentRun.cancel_requested_at.is_(None),
    ).values(status=RunStatus.RUNNING, execution_epoch=AgentRun.execution_epoch + 1,
             heartbeat_at=utcnow()))
    if claimed.rowcount != 1:
        db.rollback()
        return None
    epoch = db.scalar(select(AgentRun.execution_epoch).where(AgentRun.id == run_id))
    append_event(db, run_id, 'run.status', {'status': RunStatus.RUNNING})
    db.commit()
    return epoch


def guard_execution(db: Session, run_id: str, epoch: int) -> None:
    """Acquire a write lock and fence cancellation/stale tools in THEIR transaction."""
    result = db.execute(update(AgentRun).where(
        AgentRun.id == run_id, AgentRun.status == RunStatus.RUNNING,
        AgentRun.execution_epoch == epoch, AgentRun.cancel_requested_at.is_(None),
    ).values(heartbeat_at=utcnow()))
    if result.rowcount != 1:
        raise RunError(409, 'execution_lost', '任务已取消或失去运行权')


def heartbeat_run(db: Session, run_id: str, epoch: int) -> bool:
    result = db.execute(update(AgentRun).where(
        AgentRun.id == run_id, AgentRun.status == RunStatus.RUNNING,
        AgentRun.execution_epoch == epoch,
    ).values(heartbeat_at=utcnow()))
    db.commit()
    return result.rowcount == 1


def finish_run(db: Session, run_id: str, epoch: int, status: RunStatus,
               *, error_code: str | None = None, output_refs: list | None = None,
               retry: bool = False) -> None:
    # First acquire a write lock also on SQLite; read cancellation under that lock.
    changed = db.execute(update(AgentRun).where(
        AgentRun.id == run_id, AgentRun.status == RunStatus.RUNNING,
        AgentRun.execution_epoch == epoch,
    ).values(heartbeat_at=utcnow()))
    if changed.rowcount != 1:
        db.rollback()
        return
    run = db.get(AgentRun, run_id, populate_existing=True)
    if retry and not run.cancel_requested_at and run.attempt < 3:
        status = RunStatus.QUEUED
        run.attempt += 1
    run.status = RunStatus.CANCELLED if run.cancel_requested_at else status
    run.error_code = error_code if run.status == RunStatus.FAILED else None
    if output_refs is not None and run.status != RunStatus.CANCELLED:
        run.output_refs = output_refs
    if run.status in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED):
        db.execute(update(AgentSession).where(
            AgentSession.id == run.session_id, AgentSession.active_run_id == run.id,
        ).values(active_run_id=None))
    append_event(db, run.id, 'run.status', {'status': run.status, 'error_code': run.error_code})
    db.commit()


def recover_stale_runs(db: Session, now=None) -> int:
    """Caller MUST hold the worker execution file lock (proves executor stopped)."""
    from datetime import timedelta
    cutoff = (now or utcnow()) - timedelta(seconds=90)
    ids = list(db.scalars(select(AgentRun.id).where(
        AgentRun.status == RunStatus.RUNNING, AgentRun.heartbeat_at < cutoff)))
    recovered = 0
    for run_id in ids:
        changed = db.execute(update(AgentRun).where(
            AgentRun.id == run_id, AgentRun.status == RunStatus.RUNNING,
            AgentRun.heartbeat_at < cutoff,
        ).values(updated_at=utcnow()))
        if changed.rowcount != 1:
            continue
        run = db.get(AgentRun, run_id, populate_existing=True)
        if run.cancel_requested_at or run.attempt >= 3:
            run.status = RunStatus.CANCELLED if run.cancel_requested_at else RunStatus.FAILED
            run.error_code = None if run.cancel_requested_at else 'worker_lost'
            db.execute(update(AgentSession).where(
                AgentSession.id == run.session_id, AgentSession.active_run_id == run.id,
            ).values(active_run_id=None))
        else:
            run.status = RunStatus.QUEUED
            run.attempt += 1
            run.heartbeat_at = None
        append_event(db, run.id, 'run.status', {'status': run.status, 'error_code': run.error_code})
        recovered += 1
    db.commit()
    return recovered
