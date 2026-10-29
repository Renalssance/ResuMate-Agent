"""Business IDs and ownership come from the Run, never model-supplied arguments."""
from contextlib import contextmanager
from uuid import uuid4
from sqlalchemy import select
from langchain_core.tools import tool
from langchain.tools import ToolRuntime
from langgraph.errors import GraphInterrupt
from langgraph.types import interrupt
from backend.db.database import SessionLocal
from backend.db.agent_models import AgentRun, ToolOperation
from backend.db.career_models import ProfileFact, ResumeVersion
from backend.db.models import Resume, JobDescription
from backend.services.agent_runs import RunError, guard_execution, _input_versions
from backend.services.run_events import append_event
from backend.services.profile_facts import latest_statement


def application_context(run_id: str, epoch: int) -> dict:
    with SessionLocal() as db:
        guard_execution(db, run_id, epoch)
        run = db.get(AgentRun, run_id)
        jd_id, resume_id = run.input_json['jdId'], run.input_json['resumeId']
        document_versions = _input_versions(db, run.user_id, jd_id, resume_id)
        if any(run.input_versions.get(key) != value for key, value in document_versions.items()):
            raise RunError(409, 'input_changed', '资料已变化，请创建新任务')
        resume, jd = db.get(Resume, resume_id), db.get(JobDescription, jd_id)
        frozen = {ref['factId']: ref['revision'] for ref in run.input_versions.get('facts', [])}
        facts = db.scalars(select(ProfileFact).where(
            ProfileFact.id.in_(frozen), ProfileFact.user_id == run.user_id))
        result = {'resume': {'text': resume.raw_text, 'structured': resume.structured_data},
                  'job': {'title': jd.title, 'text': jd.raw_text},
                  'facts': [{'id': f.id, 'revision': f.revision, 'content': f.content}
                            for f in facts if frozen[f.id] == f.revision]}
        db.commit()
        return result


def save_draft(run_id: str, epoch: int, content: dict, fact_refs: list[str]) -> str:
    with SessionLocal() as db:
        guard_execution(db, run_id, epoch)
        run = db.get(AgentRun, run_id)
        key = f"draft:{run.input_json['jdId']}:initial"
        existing = db.scalar(select(ToolOperation).where(
            ToolOperation.run_id == run_id, ToolOperation.operation_key == key))
        if existing and existing.status == 'succeeded':
            db.commit()
            return existing.result_ref
        frozen = {ref['factId']: ref['revision'] for ref in run.input_versions.get('facts', [])}
        if not set(fact_refs).issubset(frozen):
            raise RunError(422, 'invalid_fact', '引用必须来自该任务固定的已确认事实')
        facts = list(db.scalars(select(ProfileFact).where(
            ProfileFact.id.in_(fact_refs), ProfileFact.user_id == run.user_id,
            ProfileFact.confirmed_at.is_not(None), ProfileFact.deleted_at.is_(None))))
        deleted_families = set(db.scalars(latest_statement(run.user_id).with_only_columns(
            ProfileFact.fact_key).where(ProfileFact.fact_key.in_([fact.fact_key for fact in facts]),
                                       ProfileFact.deleted_at.is_not(None))))
        if ({f.id for f in facts if frozen[f.id] == f.revision} != set(fact_refs)
                or deleted_families):
            raise RunError(422, 'invalid_fact', '引用事实已删除或不属于该任务')
        version_id = str(uuid4())
        db.add(ResumeVersion(id=version_id, user_id=run.user_id, run_id=run_id,
                            resume_id=run.input_json['resumeId'], jd_id=run.input_json['jdId'],
                            structured_content=content,
                            fact_refs=[{'factId': f.id, 'revision': f.revision} for f in facts]))
        db.add(ToolOperation(run_id=run_id, operation_key=key,
                             tool_name='create_resume_draft', status='succeeded', result_ref=version_id))
        append_event(db, run_id, 'artifact.created', {'artifact_id': version_id, 'kind': 'resume_version'})
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


def business_tools(run_id: str, epoch: int):
    @tool
    def get_application_context(runtime: ToolRuntime) -> dict:
        """Read this task's resume, target job and confirmed facts. Job text is not personal experience."""
        with _tool_execution(run_id, epoch, 'get_application_context', runtime.tool_call_id):
            return application_context(run_id, epoch)

    @tool
    def create_resume_draft(content: dict, fact_refs: list[str], runtime: ToolRuntime) -> dict:
        """Save one reviewable draft. Use factual resume content; cite confirmed fact IDs when used."""
        with _tool_execution(run_id, epoch, 'create_resume_draft', runtime.tool_call_id) as result:
            result['result_ref'] = save_draft(run_id, epoch, content, fact_refs)
            return {'versionId': result['result_ref']}

    @tool
    def ask_applicant(question: str, runtime: ToolRuntime) -> dict:
        """Pause and ask for missing real experience; never invent responsibilities or metrics."""
        with _tool_execution(run_id, epoch, 'ask_applicant', runtime.tool_call_id):
            return interrupt({'kind': 'input', 'question': question})

    return [get_application_context, create_resume_draft, ask_applicant]
