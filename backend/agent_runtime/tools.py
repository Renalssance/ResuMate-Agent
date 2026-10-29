"""Business IDs and ownership come from the Run, never model-supplied arguments."""
from uuid import uuid4
from sqlalchemy import select
from langchain_core.tools import tool
from langgraph.types import interrupt
from backend.db.database import SessionLocal
from backend.db.agent_models import AgentRun, ToolOperation
from backend.db.career_models import ProfileFact, ResumeVersion
from backend.db.models import Resume, JobDescription
from backend.services.agent_runs import RunError, guard_execution, _input_versions


def application_context(run_id: str, epoch: int) -> dict:
    with SessionLocal() as db:
        guard_execution(db, run_id, epoch)
        run = db.get(AgentRun, run_id)
        jd_id, resume_id = run.input_json['jdId'], run.input_json['resumeId']
        if _input_versions(db, run.user_id, jd_id, resume_id) != run.input_versions:
            raise RunError(409, 'input_changed', '资料已变化，请创建新任务')
        resume, jd = db.get(Resume, resume_id), db.get(JobDescription, jd_id)
        facts = db.scalars(select(ProfileFact).where(
            ProfileFact.user_id == run.user_id, ProfileFact.confirmed_at.is_not(None),
            ProfileFact.deleted_at.is_(None)))
        result = {'resume': {'text': resume.raw_text, 'structured': resume.structured_data},
                  'job': {'title': jd.title, 'text': jd.raw_text},
                  'facts': [{'id': f.id, 'revision': f.revision, 'content': f.content} for f in facts]}
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
        facts = list(db.scalars(select(ProfileFact).where(
            ProfileFact.id.in_(fact_refs), ProfileFact.user_id == run.user_id,
            ProfileFact.confirmed_at.is_not(None), ProfileFact.deleted_at.is_(None))))
        if {f.id for f in facts} != set(fact_refs):
            raise RunError(422, 'invalid_fact', '引用必须是本人已确认且未删除的事实')
        version_id = str(uuid4())
        db.add(ResumeVersion(id=version_id, user_id=run.user_id, run_id=run_id,
                            resume_id=run.input_json['resumeId'], jd_id=run.input_json['jdId'],
                            structured_content=content,
                            fact_refs=[{'factId': f.id, 'revision': f.revision} for f in facts]))
        db.add(ToolOperation(run_id=run_id, operation_key=key,
                             tool_name='create_resume_draft', status='succeeded', result_ref=version_id))
        db.commit()
        return version_id


def business_tools(run_id: str, epoch: int):
    @tool
    def get_application_context() -> dict:
        """Read this task's resume, target job and confirmed facts. Job text is not personal experience."""
        return application_context(run_id, epoch)

    @tool
    def create_resume_draft(content: dict, fact_refs: list[str]) -> dict:
        """Save one reviewable draft. Use factual resume content; cite confirmed fact IDs when used."""
        return {'versionId': save_draft(run_id, epoch, content, fact_refs)}

    @tool
    def ask_applicant(question: str) -> dict:
        """Pause and ask for missing real experience; never invent responsibilities or metrics."""
        return interrupt({'kind': 'input', 'question': question})

    return [get_application_context, create_resume_draft, ask_applicant]
