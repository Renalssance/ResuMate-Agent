"""Frozen interview material, accepted SQL answers and source-bound model output."""
from copy import deepcopy
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from backend.services.agent_runs import RunError
from backend.services.resume_versions import _section


class OutputModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class ResumeRef(OutputModel):
    kind: Literal['resume']
    section: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class JobRef(OutputModel):
    kind: Literal['job']
    quote: str = Field(min_length=1)


class AnswerRef(OutputModel):
    kind: Literal['answer']
    turnIndex: int = Field(ge=1, le=8)
    quote: str = Field(min_length=1)


InterviewRef = Annotated[ResumeRef | JobRef | AnswerRef, Field(discriminator='kind')]


class InterviewQuestion(OutputModel):
    text: str = Field(min_length=1, max_length=2000)
    mode: Literal['opening', 'follow_up', 'new_topic']
    refs: list[InterviewRef] = Field(min_length=1, max_length=12)


class FeedbackPoint(OutputModel):
    text: str = Field(min_length=1, max_length=2000)
    refs: list[InterviewRef] = Field(min_length=1, max_length=12)


class InterviewFeedback(OutputModel):
    summary: str = Field(min_length=1, max_length=2000)
    strengths: list[FeedbackPoint] = Field(max_length=5)
    improvements: list[FeedbackPoint] = Field(max_length=5)
    practiceFocus: str = Field(min_length=1, max_length=4000)

    @model_validator(mode='after')
    def has_evidence(self):
        if not self.strengths and not self.improvements:
            raise ValueError('Practice feedback must contain a referenced assessment')
        return self


class InterviewStep(OutputModel):
    feedback: InterviewFeedback | None
    question: InterviewQuestion | None


def _contains_quote(value, quote: str) -> bool:
    if isinstance(value, str):
        return quote in value
    if isinstance(value, dict):
        return any(_contains_quote(item, quote) for item in value.values())
    if isinstance(value, list):
        return any(_contains_quote(item, quote) for item in value)
    return False


def _bind_ref(reference: dict, context: dict) -> dict:
    source = context['source']
    kind, quote = reference['kind'], reference['quote']
    valid, identifiers = False, {}
    if kind == 'resume':
        content, _refs = _section(source['structuredContent']['resume'], reference['section'])
        valid = _contains_quote(content, quote)
        identifiers = {'resumeVersionId': source['resumeVersionId'], 'revision': source['revision']}
    elif kind == 'job':
        job = source['job']
        valid = _contains_quote([job['title'], job['company'], job['rawText'], job['structuredData']], quote)
        identifiers = {'jdId': job['jdId'], 'capturedAt': job['capturedAt']}
    elif kind == 'answer':
        turn = next((turn for turn in context['turns'] if turn['turnIndex'] == reference['turnIndex']), None)
        valid = turn is not None and turn['answer'] is not None and quote in turn['answer']
        if valid:
            identifiers = {'turnId': turn['id']}
    if not valid:
        raise RunError(422, 'invalid_interview_reference', '练习引用不在冻结材料或已接受回答中')
    return {**reference, **identifiers}


def validate_step(output, context: dict) -> dict:
    """Reject unsupported results as a whole; only SQL may supply identity fields."""
    try:
        step = InterviewStep.model_validate(output).model_dump()
    except ValidationError as error:
        raise RunError(422, 'invalid_interview_output', '面试生成结果格式不正确') from error
    expected = context['expectedTurn']
    question, feedback = step['question'], step['feedback']
    if (expected == 0 and feedback is not None) or (expected > 0 and feedback is None):
        raise RunError(422, 'invalid_interview_output', '练习反馈与已接受回答的轮次不一致')
    if (expected == 8 and question is not None) or (expected < 8 and question is None):
        raise RunError(422, 'invalid_interview_output', '面试最多八题，当前生成问题数量不正确')
    if question is not None:
        if (expected == 0) != (question['mode'] == 'opening'):
            raise RunError(422, 'invalid_interview_output', '面试问题类型与当前轮次不一致')
        if question['mode'] == 'follow_up' and not any(
                ref['kind'] == 'answer' and ref['turnIndex'] == expected for ref in question['refs']):
            raise RunError(422, 'invalid_interview_reference', '追问必须引用上一条已接受回答')
        question['refs'] = [_bind_ref(ref, context) for ref in question['refs']]
    if feedback is not None:
        for point in [*feedback['strengths'], *feedback['improvements']]:
            point['refs'] = [_bind_ref(ref, context) for ref in point['refs']]
    return deepcopy(step)

from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from backend.agent_runtime.context import ContextBundle, _paged_strings, estimate_tokens, json_text
from backend.agent_runtime.context_middleware import BusinessContextMiddleware
from backend.db.database import SessionLocal
from backend.services.interviews import guard_interview_execution
from backend.services.memory import memories_for_run
import json


def read_context(db, run, interview, turns):
    return {'interviewId': interview.id, 'expectedTurn': run.input_json['expectedTurn'],
        'source': deepcopy(interview.source_snapshot),
        'turns': [{'id': row.id, 'turnIndex': row.turn_index, 'question': row.question,
                   'questionContext': deepcopy(row.question_context), 'answer': row.answer,
                   'feedback': deepcopy(row.feedback)} for row in turns],
        'memories': memories_for_run(db, run)}


def context_bundle(run_id: str, epoch: int, *, budget=None):
    with SessionLocal() as db:
        run, interview, turns = guard_interview_execution(db, run_id, epoch)
        context = read_context(db, run, interview, turns)
        source = context['source']
        artifacts, files = [], {}
        for kind in ('source', 'turns'):
            path = f'/inputs/{run.id}/{kind}.json'
            files[path] = json.dumps(_paged_strings(context[kind]), ensure_ascii=False, indent=2)
            artifacts.append({'kind': kind, 'path': path, 'lines': len(files[path].splitlines())})
        required = {'kind': run.kind, 'runId': run.id, 'sessionId': run.session_id,
            'interviewId': interview.id, 'expectedTurn': context['expectedTurn'], 'maxQuestions': 8,
            'sourceIdentity': {key: source[key] for key in ('applicationId', 'resumeVersionId', 'revision', 'submittedAt')},
            'jobIdentity': {key: source['job'][key] for key in ('jdId', 'capturedAt')},
            'currentAnswer': None if not turns else {'turnId': turns[-1].id, 'turnIndex': turns[-1].turn_index,
                'question': turns[-1].question, 'answer': turns[-1].answer},
            'constraints': ['只使用冻结投递材料和开始练习时的岗位；岗位不是经历证据。',
                '这是模拟练习；回答和反馈不能成为候选人经历事实。',
                'expectedTurn=0 只给首题；1..7 给该轮反馈和下一题；8 只给反馈。',
                '追问必须引用上一条已接受回答；所有引用逐字存在于对应材料。',
                '记忆只指导练习偏好，不能作为简历事实或引用来源。'],
            'memories': context['memories'], 'artifacts': artifacts}
        db.commit()  # No model, summary, file/checkpoint I/O while SQL write gates are held.
    return ContextBundle(required=required, artifacts=artifacts, context=context, files=files,
                         budget=budget or {})


class InterviewContextMiddleware(BusinessContextMiddleware):
    def _bundle(self):
        return context_bundle(self.run_id, self.epoch, budget=self.budget)


def interview_tools(run_id, epoch, *, inline_token_limit, budget):
    @tool
    def get_interview_context(runtime: ToolRuntime) -> dict:
        """Read frozen submitted resume/job, accepted interview answers and confirmed practice memories."""
        from deepagents.backends import StateBackend
        bundle = context_bundle(run_id, epoch, budget=budget)
        if estimate_tokens([HumanMessage(content=json_text(bundle.context))]) <= inline_token_limit:
            return bundle.context
        backend = StateBackend()
        for path, content in bundle.files.items():
            backend.write(path, content)
        return {'format': 'artifact_manifest', 'required': bundle.required, 'artifacts': bundle.artifacts,
                'budget': bundle.budget,
                'readInstructions': '用 read_file(file_path,offset,limit) 分页读取冻结原文；textChunks 按顺序以空字符串拼接。引用不得使用摘要代替原文。'}
    return [get_interview_context]
