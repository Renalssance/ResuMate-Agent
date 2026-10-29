"""Synthetic case facts and model tool arguments must match their own business input."""
from collections import Counter
from langchain_core.messages import SystemMessage, ToolMessage
from evals.fixtures import load_cases, make_model


def test_core_categories_and_frontend_facts_are_distinct():
    cases = load_cases()
    assert len(cases) == 12
    assert Counter(case['category'] for case in cases) == {
        'normal': 3, 'clarification': 2, 'refusal_cancel': 2, 'tool_failure': 2,
        'duplicate': 1, 'source_conflict': 1, 'long_context': 1}
    frontend = next(c for c in cases if c['id'] == 'normal-project')
    assert 'React' in frontend['resume']['raw_text']
    assert '数据库' not in frontend['proposal']['after']
    assert 'API' not in frontend['proposal']['after']
    long = next(c for c in cases if c['id'] == 'long-context')
    assert len(long['resume']['structured_data']['projects']) == 60
    assert len({p['name'] for p in long['resume']['structured_data']['projects']}) == 60
    assert '测试环境' in long['facts'][0]['content']['text']
    assert '中文简短' in long['memories'][0]['content']


def test_stub_uses_exact_context_before_and_current_answer_identity():
    case = next(c for c in load_cases() if c['id'] == 'ask-technology')
    model = make_model(case, {})
    context = {'resume': {'id': 7, 'inputVersion': 'actual-frozen-version',
        'structured': case['resume']['structured_data']}, 'facts': [],
        'applicantAnswers': [{'actionId': 'persisted-action-9', 'answers': case['answer']}]}
    change = model.draft_changes(context)[0]
    assert change['before'] == context['resume']['structured']['self_summary']
    assert change['fact_refs'][0]['inputVersion'] == 'actual-frozen-version'
    assert change['fact_refs'][-1] == {'kind': 'applicant_answer', 'actionId': 'persisted-action-9'}
    assert '生产' not in change['after']


def test_summary_response_does_not_count_as_main_step():
    case = next(c for c in load_cases() if c['id'] == 'long-context')
    model = make_model(case, {})
    model.invoke([SystemMessage(content='必保留业务上下文（摘要调用）\n{}')])
    assert model.summary_calls == 1
    assert model.main_calls == model.step == 0


def test_long_fixture_reads_exact_before_and_marks_from_paged_file():
    case = next(c for c in load_cases() if c['id'] == 'long-context')
    model = make_model(case, {})
    model.tool_paths['actual-read'] = '/inputs/run-1/resume.json'
    model._collect_tool_results([ToolMessage(name='read_file', tool_call_id='actual-read', content='''1  {
2    "id": 1,
3    "structured": {
4      "self_summary": "逐字原文。",
5      "source_refs": [
6        "page:actual"
7      ],
8      "projects": [''')])
    assert model.saved_summary == '逐字原文。'
    assert model.saved_source_refs == ['page:actual']
    assert model.read_paths == ['/inputs/run-1/resume.json']
