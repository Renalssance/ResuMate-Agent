"""Source-bound suggestions and reviewed versions; never overwrite the main resume."""
from copy import deepcopy
from datetime import timezone
import re
from uuid import uuid4

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.agent_models import AgentAction, AgentRun, ToolOperation
from backend.db.career_models import ProfileFact, ResumeVersion
from backend.schemas.resume_versions import ResumeChange, ResumeVersionConfirm, ResumeVersionUpdate, VersionStatus
from backend.services.agent_runs import RunError
from backend.services.profile_facts import latest_statement
from backend.services.run_events import append_event

EDITABLE_SECTION = re.compile(r'^/(self_summary|summary|work_experience/(0|[1-9][0-9]*)/description|projects/(0|[1-9][0-9]*)/description)$')


def _section(structured: dict, path: str) -> tuple[object, list]:
    """Resolve a real field and its nearest containing source_refs, without JSON Patch."""
    if not path.startswith('/'):
        raise RunError(422, 'invalid_source', '来源字段不存在')
    value, refs = structured, []
    for token in path[1:].split('/'):
        if isinstance(value, dict):
            refs = value.get('source_refs', refs)
            if token not in value:
                raise RunError(422, 'invalid_source', '来源字段不存在')
            value = value[token]
        elif isinstance(value, list) and token.isdigit() and int(token) < len(value):
            value = value[int(token)]
        else:
            raise RunError(422, 'invalid_source', '来源字段不存在')
    if isinstance(value, dict):
        refs = value.get('source_refs', refs)
    return value, refs


def _validate_source(db: Session, run: AgentRun, context: dict, reference: dict) -> None:
    kind = reference['kind']
    if kind == 'profile_fact':
        frozen = {fact['id']: fact['revision'] for fact in context['facts']}
        fact = db.get(ProfileFact, reference['factId'])
        if (frozen.get(reference['factId']) != reference['revision'] or fact is None
                or fact.user_id != run.user_id or fact.confirmed_at is None
                or fact.deleted_at is not None
                or fact.source_document_id not in (None, run.input_json['resumeId'])):
            raise RunError(422, 'invalid_fact', '引用必须来自该任务固定的已确认事实')
        latest = db.scalar(latest_statement(run.user_id).where(ProfileFact.fact_key == fact.fact_key))
        if latest is None or latest.deleted_at is not None:
            raise RunError(422, 'invalid_fact', '引用事实已删除')
    elif kind == 'resume':
        resume = context['resume']
        if reference['resumeId'] != resume['id'] or reference['inputVersion'] != resume['inputVersion']:
            raise RunError(422, 'invalid_source', '来源必须是该任务固定的简历版本')
        _, refs = _section(resume['structured'] or {}, reference['section'])
        if reference['sourceRefs'] != refs:
            raise RunError(422, 'invalid_source', '来源标记与原简历不一致')
    elif kind == 'applicant_answer':
        if reference['actionId'] not in {answer['actionId'] for answer in context['applicantAnswers']}:
            raise RunError(422, 'invalid_source', '来源必须是该任务已提交的补充回答')


def create_draft(db: Session, run: AgentRun, changes: list) -> str:
    """Write artifact, operation and event together; the owning caller commits once."""
    key = f"draft:{run.input_json['jdId']}:initial"
    existing = db.scalar(select(ToolOperation).where(
        ToolOperation.run_id == run.id, ToolOperation.operation_key == key))
    if existing and existing.status == 'succeeded':
        return existing.result_ref
    from backend.agent_runtime.context import read_context
    context = read_context(db, run)
    try:
        proposals = TypeAdapter(list[ResumeChange]).validate_python(changes)
    except ValidationError as error:
        raise RunError(422, 'invalid_proposal', '字段建议格式错误，请检查正文、来源和待补充状态') from error
    base = context['resume']['structured'] or {}
    seen, saved, references = set(), [], []
    for proposal in proposals:
        change = proposal.model_dump(by_alias=True)
        path = change['section']
        if not EDITABLE_SECTION.fullmatch(path) or path in seen:
            raise RunError(422, 'invalid_proposal', '仅支持已有简介、经历或项目描述，每个字段只能有一条建议')
        before, _ = _section(base, path)
        if change['before'] != before:
            raise RunError(422, 'invalid_proposal', '建议的原文与任务固定简历不一致')
        seen.add(path)
        for reference in change['fact_refs']:
            _validate_source(db, run, context, reference)
            if reference not in references:
                references.append(reference)
        saved.append({**change, 'id': str(uuid4()), 'status': 'pending'})
    version_id = str(uuid4())
    db.add(ResumeVersion(id=version_id, user_id=run.user_id, run_id=run.id,
                         resume_id=run.input_json['resumeId'], jd_id=run.input_json['jdId'],
                         structured_content={'resume': deepcopy(base), 'changes': saved,
                                             'inputVersions': deepcopy(run.input_versions)},
                         fact_refs=references))
    db.add(ToolOperation(run_id=run.id, operation_key=key,
                         tool_name='create_resume_draft', status='succeeded', result_ref=version_id))
    append_event(db, run.id, 'artifact.created', {'artifact_id': version_id, 'kind': 'resume_version'})
    return version_id


def serialize_version(db: Session, user_id: int, version: ResumeVersion, *, input_changes: list[str] | None = None) -> dict:
    if version.user_id != user_id:
        raise RunError(404, 'not_found', '简历版本不存在')
    result = {'id': version.id, 'runId': version.run_id, 'resumeId': version.resume_id,
              'jdId': version.jd_id, 'revision': version.revision, 'status': version.status,
              'structuredContent': version.structured_content, 'factRefs': version.fact_refs,
              'createdAt': version.created_at.replace(tzinfo=timezone.utc).isoformat(),
              'basedOnOldInput': False, 'changedInputs': [], 'sources': [], 'reviewable': False}
    run = db.get(AgentRun, version.run_id) if version.run_id else None
    result['reviewable'] = _reviewable(version, run)
    if run is None:
        return result
    from backend.agent_runtime.context import changed_inputs
    result['changedInputs'] = changed_inputs(db, run) if input_changes is None else input_changes
    result['basedOnOldInput'] = bool(result['changedInputs'])
    # Legacy Runs still know their input versions, but cannot reconstruct source text.
    if 'inputVersions' not in version.structured_content:
        return result
    context = run.input_json.get('contextSnapshot', {})
    facts = {fact['id']: fact for fact in context.get('facts', [])}
    answers = {}
    if any(ref['kind'] == 'applicant_answer' for ref in version.fact_refs):
        answers = {action.id: action for action in db.scalars(select(AgentAction).where(
            AgentAction.run_id == run.id, AgentAction.kind == 'input', AgentAction.status == 'answered'))}
    for reference in version.fact_refs:
        kind = reference['kind']
        if kind == 'resume':
            content, _ = _section(context['resume']['structured'] or {}, reference['section'])
            label = '简历 · ' + reference['section']
        elif kind == 'profile_fact':
            content = facts[reference['factId']]['content']
            label = f"已确认事实 · 第 {reference['revision']} 版"
        else:
            action = answers[reference['actionId']]
            content = {'question': action.payload.get('question', ''), 'answers': action.response['answers']}
            label = '本次补充回答'
        result['sources'].append({'reference': reference, 'label': label, 'content': deepcopy(content)})
    return result


def _owned_version(db: Session, user_id: int, version_id: str) -> ResumeVersion:
    version = db.scalar(select(ResumeVersion).where(ResumeVersion.id == version_id, ResumeVersion.user_id == user_id))
    if version is None:
        raise RunError(404, 'not_found', '简历版本不存在')
    return version


def get_version(db: Session, user_id: int, version_id: str) -> dict:
    return serialize_version(db, user_id, _owned_version(db, user_id, version_id))


def _reviewable(version: ResumeVersion, run: AgentRun | None) -> bool:
    return bool(run is not None and 'contextSnapshot' in run.input_json
                and {'resume', 'changes', 'inputVersions'} <= version.structured_content.keys())


def _review_base(db: Session, version: ResumeVersion) -> dict:
    run = db.get(AgentRun, version.run_id) if version.run_id else None
    if not _reviewable(version, run):
        raise RunError(409, 'legacy_read_only', '此历史草稿仅可查看，请重新准备材料以生成可逐条审阅的建议')
    # Review owns this snapshot even after the original document changes or is deleted.
    return deepcopy(run.input_json['contextSnapshot']['resume']['structured'] or {})


def _check_revision(version: ResumeVersion, expected_revision: int) -> None:
    if version.revision != expected_revision:
        raise RunError(409, 'revision_conflict', '版本已被更新，请查看服务器最新版本后再保存')


def _write_review(db: Session, user_id: int, version_id: str, expected_revision: int, **values) -> dict:
    # A prior SELECT or FOR UPDATE alone cannot protect SQLite readers from lost updates.
    result = db.execute(update(ResumeVersion).where(
        ResumeVersion.id == version_id, ResumeVersion.user_id == user_id,
        ResumeVersion.status == VersionStatus.DRAFT, ResumeVersion.revision == expected_revision,
    ).values(**values, revision=expected_revision + 1).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        raise RunError(409, 'revision_conflict', '版本已被更新，请查看服务器最新版本后再保存')
    db.commit()
    db.expire_all()
    return get_version(db, user_id, version_id)


def update_version(db: Session, user_id: int, version_id: str, request: ResumeVersionUpdate) -> dict:
    version = _owned_version(db, user_id, version_id)
    _check_revision(version, request.expected_revision)
    if version.status == VersionStatus.CONFIRMED:
        raise RunError(409, 'version_confirmed', '已确认版本不可修改')
    base = _review_base(db, version)
    content = deepcopy(version.structured_content)
    originals = content['changes']
    decisions = {decision.id: decision for decision in request.changes}
    if len(decisions) != len(request.changes) or set(decisions) != {change['id'] for change in originals}:
        raise RunError(422, 'invalid_decisions', '必须对每条建议提交且仅提交一次决定')
    for change in originals:
        decision = decisions[change['id']]
        if decision.status == 'accepted' and change['requires_input']:
            raise RunError(422, 'invalid_decisions', '待补充信息不能直接接受，请本人编辑或拒绝')
        change['status'] = decision.status
        change.pop('editedText', None)
        if decision.status == 'edited':
            change['editedText'] = decision.edited_text
        if decision.status in ('accepted', 'edited'):
            parent_path, field = change['section'].rsplit('/', 1)
            parent = _section(base, parent_path)[0] if parent_path else base
            parent[field] = change['after'] if decision.status == 'accepted' else decision.edited_text
    content['resume'] = base
    return _write_review(db, user_id, version_id, request.expected_revision, structured_content=content)


def confirm_version(db: Session, user_id: int, version_id: str, request: ResumeVersionConfirm) -> dict:
    version = _owned_version(db, user_id, version_id)
    _check_revision(version, request.expected_revision)
    _review_base(db, version)
    if version.status == VersionStatus.CONFIRMED:
        return serialize_version(db, user_id, version)
    if any(change['status'] == 'pending' or
           (change['status'] == 'accepted' and change['requires_input'])
           for change in version.structured_content['changes']):
        raise RunError(422, 'review_incomplete', '请先审阅并保存全部建议后再确认')
    return _write_review(db, user_id, version_id, request.expected_revision, status=VersionStatus.CONFIRMED)
