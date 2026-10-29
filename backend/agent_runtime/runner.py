"""Resume real graph state; SQL owns actions/artifacts and final Run status."""
import logging
from sqlalchemy import select
from langchain_core.messages import HumanMessage, RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from openai import APIConnectionError, APITimeoutError, APIStatusError
from backend.agent_runtime.factory import build_agent
from backend.db.database import SessionLocal
from backend.db.agent_models import AgentRun, AgentAction
from backend.db.career_models import ResumeVersion
from backend.schemas.agent_runs import RunStatus
from backend.services import agent_runs

logger = logging.getLogger(__name__)


def run_agent(run_id: str, epoch: int) -> None:
    from backend.worker_tasks import state_directory
    try:
        with SessionLocal() as db:
            agent_runs.guard_execution(db, run_id, epoch)
            run = db.get(AgentRun, run_id)
            user_id, session_id = run.user_id, run.session_id
            db.commit()
        with SqliteSaver.from_conn_string(str(state_directory() / 'checkpoints.sqlite')) as saver:
            agent = build_agent(user_id, saver, run_id=run_id, epoch=epoch)
            config = {'configurable': {'thread_id': session_id}, 'recursion_limit': 60}
            state = agent.get_state(config)
            if state.values.get('run_id') != run_id:
                if state.values:
                    # These are SDK-private summary channels; normal input omits them.
                    # Clear task context before starting a new Run on the same thread.
                    agent.update_state(config, {
                        'files': {path: None for path in state.values.get('files', {})},
                        'todos': [], '_summarization_event': None, '_summarization_session_id': None,
                    })
                graph_input = {'run_id': run_id, 'messages': [RemoveMessage(id=REMOVE_ALL_MESSAGES),
                               HumanMessage(content='请根据当前任务资料准备一份待审阅的简历草稿。')]}
            elif state.interrupts:
                with SessionLocal() as db:
                    answers = {a.interrupt_id: a.response['answers'] for a in db.scalars(
                        select(AgentAction).where(AgentAction.run_id == run_id, AgentAction.status == 'answered'))}
                ids = {i.id for i in state.interrupts}
                if not ids.issubset(answers):
                    _save_interrupts(run_id, epoch, state.interrupts)
                    return
                graph_input = Command(resume={key: answers[key] for key in ids})
            elif state.next:
                graph_input = None  # A crashed node is replayed by LangGraph, not by our own loop.
            else:
                _complete(run_id, epoch)
                return
            result = agent.invoke(graph_input, config)
            if result.get('__interrupt__'):
                _save_interrupts(run_id, epoch, result['__interrupt__'])
            else:
                _complete(run_id, epoch)
    except Exception as error:
        # Preserve a concise code, never raw prompts, keys, provider bodies or SQL parameters.
        code = error.code if isinstance(error, agent_runs.RunError) else 'agent_failed'
        transient = isinstance(error, (APIConnectionError, APITimeoutError)) or (
            isinstance(error, APIStatusError) and (error.status_code == 429 or error.status_code >= 500))
        with SessionLocal() as db:
            agent_runs.finish_run(db, run_id, epoch, RunStatus.FAILED,
                                  error_code=code, retry=transient)
        logger.warning('Run %s stopped (%s)', run_id, type(error).__name__)


def _save_interrupts(run_id, epoch, interrupts):
    with SessionLocal() as db:
        agent_runs.guard_execution(db, run_id, epoch)
        for item in interrupts:
            action = db.scalar(select(AgentAction).where(
                AgentAction.run_id == run_id, AgentAction.interrupt_id == item.id))
            if action is None:
                db.add(AgentAction(run_id=run_id, interrupt_id=item.id, kind='input', payload=item.value))
        agent_runs.finish_run(db, run_id, epoch, RunStatus.WAITING_INPUT)


def _complete(run_id, epoch):
    with SessionLocal() as db:
        refs = [{'type': 'resume_version', 'id': version_id} for version_id in db.scalars(
            select(ResumeVersion.id).where(ResumeVersion.run_id == run_id))]
        agent_runs.finish_run(db, run_id, epoch,
                             RunStatus.SUCCEEDED if refs else RunStatus.FAILED,
                             error_code=None if refs else 'no_draft', output_refs=refs)
