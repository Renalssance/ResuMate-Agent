"""Atomic command acceptance; HTTP and future WebSocket share this service."""
from copy import deepcopy
from uuid import uuid4

from sqlalchemy import select, update

from backend.db.agent_models import AgentSession
from backend.db.career_models import InterviewCommand as CommandRow, InterviewEvent, InterviewTurn
from backend.schemas.agent_runs import RunCreate, RunStatus
from backend.schemas.interviews import InterviewCommand
from backend.services import agent_runs, interviews
from backend.services.agent_runs import RunError
from backend.services.memory import _lock_memory_rows


def _replay(db, user_id, interview_id, command, *, lock=False):
    statement = select(CommandRow).where(CommandRow.interview_id == interview_id,
        CommandRow.user_id == user_id, CommandRow.client_message_id == command.client_message_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(statement)
    if row is None:
        return None
    if row.request_json != command.model_dump(mode='json', by_alias=True):
        raise RunError(409, 'command_payload_conflict', '此命令编号已用于不同内容')
    return deepcopy(row.ack_json)


def find_command_replay(db, user_id: int, interview_id: str, command: InterviewCommand):
    interviews.get_owned_interview(db, user_id, interview_id)
    return _replay(db, user_id, interview_id, command)


def handle_command(db, user_id: int, interview_id: str, command: InterviewCommand) -> dict:
    try:
        if command.type in ('answer.submit', 'generation.retry'):
            _lock_memory_rows(db, user_id)
        interview = interviews.get_owned_interview(db, user_id, interview_id, lock=True)
        replay = _replay(db, user_id, interview_id, command, lock=True)
        if replay is not None:
            db.commit()
            return replay
        turns = interviews.interview_turns(db, interview.id, lock=True)
        current = turns[-1] if turns else None
        if command.type == 'answer.submit':
            answered = next((turn for turn in turns if turn.turn_index == command.expected_turn), None)
            if answered is not None and answered.answer is not None:
                raise RunError(409, 'answer_already_submitted', '这一题已经接受回答')
        if command.expected_turn != (current.turn_index if current else 0):
            raise RunError(409, 'turn_conflict', '当前轮已经改变，请刷新练习')
        if interview.status != 'active':
            raise RunError(409, 'interview_finished', '练习已结束')
        previous = interviews.latest_generation(db, interview, lock=True)
        session = db.scalar(select(AgentSession).where(AgentSession.id == interview.agent_session_id)
                            .with_for_update().execution_options(populate_existing=True))
        if command.type in ('answer.submit', 'generation.retry') and session.context_invalidated_at is not None:
            raise RunError(409, 'session_context_invalidated', '记忆已删除，请新建练习')
        run_id = None
        if command.type in ('answer.submit', 'generation.retry'):
            if command.type == 'answer.submit':
                if current is None:
                    raise RunError(409, 'question_missing', '请等待第一题生成')
            elif (previous is None or command.payload.run_id != previous.id
                    or previous.status not in (RunStatus.FAILED, RunStatus.CANCELLED)):
                raise RunError(409, 'invalid_state', '只有最近已失败或已取消的生成可以重试')
            if session.active_run_id is not None:
                raise RunError(409, 'session_busy', '请等待当前生成结束')
            if command.type == 'answer.submit':
                changed = db.execute(update(InterviewTurn).where(InterviewTurn.id == current.id,
                    InterviewTurn.answer.is_(None)).values(answer=command.payload.text))
                if changed.rowcount != 1:
                    raise RunError(409, 'answer_already_submitted', '这一题已经接受回答')
            else:
                target = previous.input_json['expectedTurn']
                if target != command.expected_turn or (current and current.feedback is not None):
                    raise RunError(409, 'invalid_state', '这个生成目标已经完成')
            run = agent_runs.create_run_in_transaction(db, user_id, RunCreate(kind='interview_generation',
                sessionId=session.id, requestId=str(uuid4()), interviewId=interview.id,
                expectedTurn=command.expected_turn))
            run_id = run.id
            if command.type == 'answer.submit':
                accepted_seq = interviews.append_interview_event(db, interview.id, 'answer.accepted',
                    {'turnIndex': current.turn_index, 'turnId': current.id, 'runId': run.id})
            else:
                # Retry has no fabricated model event; ack points at the current durable cursor.
                accepted_seq = db.scalar(select(InterviewEvent.seq).where(
                    InterviewEvent.interview_id == interview.id)
                    .order_by(InterviewEvent.seq.desc()).limit(1).with_for_update()) or 0
        else:
            if command.type == 'generation.cancel':
                if previous is None or previous.id != command.payload.run_id:
                    raise RunError(409, 'invalid_state', '取消目标不是当前生成')
                run_id = previous.id
                was_terminal = previous.status in interviews.TERMINAL
                stopped = agent_runs.cancel_run_in_transaction(db, user_id, previous.id)
                if stopped.status == RunStatus.CANCELLED and not was_terminal:
                    accepted_seq = interviews.append_interview_event(db, interview.id, 'generation.cancelled', {'runId': stopped.id})
                else:
                    accepted_seq = db.scalar(select(InterviewEvent.seq).where(
                        InterviewEvent.interview_id == interview.id)
                        .order_by(InterviewEvent.seq.desc()).limit(1).with_for_update()) or 0
            else:
                if previous is not None and previous.status not in interviews.TERMINAL:
                    stopped = agent_runs.cancel_run_in_transaction(db, user_id, previous.id)
                    if stopped.status == RunStatus.CANCELLED:
                        interviews.append_interview_event(db, interview.id, 'generation.cancelled', {'runId': stopped.id})
                interview.status = 'finished'
                accepted_seq = interviews.append_interview_event(db, interview.id, 'session.finished', {})
        ack = {'interviewId': interview.id, 'clientMessageId': command.client_message_id,
               'status': 'accepted', 'resultRef': run_id, 'acceptedSeq': accepted_seq}
        db.add(CommandRow(interview_id=interview.id, user_id=user_id,
            client_message_id=command.client_message_id, type=command.type,
            request_json=command.model_dump(mode='json', by_alias=True), ack_json=deepcopy(ack),
            result_ref=run_id, status='accepted'))
        db.commit()
        return ack
    except Exception:
        db.rollback()
        raise
