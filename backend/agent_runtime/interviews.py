"""One real SDK graph generation, then one fenced SQL interview step commit."""
import logging
from sqlalchemy import select
from langchain_core.messages import HumanMessage, RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.checkpoint.sqlite import SqliteSaver
from openai import APIConnectionError, APITimeoutError, APIStatusError

from backend.agent_runtime.factory import build_interview_agent
from backend.agent_runtime.interview_context import read_context, validate_step
from backend.agent_runtime.telemetry import RunTelemetry, SDKToolTelemetry
from backend.db.database import SessionLocal
from backend.db.agent_models import AgentRun, ToolOperation
from backend.db.career_models import InterviewTurn, InterviewEvent
from backend.schemas.agent_runs import RunStatus
from backend.services.agent_runs import RunError
from backend.services.interviews import guard_interview_execution, finish_interview_generation, append_interview_event
from backend.services.realtime_bus import publish_interview_hint_sync

logger = logging.getLogger(__name__)


def _notify(interview_id):
    try:
        with SessionLocal() as db:
            seq = db.scalar(select(InterviewEvent.seq).where(InterviewEvent.interview_id == interview_id)
                .order_by(InterviewEvent.seq.desc()).limit(1)) or 0
        publish_interview_hint_sync(interview_id, seq)
    except Exception:
        logger.warning('Interview notification unavailable; SQL events remain available')


def _persist_step(run_id, epoch, output):
    with SessionLocal() as db:
        run, interview, turns = guard_interview_execution(db, run_id, epoch)
        step = validate_step(output, read_context(db, run, interview, turns))
        expected = run.input_json['expectedTurn']
        result = {'interviewId': interview.id, 'expectedTurn': expected, **step}
        if step['feedback'] is not None:
            turns[-1].feedback = step['feedback']
            append_interview_event(db, interview.id, 'feedback.ready',
                {'runId': run.id, 'turnIndex': expected, 'turnId': turns[-1].id})
        if step['question'] is not None:
            question = step['question']
            row = InterviewTurn(interview_id=interview.id, turn_index=expected + 1,
                question=question['text'], question_context={'mode': question['mode'], 'refs': question['refs']})
            db.add(row)
            db.flush()
            result['question'] = {**question, 'turnIndex': row.turn_index}
            append_interview_event(db, interview.id, 'question.completed',
                {'runId': run.id, 'turnIndex': row.turn_index, 'turnId': row.id})
        else:
            interview.status = 'finished'
            append_interview_event(db, interview.id, 'session.finished', {'runId': run.id})
        db.add(ToolOperation(run_id=run.id, operation_key='interview:step',
            tool_name='interview_step', status='succeeded', result_ref=interview.id))
        finish_interview_generation(db, run_id, epoch, RunStatus.SUCCEEDED, result_json=result,
                                   output_refs=[{'type': 'interview', 'id': interview.id}])
    _notify(result['interviewId'])


def run_interview_generation(run_id: str, epoch: int) -> None:
    from backend.worker_tasks import state_directory
    telemetry, interview_id = None, None
    try:
        with SessionLocal() as db:
            run, interview, _turns = guard_interview_execution(db, run_id, epoch)
            user_id, session_id, interview_id = run.user_id, run.session_id, interview.id
            telemetry = RunTelemetry(run)
            db.commit()
        with SqliteSaver.from_conn_string(str(state_directory() / 'checkpoints.sqlite')) as saver:
            agent = build_interview_agent(user_id, saver, run_id=run_id, epoch=epoch, telemetry=telemetry)
            config = {'configurable': {'thread_id': session_id}, 'recursion_limit': 80}
            if telemetry.enabled:
                config['callbacks'] = [SDKToolTelemetry(telemetry)]
            state = agent.get_state(config)
            if state.values.get('run_id') != run_id:
                if state.values:
                    agent.update_state(config, {'files': {path: None for path in state.values.get('files', {})},
                        'todos': [], '_summarization_event': None, '_summarization_session_id': None,
                        'structured_response': None})
                graph_input = {'run_id': run_id, 'messages': [RemoveMessage(id=REMOVE_ALL_MESSAGES),
                    HumanMessage(content='请依据冻结材料和本轮已接受回答，生成本轮 InterviewStep。')]}
            elif state.next:
                graph_input = None
            else:
                _persist_step(run_id, epoch, state.values.get('structured_response'))
                return
            output = agent.invoke(graph_input, config)
            _persist_step(run_id, epoch, output.get('structured_response'))
    except Exception as error:
        code = error.code if isinstance(error, RunError) else 'agent_failed'
        transient = isinstance(error, (APIConnectionError, APITimeoutError)) or (
            isinstance(error, APIStatusError) and (error.status_code == 429 or error.status_code >= 500))
        with SessionLocal() as db:
            finish_interview_generation(db, run_id, epoch, RunStatus.FAILED, error_code=code, retry=transient)
        if interview_id:
            _notify(interview_id)
        logger.warning('Interview Run %s stopped (%s)', run_id, type(error).__name__)
    finally:
        if telemetry is not None and telemetry.enabled:
            try:
                with SessionLocal() as db:
                    telemetry.finish(db.get(AgentRun, run_id))
            except Exception:
                telemetry.disable()
