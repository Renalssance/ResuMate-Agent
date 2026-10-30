"""Test-only worker barriers and observations for four real process-kill cases."""
import json
import os
from pathlib import Path
import time

from langchain_core.messages import ToolMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from sqlalchemy import select

from backend.agent_runtime import factory, runner, tools
from backend.db.agent_models import AgentAction, AgentRun, AgentRunEvent, ToolOperation
from backend.db.career_models import ResumeVersion
from backend.db.database import SessionLocal
from backend.tests.agent_fixtures import DraftModel
from backend.worker import app  # noqa: F401


def state_root():
    return Path(os.environ['AGENT_STATE_DIR'])


def pause_at(point: str, **details):
    root = state_root()
    if os.getenv('RESUMATE_RECOVERY_POINT') != point or not (root / 'hold').exists():
        return
    (root / 'barrier.json').write_text(json.dumps({'point': point, **details}, ensure_ascii=False))
    deadline = time.monotonic() + 300
    while (root / 'hold').exists():
        if time.monotonic() >= deadline:
            raise RuntimeError('Test barrier was not released')
        time.sleep(0.1)


class RecoveryDraftModel(DraftModel):
    def _generate(self, messages, **kwargs):
        phase = [message.name for message in messages if isinstance(message, ToolMessage)]
        record = {'phase': phase, 'started_at': time.time(), 'pid': os.getpid()}
        with (state_root() / 'model-starts.jsonl').open('a') as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')
        pause_at('recovery-model-before-return', phase=phase)
        return super()._generate(messages, **kwargs)


factory.model_for_user = lambda user_id: RecoveryDraftModel(
    ask=os.getenv('RESUMATE_RECOVERY_POINT') == 'recovery-answer-before-delivery')
_save_draft = tools.save_draft
_complete = runner._complete


def save_then_pause(*args, **kwargs):
    version_id = _save_draft(*args, **kwargs)
    pause_at('recovery-draft-after-commit', version_id=version_id)
    return version_id


def checkpoint_then_pause(run_id, epoch):
    # run_agent calls _complete only after graph.stream ended/checkpoint persisted.
    pause_at('recovery-checkpoint-before-terminal', run_id=run_id, epoch=epoch)
    return _complete(run_id, epoch)


tools.save_draft = save_then_pause
runner._complete = checkpoint_then_pause


def inspect_recovery(run_id: str) -> dict:
    """Invoked in the Linux API container; never a native read of live SQLite."""
    with SessionLocal() as db:
        run = db.get(AgentRun, run_id)
        result = {'run': {'id': run.id, 'session_id': run.session_id, 'status': run.status,
                          'attempt': run.attempt, 'epoch': run.execution_epoch,
                          'heartbeat_at': run.heartbeat_at.isoformat() if run.heartbeat_at else None,
                          'output_refs': run.output_refs, 'error_code': run.error_code},
                  'versions': [{'id': row.id, 'structured_content': row.structured_content,
                                'fact_refs': row.fact_refs} for row in db.scalars(
                                    select(ResumeVersion).where(ResumeVersion.run_id == run_id))],
                  'operations': [{'id': row.id, 'operation_key': row.operation_key,
                                  'status': row.status, 'result_ref': row.result_ref}
                                 for row in db.scalars(select(ToolOperation).where(ToolOperation.run_id == run_id))],
                  'actions': [{'id': row.id, 'interrupt_id': row.interrupt_id,
                               'status': row.status, 'response': row.response}
                              for row in db.scalars(select(AgentAction).where(AgentAction.run_id == run_id))],
                  'events': [{'seq': row.seq, 'type': row.type, 'payload': row.payload}
                             for row in db.scalars(select(AgentRunEvent).where(
                                 AgentRunEvent.run_id == run_id).order_by(AgentRunEvent.seq))]}
        session_id, user_id, epoch = run.session_id, run.user_id, run.execution_epoch
    with SqliteSaver.from_conn_string(str(state_root() / 'checkpoints.sqlite')) as saver:
        agent = factory.build_agent(user_id, saver, run_id=run_id, epoch=epoch)
        state = agent.get_state({'configurable': {'thread_id': session_id}})
        result['checkpoint'] = {'run_id': state.values.get('run_id'), 'next': list(state.next),
                                'interrupts': [item.id for item in state.interrupts],
                                'message_count': len(state.values.get('messages', []))}
    starts = state_root() / 'model-starts.jsonl'
    result['model_starts'] = [json.loads(line) for line in starts.read_text().splitlines()] if starts.exists() else []
    return result
