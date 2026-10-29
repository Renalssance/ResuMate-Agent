"""Business IDs and ownership come from the Run, never model-supplied arguments."""
from contextlib import contextmanager
from langchain_core.tools import tool
from langchain.tools import ToolRuntime
from langgraph.errors import GraphInterrupt
from langgraph.types import interrupt
from backend.db.database import SessionLocal
from backend.db.agent_models import AgentRun
from backend.services.agent_runs import RunError, guard_execution
from backend.services.run_events import append_event


def application_context(run_id: str, epoch: int) -> dict:
    from backend.agent_runtime.context import read_context
    with SessionLocal() as db:
        guard_execution(db, run_id, epoch)
        result = read_context(db, db.get(AgentRun, run_id))
        db.commit()
        return result


def save_draft(run_id: str, epoch: int, changes: list) -> str:
    from backend.services.resume_versions import create_draft
    with SessionLocal() as db:
        guard_execution(db, run_id, epoch)
        version_id = create_draft(db, db.get(AgentRun, run_id), changes)
        db.commit()
        return version_id


@contextmanager
def _tool_execution(run_id: str, epoch: int, tool_name: str, call_id: str | None):
    with SessionLocal() as db:
        guard_execution(db, run_id, epoch)
        key = call_id or tool_name
        if tool_name == 'create_resume_draft':
            key = f"draft:{db.get(AgentRun, run_id).input_json['jdId']}:initial"
        payload = {'tool_name': tool_name, 'operation_key': key}
        append_event(db, run_id, 'tool.started', payload)
        db.commit()
    result = {}
    try:
        yield result
    except GraphInterrupt:
        # A request for input is a checkpoint pause, not a failed tool.
        raise
    except Exception as error:
        with SessionLocal() as db:
            guard_execution(db, run_id, epoch)
            append_event(db, run_id, 'tool.failed', {
                **payload, 'error_code': error.code if isinstance(error, RunError) else 'tool_failed',
                'message': '工具执行失败',
            })
            db.commit()
        raise
    else:
        with SessionLocal() as db:
            guard_execution(db, run_id, epoch)
            append_event(db, run_id, 'tool.completed', {**payload, 'result_ref': result.get('result_ref')})
            db.commit()


def context_bundle(run_id: str, epoch: int, *, budget: dict | None = None):
    from backend.agent_runtime.context import build_context
    with SessionLocal() as db:
        guard_execution(db, run_id, epoch)
        result = build_context(db, db.get(AgentRun, run_id), budget=budget)
        db.commit()
        return result


def business_tools(run_id: str, epoch: int, *, inline_token_limit: int = 6000, budget: dict | None = None):
    @tool
    def get_application_context(runtime: ToolRuntime) -> dict:
        """Read this task's resume, target job and confirmed facts. Job text is not personal experience."""
        with _tool_execution(run_id, epoch, 'get_application_context', runtime.tool_call_id):
            from deepagents.backends import StateBackend
            from backend.agent_runtime.context import estimate_tokens, json_text
            from langchain_core.messages import HumanMessage
            bundle = context_bundle(run_id, epoch, budget=budget)
            if estimate_tokens([HumanMessage(content=json_text(bundle.context))]) <= inline_token_limit:
                return bundle.context
            backend = StateBackend()
            for path, content in bundle.files.items():
                backend.write(path, content)
            return {'format': 'artifact_manifest', 'required': bundle.required,
                    'artifacts': bundle.artifacts, 'budget': bundle.budget,
                    'readInstructions': '用 read_file(path,offset,limit) 分段读取；JSON保留精确字段及source_refs；textChunks按顺序以空字符串拼接，还原逐字原文/before。SQL快照为权威，摘要不得作为before。'}

    @tool
    def create_resume_draft(changes: list[dict], runtime: ToolRuntime) -> dict:
        """Save pending field suggestions, preserving the fixed original resume.

        Each change needs section, before, after, reason, fact_refs, requires_input.
        Allowed sections: /self_summary, existing /summary, /work_experience/N/description,
        /projects/N/description. before must equal the fixed field. Missing information:
        requires_input=true and after=null; otherwise cite at least one source.
        Sources: {kind:profile_fact,factId,revision}; or
        {kind:resume,resumeId,inputVersion,section,sourceRefs}; or
        {kind:applicant_answer,actionId} from an answered input in this Run.
        Use get_application_context for exact source values. Job requirements are not evidence.
        """
        with _tool_execution(run_id, epoch, 'create_resume_draft', runtime.tool_call_id) as result:
            result['result_ref'] = save_draft(run_id, epoch, changes)
            return {'versionId': result['result_ref']}

    @tool
    def ask_applicant(question: str, runtime: ToolRuntime) -> dict:
        """Pause and ask for missing real experience; never invent responsibilities or metrics."""
        with _tool_execution(run_id, epoch, 'ask_applicant', runtime.tool_call_id):
            return interrupt({'kind': 'input', 'question': question})

    return [get_application_context, create_resume_draft, ask_applicant]
