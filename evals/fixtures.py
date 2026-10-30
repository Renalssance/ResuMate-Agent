"""Synthetic eval input and SDK model fixtures. Importing this module never opens a DB."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import re

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


RESUME_BASELINE_FIELDS = ('id', 'user_id', 'raw_text', 'structured_data')
FACT_BASELINE_FIELDS = ('id', 'user_id', 'fact_key', 'kind', 'content', 'source_document_id', 'revision', 'confirmed_at', 'deleted_at')
MEMORY_BASELINE_FIELDS = ('id', 'user_id', 'kind', 'content', 'source_ref', 'confirmed_at', 'deleted_at')


def load_cases(suite='core'):
    if suite != 'core':
        raise ValueError('Only suite core is available')
    cases = [json.loads(line) for line in (Path(__file__).parent / 'cases' / 'core.jsonl').read_text().splitlines() if line.strip()]
    cases.extend(json.loads(line) for line in (Path(__file__).parent / 'cases' / 'recovery.jsonl').read_text().splitlines() if line.strip())
    cases.extend(json.loads(line) for line in (Path(__file__).parent / 'cases' / 'interviews.jsonl').read_text().splitlines() if line.strip())
    for case in cases:
        if case.get('long'):
            _long_input(case)
    return cases


def _long_input(case):
    subjects = ['订单字段校验', '库存状态查询', '报名信息提交', '发票字段检查', '任务状态展示', '课程信息维护']
    projects = []
    for i in range(60):
        subject = subjects[i % len(subjects)]
        detail = (f'项目 {i + 1} 的 {subject}：在测试环境使用 Python 实现请求字段检查、错误提示与测试用例；'
                  f'核对第 {i + 1} 组业务规则并记录异常输入，不涉及生产部署。')
        projects.append({'name': f'合成项目 {i + 1}：{subject}',
                         'description': detail * 6, 'source_refs': [f'project:{i + 1}']})
    case['resume']['structured_data']['projects'] = projects
    case['resume']['raw_text'] = '测试申请人甲。仅测试环境，不得声称线上规模。\n' + '\n'.join(p['description'] * 2 for p in projects)
    case['job']['raw_text'] = '\n'.join(
        f'岗位任务 {i + 1}：审查 {subjects[i % len(subjects)]} 的字段规则、错误路径和测试证据；说明环境和职责边界。' * 12
        for i in range(60))
    case['match_report'] = {'notes': [
        f'项目 {i + 1} 的已有匹配意见：突出 {subjects[i % len(subjects)]} 的实际校验与测试工作，保留测试环境限定，不补写规模或提升比例。' * 8
        for i in range(60)]}


def _baseline(row, columns):
    values = {}
    for key in columns:
        value = getattr(row, key)
        values[key] = value.isoformat() if isinstance(value, datetime) else deepcopy(value)
    return values


def seed_case(case):
    """Called only after the harness establishes a fresh DATABASE_URL and state directory."""
    from backend.db.database import Base, engine, SessionLocal
    from backend.db.models import User, Resume, JobDescription, AnalysisJob, AnalysisCandidate, MatchResult
    from backend.db.agent_models import AgentSession
    from backend.db.career_models import ProfileFact, BusinessMemory
    Base.metadata.create_all(engine)
    frozen_time = datetime(2026, 10, 1, 0, 0, 0)
    with SessionLocal() as db:
        db.add(User(id=1, username='synthetic-eval-applicant', password_hash='not-a-login'))
        db.flush()
        resume = Resume(id=1, user_id=1, filename='synthetic-resume.txt',
                        raw_text=case['resume']['raw_text'], structured_data=deepcopy(case['resume']['structured_data']),
                        updated_at=frozen_time)
        job = JobDescription(id=1, user_id=1, title=case['job']['title'],
                             raw_text=case['job']['raw_text'], updated_at=frozen_time)
        session = AgentSession(user_id=1, purpose='tailoring')
        db.add_all([resume, job, session])
        db.flush()
        facts = [ProfileFact(**deepcopy(item), user_id=1, source_document_id=1, confirmed_at=frozen_time)
                 for item in case['facts']]
        memories = [BusinessMemory(**deepcopy(item), user_id=1, source_ref={'kind': 'manual'}, confirmed_at=frozen_time)
                    for item in case['memories']]
        db.add_all([*facts, *memories])
        if case.get('match_report'):
            analysis = AnalysisJob(user_id=1, jd_id=1, title='合成历史匹配', status='completed')
            db.add(analysis)
            db.flush()
            candidate = AnalysisCandidate(job_id=analysis.id, resume_id=1)
            db.add(candidate)
            db.flush()
            db.add(MatchResult(job_id=analysis.id, resume_id=1, jd_id=1, candidate_id=candidate.id,
                               overall_score=82, recommendation='recommend', reason='已有测试环境接口经历',
                               report_json=deepcopy(case['match_report'])))
        db.commit()
        return {'user_id': 1, 'resume_id': 1, 'jd_id': 1, 'session_id': session.id, 'baseline': {
            'resume': _baseline(resume, RESUME_BASELINE_FIELDS),
            'facts': [_baseline(fact, FACT_BASELINE_FIELDS) for fact in facts],
            'memories': [_baseline(memory, MEMORY_BASELINE_FIELDS) for memory in memories]}}


def _field(document, section):
    value, refs = document, []
    for token in section[1:].split('/'):
        if isinstance(value, dict):
            refs = value.get('source_refs', refs)
            value = value[token]
        else:
            value = value[int(token)]
    return value, refs


class EvalModel(BaseChatModel):
    """Emits real SDK tool calls; only their arguments are deterministic."""
    model_name: str = 'resumate-eval-stub-v1'
    profile: dict = {'max_input_tokens': 64000}
    max_tokens: int = 1024
    case: dict
    step: int = 0
    main_calls: int = 0
    summary_calls: int = 0
    requests: list = Field(default_factory=list)
    summaries: list = Field(default_factory=list)
    read_paths: list = Field(default_factory=list)
    draft_results: list = Field(default_factory=list)
    seen_tool_calls: set = Field(default_factory=set)
    tool_paths: dict = Field(default_factory=dict)
    context: dict = Field(default_factory=dict)
    saved_summary: str | None = None
    saved_source_refs: list = Field(default_factory=list)
    bound_tools: list = Field(default_factory=list)

    @property
    def _llm_type(self):
        return 'resumate-eval-stub'

    def bind_tools(self, tools, **kwargs):
        self.bound_tools = tools
        return self

    def draft_changes(self, context):
        proposal, resume = self.case['proposal'], context['resume']
        section = proposal['section']
        before, _ = _field(resume['structured'], section)
        refs = []
        for source_section in [section, *proposal.get('source_sections', [])]:
            _, source_refs = _field(resume['structured'], source_section)
            refs.append({'kind': 'resume', 'resumeId': resume['id'], 'inputVersion': resume['inputVersion'],
                         'section': source_section, 'sourceRefs': source_refs})
        if proposal.get('include_fact'):
            fact = context['facts'][0]
            refs.append({'kind': 'profile_fact', 'factId': fact['id'], 'revision': fact['revision']})
        if proposal.get('include_answer'):
            refs.append({'kind': 'applicant_answer', 'actionId': context['applicantAnswers'][-1]['actionId']})
        return [{'section': section, 'before': before, 'after': proposal['after'], 'reason': proposal['reason'],
                 'fact_refs': refs, 'requires_input': False}]

    def _collect_tool_results(self, messages):
        for message in messages:
            if not isinstance(message, ToolMessage) or message.tool_call_id in self.seen_tool_calls:
                continue
            self.seen_tool_calls.add(message.tool_call_id)
            if message.name == 'get_application_context':
                payload = json.loads(message.content)
                if payload.get('format') != 'artifact_manifest':
                    self.context = payload
            elif message.name == 'read_file':
                self.read_paths.append(self.tool_paths[message.tool_call_id])
                if '"self_summary"' in message.content:
                    # A real paged file can be a partial JSON object. Read this exact scalar
                    # from its JSON string, not a value copied from the synthetic case.
                    match = re.search(r'"self_summary"\s*:\s*("(?:[^"\\]|\\.)*")', message.content)
                    if match:
                        self.saved_summary = json.loads(match.group(1))
                    plain = re.sub(r'^\s*\d+\s+', '', message.content, flags=re.M)
                    marks = re.search(r'\"source_refs\"\s*:\s*(\[[^]]*\])', plain)
                    if marks:
                        self.saved_source_refs = json.loads(marks.group(1))
            elif message.name == 'create_resume_draft':
                self.draft_results.append(json.loads(message.content)['versionId'])

    def _generate(self, messages, **kwargs):
        if messages[0].text.startswith('必保留业务上下文（摘要调用）'):
            self.summary_calls += 1
            self.summaries.append(deepcopy(messages))
            # Omitting business details proves their retention comes from SQL injection.
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content='已阅读资料，继续核查并准备待审阅草稿。'))])
        self.main_calls += 1
        self.requests.append(deepcopy(messages))
        self._collect_tool_results(messages)
        required = json.loads(messages[0].text.rsplit('必保留业务上下文\n', 1)[1])
        root = f"/inputs/{required['runId']}"
        commands = [('get_application_context', {})]
        if self.case.get('long'):
            commands.extend(('read_file', {'file_path': f'{root}/{name}.json', 'offset': 0, 'limit': limit})
                            for name, limit in [('resume', 50), ('resume-text', 45), ('job-text', 45), ('match', 45)])
        if self.case.get('question'):
            commands.extend([('ask_applicant', {'question': self.case['question']}), ('get_application_context', {})])
            if self.case.get('long'):
                commands.append(('read_file', {'file_path': root + '/resume.json', 'offset': 0, 'limit': 50}))
        save_count = 2 if self.case.get('repeat') else 1
        if self.step < len(commands):
            name, args = commands[self.step]
        elif self.step < len(commands) + save_count:
            context = self.context
            if self.case.get('long'):
                context = {'resume': {'id': required['resumeId'], 'inputVersion': required['inputVersions']['resume'],
                            'structured': {'self_summary': self.saved_summary, 'source_refs': self.saved_source_refs}},
                           'facts': required['facts'], 'applicantAnswers': required['applicantAnswers']}
            name, args = 'create_resume_draft', {'changes': self.draft_changes(context)}
        else:
            final = ('无法加入没有依据的管理和 Kubernetes 经历；已按真实职责生成草稿，请审阅。'
                     if self.case['id'] == 'refuse-fabrication' else '已生成有来源的字段建议，请逐项审阅后决定是否采纳。')
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=final))])
        self.step += 1
        call_id = f'eval-{self.step}'
        if name == 'read_file':
            self.tool_paths[call_id] = args['file_path']
        message = AIMessage(content=('正在核对固定原文、确认事实、岗位要求和可引用的经历。' * 100
                                     if self.case.get('long') else ''),
                            tool_calls=[{'name': name, 'args': args, 'id': call_id, 'type': 'tool_call'}])
        return ChatResult(generations=[ChatGeneration(message=message)])


def make_model(case, seed):
    return EvalModel(case=deepcopy(case), profile={'max_input_tokens': 30000 if case.get('long') else 64000})
