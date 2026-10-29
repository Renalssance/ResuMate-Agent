"""Fixed business input for tailoring; live answers remain scoped to their Run."""
from copy import deepcopy
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.agent_models import AgentAction, AgentRun
from backend.db.career_models import ProfileFact
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
