"""Frozen interview material and short SQL transactions shared with the worker."""
from copy import deepcopy
from datetime import timezone
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.agent_models import AgentRun, AgentSession
from backend.db.career_models import BusinessMemory, InterviewCommand, InterviewEvent, InterviewSession, InterviewTurn, ResumeVersion
from backend.db.models import JobApplication, JobDescription, utcnow
from backend.schemas.agent_runs import RunCreate, RunStatus
from backend.schemas.interviews import InterviewCreate
from backend.schemas.resume_versions import VersionStatus
from backend.services import agent_runs
from backend.services.agent_runs import RunError
from backend.services.memory import _lock_memory_rows, capture_memory_ids

TERMINAL = (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED)


def get_owned_interview(db: Session, user_id: int, interview_id: str, *, lock=False) -> InterviewSession:
    if lock:
        db.execute(update(InterviewSession).where(InterviewSession.id == interview_id,
            InterviewSession.user_id == user_id).values(status=InterviewSession.status))
    statement = select(InterviewSession).where(InterviewSession.id == interview_id,
                                              InterviewSession.user_id == user_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    interview = db.scalar(statement)
    if interview is None:
        raise RunError(404, 'not_found', '面试会话不存在')
    if not interview.source_snapshot or not interview.agent_session_id:
        raise RunError(409, 'interview_context_missing', '此旧会话缺少冻结材料，请重新开始练习')
    return interview


def interview_turns(db, interview_id, *, lock=False):
    statement = select(InterviewTurn).where(InterviewTurn.interview_id == interview_id).order_by(InterviewTurn.turn_index)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return list(db.scalars(statement))


def latest_generation(db, interview, *, lock=False):
    # Command IDs serialize accepted generations. MySQL DATETIME seconds and random
    # Run UUIDs do not establish order when several synthetic/fast turns share a second.
    statement = select(AgentRun).join(InterviewCommand, InterviewCommand.result_ref == AgentRun.id).where(
        InterviewCommand.interview_id == interview.id,
        InterviewCommand.type.in_(('answer.submit', 'generation.retry')),
        AgentRun.session_id == interview.agent_session_id,
        AgentRun.kind == 'interview_generation').order_by(InterviewCommand.id.desc()).limit(1)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    run = db.scalar(statement)
    if run is not None:
        return run
    # Before the first generating command, the session has exactly one initial Run.
    initial = select(AgentRun).where(AgentRun.session_id == interview.agent_session_id,
                                    AgentRun.kind == 'interview_generation').limit(1)
    if lock:
        initial = initial.with_for_update().execution_options(populate_existing=True)
    return db.scalar(initial)


def find_create_replay(db, user_id, request: InterviewCreate):
    run = db.scalar(select(AgentRun).where(AgentRun.user_id == user_id,
                                          AgentRun.request_id == request.request_id))
    if run is None:
        return None
    if (run.kind != 'interview_generation' or run.input_json.get('expectedTurn') != 0
            or run.input_json.get('applicationId') != request.application_id):
        raise RunError(409, 'request_conflict', '此请求编号已用于不同材料')
    return {'interviewId': run.input_json['interviewId'], 'runId': run.id}


def create_interview(db: Session, user_id: int, request: InterviewCreate) -> dict:
    replay = find_create_replay(db, user_id, request)
    if replay is not None:
        return replay
    try:
        _lock_memory_rows(db, user_id)
        application = db.scalar(select(JobApplication).where(JobApplication.id == request.application_id,
            JobApplication.user_id == user_id).with_for_update().execution_options(populate_existing=True))
        if application is None:
            raise RunError(404, 'not_found', '申请记录不存在')
        if not application.submitted_snapshot or not application.resume_version_id:
            raise RunError(409, 'interview_context_missing', '请先关联已确认的投递材料')
        version = db.scalar(select(ResumeVersion).where(ResumeVersion.id == application.resume_version_id,
            ResumeVersion.user_id == user_id).with_for_update())
        if version is None or version.status != VersionStatus.CONFIRMED:
            raise RunError(409, 'interview_context_missing', '投递材料尚未确认')
        job = db.scalar(select(JobDescription).where(JobDescription.id == application.jd_id,
            JobDescription.user_id == user_id).with_for_update())
        if job is None:
            raise RunError(404, 'not_found', '投递岗位不存在')
        snapshot = deepcopy(application.submitted_snapshot)
        snapshot['applicationId'] = application.id
        snapshot.pop('jdId', None)
        snapshot['job'] = {'jdId': job.id, 'title': job.title, 'company': job.company,
            'rawText': job.raw_text, 'structuredData': deepcopy(job.structured_data),
            'capturedAt': utcnow().replace(tzinfo=timezone.utc).isoformat()}
        session = AgentSession(id=str(uuid4()), user_id=user_id, purpose='interview_generation')
        db.add(session)
        db.flush()
        interview = InterviewSession(id=str(uuid4()), user_id=user_id, application_id=application.id,
            jd_id=job.id, resume_version_id=version.id, agent_session_id=session.id,
            source_snapshot=snapshot)
        db.add(interview)
        db.flush()
        run = agent_runs.create_run_in_transaction(db, user_id, RunCreate(kind='interview_generation',
            sessionId=session.id, requestId=request.request_id, interviewId=interview.id, expectedTurn=0))
        db.commit()
        return {'interviewId': interview.id, 'runId': run.id}
    except (IntegrityError, RunError) as error:
        db.rollback()
        # SQLite can observe the winning Run before insert; MySQL can instead
        # discover it at the unique constraint after an older RR snapshot.
        if isinstance(error, IntegrityError) or error.code == 'request_conflict':
            replay = find_create_replay(db, user_id, request)
            if replay is not None:
                return replay
        raise
    except Exception:
        db.rollback()
        raise


def capture_interview_run(db, user_id, request, inputs):
    # Caller acquired memory before the interview gate; reacquiring is in the same transaction.
    memories = capture_memory_ids(db, user_id)
    interview = get_owned_interview(db, user_id, request.interview_id, lock=True)
    if interview.agent_session_id != request.session_id:
        raise RunError(409, 'interview_command_required', '面试与生成会话不一致')
    if interview.status != 'active':
        raise RunError(409, 'interview_finished', '练习已结束')
    inputs['applicationId'] = interview.source_snapshot['applicationId']
    return {'memories': memories}


def append_interview_event(db, interview_id: str, event_type: str, payload: dict) -> int:
    """Caller holds the InterviewSession write gate; current-read the event tail."""
    db.flush()
    last = db.scalar(select(InterviewEvent.seq).where(InterviewEvent.interview_id == interview_id)
        .order_by(InterviewEvent.seq.desc()).limit(1).with_for_update()) or 0
    db.add(InterviewEvent(interview_id=interview_id, seq=last + 1, type=event_type, payload=deepcopy(payload)))
    db.flush()
    return last + 1


def _lock_interview_run(db, run_id):
    identity = db.execute(select(AgentRun.user_id, AgentRun.input_json).where(
        AgentRun.id == run_id, AgentRun.kind == 'interview_generation')).first()
    if identity is None:
        raise RunError(404, 'not_found', '面试生成不存在')
    _lock_memory_rows(db, identity.user_id)
    interview = get_owned_interview(db, identity.user_id, identity.input_json['interviewId'], lock=True)
    return interview


def guard_interview_execution(db: Session, run_id: str, epoch: int):
    interview = _lock_interview_run(db, run_id)
    agent_runs.guard_execution(db, run_id, epoch)
    run = db.get(AgentRun, run_id, populate_existing=True)
    session = db.scalar(select(AgentSession).where(AgentSession.id == interview.agent_session_id)
                        .with_for_update().execution_options(populate_existing=True))
    turns = interview_turns(db, interview.id, lock=True)
    current_turn = turns[-1].turn_index if turns else 0
    if (interview.status != 'active' or session.active_run_id != run.id
            or current_turn != run.input_json['expectedTurn']
            or (current_turn and (turns[-1].answer is None or turns[-1].feedback is not None))):
        raise RunError(409, 'execution_lost', '面试已结束或当前轮已经改变')
    return run, interview, turns


def finish_interview_generation(db: Session, run_id: str, epoch: int, status: RunStatus,
        *, error_code=None, retry=False, result_json=None, output_refs=None) -> None:
    interview = _lock_interview_run(db, run_id)
    run = db.scalar(select(AgentRun).where(AgentRun.id == run_id)
                    .with_for_update().execution_options(populate_existing=True))
    if run.status != RunStatus.RUNNING or run.execution_epoch != epoch:
        db.rollback()
        return
    if run.cancel_requested_at:
        append_interview_event(db, interview.id, 'generation.cancelled', {'runId': run.id})
    agent_runs.finish_run(db, run_id, epoch, status, error_code=error_code, retry=retry,
                         result_json=result_json, output_refs=output_refs)


def interview_snapshot(db: Session, user_id: int, interview_id: str) -> dict:
    interview = get_owned_interview(db, user_id, interview_id)
    turns = interview_turns(db, interview.id)
    run = latest_generation(db, interview)
    session = db.get(AgentSession, interview.agent_session_id)
    seq = db.scalar(select(InterviewEvent.seq).where(InterviewEvent.interview_id == interview.id)
                    .order_by(InterviewEvent.seq.desc()).limit(1)) or 0
    return {'interviewId': interview.id, 'userId': user_id,
        'applicationId': interview.source_snapshot['applicationId'], 'status': interview.status,
        'currentTurn': turns[-1].turn_index if turns else 0, 'lastSeq': seq,
        'sessionInvalidated': session.context_invalidated_at is not None,
        'sourceSnapshot': deepcopy(interview.source_snapshot),
        'turns': [{'id': row.id, 'turnIndex': row.turn_index, 'question': row.question,
                   'questionContext': deepcopy(row.question_context), 'answer': row.answer,
                   'feedback': deepcopy(row.feedback)} for row in turns],
        'generation': None if run is None else {'runId': run.id, 'status': run.status,
            'errorCode': run.error_code, 'cancelRequested': run.cancel_requested_at is not None}}


def confirm_feedback_memory(db: Session, user_id: int, interview_id: str, turn_index: int,
                            *, confirmed: bool) -> dict:
    from backend.services.memory import serialize
    if confirmed is not True:
        raise RunError(422, 'confirmation_required', '请先确认这段练习重点')
    try:
        _lock_memory_rows(db, user_id)
        interview = get_owned_interview(db, user_id, interview_id, lock=True)
        turn = db.scalar(select(InterviewTurn).where(InterviewTurn.interview_id == interview.id,
            InterviewTurn.turn_index == turn_index).with_for_update().execution_options(populate_existing=True))
        if turn is None or not turn.feedback or not turn.feedback.get('practiceFocus'):
            raise RunError(409, 'feedback_missing', '此轮尚无可确认的练习反馈')
        memory_id = turn.feedback.get('memoryId')
        if memory_id:
            memory = db.get(BusinessMemory, memory_id, populate_existing=True)
            if memory is None or memory.deleted_at is not None:
                raise RunError(409, 'memory_deleted', '这段记忆已删除，不会自动恢复')
            result = serialize(memory)
            db.commit()
            return result
        memory = BusinessMemory(id=str(uuid4()), user_id=user_id, kind='interview_feedback',
            content=turn.feedback['practiceFocus'], confirmed_at=utcnow(),
            source_ref={'kind': 'interview_turn', 'interviewId': interview.id, 'turnId': turn.id})
        db.add(memory)
        db.flush()
        turn.feedback = {**turn.feedback, 'memoryId': memory.id}
        db.commit()
        return serialize(memory)
    except Exception:
        db.rollback()
        raise
