"""Browser-only external model/embedding replacements; SQL, worker and Chroma are real."""
import json
import os
import time
from collections import defaultdict
from contextvars import ContextVar
from pathlib import Path

import httpx
from openai import OpenAI
from backend.agents import harness
from backend.rag import chroma

_context = ContextVar('browser_schema_context')
_calls = defaultdict(int)
_original_run_schema = harness.AgentHarness.run_schema


def browser_run_schema(self, **kwargs):
    token = _context.set(kwargs)
    try:
        return _original_run_schema(self, **kwargs)
    finally:
        _context.reset(token)


def question(item, index):
    return dict(question=f'请结合实际经历说明第{index}项接口设计决定及验证过程。',
                question_type=item['question_type'], difficulty='medium', assessment_points=['具体职责与验证依据'],
                related_criteria=[item['primary_criterion_id']], evidence_chunk_ids=item.get('evidence_chunk_ids', []),
                reference_answer_direction='说明当时的输入、本人负责的部分和核对结果。',
                scoring_rubric=['使用真实经历', '区分事实和待确认信息'], suggested_followups=['哪些结论还需要进一步核对？'])


def content_for(context):
    task, variables = context['task'], context['variables']
    if task == 'document.parse_jd':
        return dict(job_title='API 工程师', summary='负责 API 与数据库设计。', responsibilities=['实现接口与数据模型'],
                    criteria=[dict(criterion_id='api', name='API 设计', description='具备接口开发经历',
                                   importance='must', weight=100, evidence_query='API 数据库 设计')], interview_focus=['接口设计'])
    if task == 'document.parse_resume':
        chunks = variables['chunks_json']
        first = chunks[0]
        refs = [dict(chunk_id=first['chunk_id'], page_number=first['page_number'], section=first['section'], text=first['text'])]
        return dict(candidate_name='示例求职者', self_summary='负责 API 和数据库设计。', source_refs=refs,
                    work_experience=[dict(company='示例团队', title='API 开发', description=first['text'], source_refs=refs)])
    if task == 'evaluate_match':
        return {'evaluations': [dict(criterion_id=criterion['criterion_id'], name=criterion['name'], weight=criterion['weight'],
                    score=3 if variables['evidence_json'].get(criterion['criterion_id']) else 0,
                    status='partial_match' if variables['evidence_json'].get(criterion['criterion_id']) else 'no_evidence',
                    reason='依据已保存的简历片段核对，具体规模仍需确认。',
                    evidence_chunk_ids=[item['chunk_id'] for item in variables['evidence_json'].get(criterion['criterion_id'], [])][:2],
                    missing_evidence=['尚未提供可核对的效果指标']) for criterion in variables['criteria_json']]}
    if task == 'plan_question_blueprint':
        from backend.services.analysis import QUESTION_TYPE_SEQUENCE
        report = json.loads(variables['report_json'])
        criterion = report['job_profile']['criteria'][0]['criterion_id']
        evidence = [ref for item in report['evaluations'] for ref in item['evidence_chunk_ids']]
        return {'formal_questions': [dict(question_id=f'q{i + 1}', question_type=kind, primary_criterion_id=criterion,
                    objective='核对职责与证据', difficulty='medium', evidence_chunk_ids=[] if kind == 'gap_validation' else evidence[:1])
                for i, kind in enumerate(QUESTION_TYPE_SEQUENCE[:variables['question_count']])]}
    if task == 'generate_question_batch':
        blueprint = json.loads(variables['blueprint_json'])
        return {'formal_questions': [question(item, item['question_id'][1:]) for item in blueprint['formal_questions']]}
    if task == 'generate_ambiguity_followups':
        report = json.loads(variables['report_json'])
        item = dict(question_type='gap_validation', primary_criterion_id=report['job_profile']['criteria'][0]['criterion_id'])
        return {'ambiguity_followups': [question(item, f'补充{i + 1}') for i in range(3)]}
    if task == 'followup.analyze_answer':
        return dict(follow_up='当时如何确认接口已经恢复，哪些观察支持这个判断？', reason='回答给出了处理步骤，还需要核对验证依据。',
                    evidence=['描述了日志排查和接口验证'], risks=['没有提供可复核的时延测量记录'],
                    current_ability='能够说明本人负责的接口排查步骤。', next_suggestion='补充当时观察到的日志和验证方法，避免猜测效果。')
    raise AssertionError(f'Unexpected browser model task: {task}')


def model_response(request):
    context = _context.get()
    state = Path(os.environ['RESUMATE_E2E_ROOT'])
    (state / 'legacy-model-started').write_text(context['task'])
    pause = state / 'legacy-pause'
    deadline = time.monotonic() + 60
    while pause.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    payload = json.loads(request.content)
    prompt = payload['messages'][1]['content']
    _calls[prompt] += 1
    if 'E2E_ALWAYS_FAIL' in prompt or ('E2E_RETRY_PARSE' in prompt and _calls[prompt] <= 3):
        return httpx.Response(503, json={'error': {'message': 'Synthetic model temporarily unavailable', 'type': 'server_error'}})
    content = content_for(context)
    return httpx.Response(200, json={'id': 'browser-long-task', 'object': 'chat.completion', 'created': 1,
        'model': payload['model'], 'choices': [{'index': 0, 'finish_reason': 'stop',
        'message': {'role': 'assistant', 'content': json.dumps(content, ensure_ascii=False)}}],
        'usage': {'prompt_tokens': 25, 'completion_tokens': 30, 'total_tokens': 55}})


class BrowserEmbedding:
    contract = {'provider': 'browser-fixture', 'model': 'deterministic-eight-dimensions'}
    def embed(self, text):
        return [float(text.casefold().count(word) + 1) for word in ('api', '数据库', '接口', '设计', '团队', '验证', '项目', '职责')]
    def embed_many(self, texts):
        return [self.embed(text) for text in texts]


def fixture_client(**kwargs):
    return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(model_response)))


harness.AgentHarness.run_schema = browser_run_schema
harness.OpenAI = fixture_client
chroma.embedding_service = BrowserEmbedding()
