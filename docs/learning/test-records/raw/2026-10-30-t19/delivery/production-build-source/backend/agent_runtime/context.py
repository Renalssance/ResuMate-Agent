"""Fixed business input for tailoring; live answers remain scoped to their Run."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import timezone
import json

from langchain_core.messages import HumanMessage
from langchain_core.messages.utils import count_tokens_approximately

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.agent_models import AgentAction, AgentRun
from backend.db.career_models import ProfileFact, ResumeVersion
from backend.db.models import AnalysisJob, JobDescription, MatchResult, Resume
from backend.services.agent_runs import RunError
from backend.services.profile_facts import latest_facts


def _documents(db: Session, user_id: int, jd_id: int, resume_id: int):
    resume = db.scalar(select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id))
    job = db.scalar(select(JobDescription).where(JobDescription.id == jd_id, JobDescription.user_id == user_id))
    return resume, job


def _version(document) -> str:
    return document.updated_at.replace(tzinfo=None).isoformat()


def capture_context(db: Session, user_id: int, jd_id: int, resume_id: int, input_versions: dict) -> dict:
    """Capture owned documents, exact confirmed fact versions and existing match advice."""
    resume, job = _documents(db, user_id, jd_id, resume_id)
    if resume is None or job is None:
        raise RunError(404, 'not_found', '简历或岗位不存在')
    frozen = {item['factId']: item['revision'] for item in input_versions.get('facts', [])}
    facts = db.scalars(select(ProfileFact).where(
        ProfileFact.user_id == user_id, ProfileFact.id.in_(frozen),
        ProfileFact.confirmed_at.is_not(None), ProfileFact.deleted_at.is_(None),
    ).order_by(ProfileFact.fact_key))
    match = db.scalar(select(MatchResult).join(AnalysisJob, AnalysisJob.id == MatchResult.job_id).where(
        AnalysisJob.user_id == user_id, MatchResult.resume_id == resume_id, MatchResult.jd_id == jd_id,
    ).order_by(MatchResult.created_at.desc(), MatchResult.id.desc()).limit(1))
    return deepcopy({
        'resume': {'id': resume.id, 'text': resume.raw_text, 'structured': resume.structured_data or {},
                   'inputVersion': input_versions['resume']},
        'job': {'id': job.id, 'title': job.title, 'text': job.raw_text, 'structured': job.structured_data or {},
                'inputVersion': input_versions['jd']},
        'facts': [{'id': fact.id, 'revision': fact.revision, 'content': fact.content}
                  for fact in facts if frozen[fact.id] == fact.revision],
        'match': None if match is None else {
            'id': match.id, 'runId': match.job_id, 'candidateId': match.candidate_id,
            'resumeId': match.resume_id, 'jdId': match.jd_id, 'overallScore': match.overall_score,
            'recommendation': match.recommendation, 'reason': match.reason,
            'dimensionScores': match.dimension_scores, 'matchedSkills': match.matched_skills,
            'missingSkills': match.missing_skills, 'strengths': match.strengths, 'gaps': match.gaps,
            'report': match.report_json, 'createdAt': match.created_at.replace(tzinfo=timezone.utc).isoformat(),
        },
    })


def read_context(db: Session, run: AgentRun) -> dict:
    """Use the original snapshot; callers commit a safe legacy backfill in their transaction."""
    resume, job = _documents(db, run.user_id, run.input_json['jdId'], run.input_json['resumeId'])
    if resume is None or job is None:
        raise RunError(409, 'input_changed', '原资料已删除，请创建新任务')
    snapshot = run.input_json.get('contextSnapshot')
    if snapshot is None:
        if (_version(resume) != run.input_versions.get('resume')
                or _version(job) != run.input_versions.get('jd')):
            raise RunError(409, 'input_changed', '旧任务资料已变化，无法恢复原输入，请创建新任务')
        snapshot = capture_context(db, run.user_id, job.id, resume.id, run.input_versions)
        # Old Runs did not freeze matching reports; current advice is not historical input.
        snapshot['match'] = None
        run.input_json = {**run.input_json, 'contextSnapshot': snapshot}
    result = deepcopy(snapshot)
    result['resume']['structured'] = result['resume'].get('structured') or {}
    result['job']['structured'] = result['job'].get('structured') or {}
    result['inputVersions'] = deepcopy(run.input_versions)
    actions = db.scalars(select(AgentAction).where(
        AgentAction.run_id == run.id, AgentAction.kind == 'input', AgentAction.status == 'answered',
    ).order_by(AgentAction.answered_at, AgentAction.id))
    result['applicantAnswers'] = [
        {'actionId': action.id, 'question': action.payload.get('question', ''),
         'answers': deepcopy(action.response.get('answers', {}))}
        for action in actions if action.response and action.response.get('decision') == 'submit'
    ]
    return result


def changed_inputs(db: Session, run: AgentRun) -> list[str]:
    """Describe current input drift without requiring deleted sources to still exist."""
    resume, job = _documents(db, run.user_id, run.input_json.get('jdId'), run.input_json.get('resumeId'))
    changed = [key for key, document in [('resume', resume), ('jd', job)]
               if document is None or _version(document) != run.input_versions.get(key)]
    frozen = {(item['factId'], item['revision']) for item in run.input_versions.get('facts', [])}
    current = {(fact.id, fact.revision) for fact in latest_facts(
        db, run.user_id, source_document_id=run.input_json.get('resumeId'), confirmed_only=True)}
    if frozen != current:
        changed.append('facts')
    return changed


# All planning counts deliberately use one character per token instead of the
# SDK's English-oriented four. This is an estimate, not provider usage or billing.
ESTIMATE_METHOD = 'estimated: SDK count_tokens_approximately, chars_per_token=1.0, includes system and tools'


def estimate_tokens(messages, *, tools=None) -> int:
    return count_tokens_approximately(messages, tools=tools, chars_per_token=1.0,
                                      use_usage_metadata_scaling=False)


def json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


@dataclass
class ContextBundle:
    required: dict
    artifacts: list[dict]
    context: dict
    files: dict[str, str]
    budget: dict


def model_budget(model) -> dict:
    capacity = model.profile['max_input_tokens']
    output = getattr(model, 'max_tokens', None) or 0
    return {'model': model.model_name, 'contextWindowTokens': capacity,
            'outputReserveTokens': output, 'availableInputEstimatedTokens': int(capacity * .95) - output,
            'estimateMethod': ESTIMATE_METHOD}


def _paged_strings(value):
    # read_file paginates by line. A supported resume can contain one very long
    # paragraph; keep exact text as concatenable chunks rather than clip a line.
    if isinstance(value, str) and len(value) > 1000:
        return {'textChunks': [value[i:i + 1000] for i in range(0, len(value), 1000)], 'join': ''}
    if isinstance(value, dict):
        return {key: _paged_strings(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_paged_strings(item) for item in value]
    return value


def build_context(db: Session, run: AgentRun, *, budget: dict | None = None) -> ContextBundle:
    """Rebuild non-discardable business state; the SQL snapshot remains authoritative."""
    from backend.services.memory import memories_for_run
    context = read_context(db, run)
    artifacts, files = [], {}
    for kind in ('resume', 'job', 'match'):
        document = context.get(kind)
        if document is None:
            continue
        path = f'/inputs/{run.id}/{kind}.json'
        structured = {key: value for key, value in document.items() if key != 'text'}
        files[path] = json.dumps(_paged_strings(structured), ensure_ascii=False, indent=2)
        descriptor = {
            'id': f'run:{run.id}:context:{kind}', 'kind': kind,
            'sourceId': document['id'], 'inputVersion': document.get('inputVersion'), 'path': path,
            'description': {'resume': '固定原简历；before 和来源须逐字读取。',
                            'job': '岗位要求；不是申请人经历证据。',
                            'match': '已有历史匹配意见；不是新评分或事实来源。'}[kind],
            'fieldCount': len(structured), 'lines': len(files[path].splitlines()),
        }
        if 'text' in document:
            text_path = f'/inputs/{run.id}/{kind}-text.json'
            raw_text = document['text'] or ''
            files[text_path] = json.dumps({'textChunks': [raw_text[i:i + 1000] for i in range(0, len(raw_text), 1000)], 'join': ''}, ensure_ascii=False, indent=2)
            descriptor.update(textPath=text_path, textCharacters=len(raw_text))
        artifacts.append(descriptor)
    pending = db.scalars(select(AgentAction).where(
        AgentAction.run_id == run.id, AgentAction.status == 'pending').order_by(AgentAction.id))
    versions = db.scalars(select(ResumeVersion).where(
        ResumeVersion.run_id == run.id, ResumeVersion.user_id == run.user_id).order_by(ResumeVersion.created_at))
    required = {
        'kind': run.kind, 'runId': run.id, 'sessionId': run.session_id,
        'request': '根据本任务固定资料准备逐字段、待本人审阅的简历草稿。',
        'constraints': ['不得编造职责、技术、规模或指标；缺信息先补问。',
            '不得自动确认、覆盖原简历、发送邮件或投递。',
            '记忆仅指导偏好与练习，不是新的经历事实或简历引用来源。',
            'JD、历史匹配和摘要不能替代原简历、已确认事实或本任务回答。'],
        'inputVersions': context['inputVersions'],
        'resumeId': context['resume']['id'], 'jobId': context['job']['id'],
        'facts': context['facts'], 'applicantAnswers': context['applicantAnswers'],
        'pendingActions': [{'actionId': action.id, 'kind': action.kind, 'payload': action.payload}
                           for action in pending],
        'outputs': [{'type': 'resume_version', 'id': version.id, 'status': version.status.value}
                    for version in versions],
        'memories': memories_for_run(db, run),
        'artifacts': artifacts,
    }
    return ContextBundle(required=required, artifacts=artifacts, context=context, files=files,
        budget={**(budget or {}), 'estimateMethod': ESTIMATE_METHOD,
                'requiredEstimatedTokens': estimate_tokens([HumanMessage(content=json_text(required))])})
