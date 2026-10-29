"""Authoritative Run lifecycle. Does not execute models or publish queue messages."""
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.agent_models import AgentAction, AgentRun, AgentRunEvent, AgentSession
from backend.db.models import JobDescription, Resume, utcnow
from backend.schemas.agent_runs import ActionResponse, RunCreate, RunStatus


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


def _input_versions(db: Session, user_id: int, jd_id: int, resume_id: int) -> dict:
    resume = db.scalar(select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id))
    jd = db.scalar(select(JobDescription).where(JobDescription.id == jd_id, JobDescription.user_id == user_id))
    if resume is None or jd is None:
        raise RunError(404, 'not_found', '简历或岗位不存在')
    # Existing document timestamps are stored as UTC without timezone in SQL.
    return {'resume': resume.updated_at.replace(tzinfo=None).isoformat(),
            'jd': jd.updated_at.replace(tzinfo=None).isoformat()}


def _existing_request(db: Session, user_id: int, request: RunCreate) -> AgentRun | None:
    run = db.scalar(select(AgentRun).where(AgentRun.user_id == user_id, AgentRun.request_id == request.request_id))
    if run is not None and (
        run.kind != request.kind
        or run.input_json != {'jdId': request.jd_id, 'resumeId': request.resume_id}
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
    versions = _input_versions(db, user_id, request.jd_id, request.resume_id)
    if request.session_id:
        session = db.scalar(select(AgentSession).where(AgentSession.id == request.session_id, AgentSession.user_id == user_id))
        if session is None:
            raise RunError(404, 'not_found', '会话不存在')
    else:
        session = AgentSession(id=str(uuid4()), user_id=user_id, purpose=request.kind)
        db.add(session)
    run = AgentRun(id=str(uuid4()), user_id=user_id, session_id=session.id,
                   request_id=request.request_id, kind=request.kind,
                   input_json={'jdId': request.jd_id, 'resumeId': request.resume_id},
                   input_versions=versions)
    try:
        # Flush session explicitly because these models intentionally have no ORM relationship.
        db.flush()
        db.add(run)
        db.flush()
        _claim_session(db, user_id, session.id, run.id)
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
    # A running call stops cooperatively in T04/T05. Do not claim it stopped here.
    db.commit()
    db.refresh(run)
    return run


def retry_run(db: Session, user_id: int, run_id: str) -> AgentRun:
    run = get_run(db, user_id, run_id, lock=True)
    if run.status != RunStatus.FAILED:
        raise RunError(409, 'invalid_state', '只有失败任务可以重试')
    try:
        versions = _input_versions(db, user_id, run.input_json['jdId'], run.input_json['resumeId'])
    except RunError as error:
        raise RunError(409, 'input_changed', '原资料已删除，请创建新任务') from error
    if versions != run.input_versions:
        raise RunError(409, 'input_changed', '资料已变化，请创建新任务')
    _claim_session(db, user_id, run.session_id, run.id)
    run.status = RunStatus.QUEUED
    run.attempt += 1
    run.error_code = None
    run.cancel_requested_at = None
    run.heartbeat_at = None
    db.commit()
    return run


def run_snapshot(db: Session, user_id: int, run_id: str) -> dict:
    run = get_run(db, user_id, run_id)
    last_seq = db.scalar(select(func.max(AgentRunEvent.seq)).where(AgentRunEvent.run_id == run.id)) or 0
    actions = db.scalars(select(AgentAction).where(AgentAction.run_id == run.id, AgentAction.status == 'pending')).all()
    return {
        'runId': run.id, 'sessionId': run.session_id, 'status': run.status,
        'kind': run.kind, 'input': run.input_json, 'inputVersions': run.input_versions,
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
        recovered += 1
    db.commit()
    return recovered
