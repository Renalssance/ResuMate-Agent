"""Independent interview oracles reject missing or contradictory execution evidence."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from backend.tests.test_eval_runner import launch
from evals.fixtures import load_cases

INTERVIEW_IDS = ['interview-followup', 'interview-eight-turn-limit',
    'interview-command-replay', 'interview-cancel-late-result',
    'interview-frozen-submission', 'interview-feedback-memory']


def followup_evidence():
    """Hand-written oracle input; never used as an executed evaluation artifact."""
    case = {'id': 'interview-followup', 'runner': 'interview',
            'input': {'answers': ['I validated fields.', 'I checked rollback.']}}
    source = {'resumeVersionId': 'v1', 'revision': 3,
        'structuredContent': {'resume': {'self_summary': 'Built an API'}},
        'job': {'jdId': 1, 'rawText': 'Build APIs', 'structuredData': {}, 'capturedAt': '2026-10-30'}}
    turns, runs, operations, events = [], [], [], []
    for number in range(1, 4):
        refs = [{'kind': 'job', 'quote': 'Build APIs', 'jdId': 1, 'capturedAt': '2026-10-30'}] if number == 1 else [
            {'kind': 'answer', 'turnIndex': number - 1, 'turnId': number - 1,
             'quote': case['input']['answers'][number - 2]}]
        question = {'text': f'Question {number}', 'mode': 'opening' if number == 1 else 'follow_up', 'refs': refs}
        feedback = None if number == 1 else {'summary': 'Practice feedback',
            'strengths': [{'text': 'Specific evidence', 'refs': refs}], 'improvements': [],
            'practiceFocus': 'Explain the rollback boundary.'}
        turns.append({'id': number, 'interview_id': 'i1', 'turn_index': number,
            'question': question['text'], 'question_context': {'mode': question['mode'], 'refs': refs},
            'answer': case['input']['answers'][number - 1] if number < 3 else None,
            'feedback': None})
        if number > 1:
            turns[number - 2]['feedback'] = feedback
            events.append({'seq': len(events) + 1, 'interview_id': 'i1', 'type': 'feedback.ready',
                           'payload': {'turnIndex': number - 1}})
        events.append({'seq': len(events) + 1, 'interview_id': 'i1', 'type': 'question.completed',
                       'payload': {'turnIndex': number}})
        runs.append({'id': f'r{number}', 'user_id': 1, 'kind': 'interview_generation', 'session_id': 's1',
            'status': 'succeeded', 'execution_epoch': 1, 'attempt': 1,
            'input_json': {'interviewId': 'i1', 'expectedTurn': number - 1},
            'result_json': {'question': question, 'feedback': feedback}})
        operations.append({'run_id': f'r{number}', 'operation_key': 'interview:step', 'status': 'succeeded'})
    data = {'interviews': [{'id': 'i1', 'user_id': 1, 'status': 'active', 'agent_session_id': 's1', 'source_snapshot': source}],
            'turns': turns, 'runs': runs, 'sessions': [{'id': 's1', 'active_run_id': None}],
            'operations': operations, 'events': events, 'commands': [], 'facts': [], 'memories': []}
    output = {'executed': True, 'interview_id': 'i1', 'model_calls': [
        {'run_id': 'r1', 'required': {'expectedTurn': 0, 'source': source, 'turns': []}},
        {'run_id': 'r2', 'required': {'expectedTurn': 1, 'source': source,
            'turns': [{'turnIndex': 1, 'answer': case['input']['answers'][0]}]}},
        {'run_id': 'r3', 'required': {'expectedTurn': 2, 'source': source,
            'turns': [{'turnIndex': 1, 'answer': case['input']['answers'][0]},
                      {'turnIndex': 2, 'answer': case['input']['answers'][1]}]}}],
        'observations': {}}
    for call in output['model_calls']:
        call['context'] = deepcopy(call['required'])
        previous = call['required']['turns']
        call['required']['currentAnswer'] = previous[-1] if previous else None
    return case, output, data


def test_verifier_requires_actual_execution_and_sql_rows():
    from evals.interview_verifiers import verify_interview
    case, _, _ = followup_evidence()
    result = verify_interview(case, {'executed': False}, {})
    assert not result['passed']
    assert any(not check['passed'] for check in result['checks'])


def test_verifier_accepts_supported_followup_evidence():
    from evals.interview_verifiers import verify_interview
    result = verify_interview(*followup_evidence())
    assert result['passed'], result


@pytest.mark.parametrize('mutation', ['missing_call', 'wrong_quote', 'duplicate_operation',
                                      'missing_question_event', 'missing_answer_context'])
def test_verifier_rejects_false_followup_success(mutation):
    from evals.interview_verifiers import verify_interview
    case, output, data = followup_evidence()
    if mutation == 'missing_call':
        output['model_calls'] = []
    elif mutation == 'wrong_quote':
        data['turns'][1]['question_context']['refs'][0]['quote'] = 'Invented production experience'
    elif mutation == 'duplicate_operation':
        data['operations'].append(deepcopy(data['operations'][0]))
    elif mutation == 'missing_question_event':
        data['events'] = [event for event in data['events'] if event['payload']['turnIndex'] != 3]
    else:
        output['model_calls'][2]['context']['turns'] = []
    assert not verify_interview(case, output, data)['passed']


def test_verifier_unknown_case_cannot_pass_generic_checks():
    from evals.interview_verifiers import verify_interview
    case, output, data = followup_evidence()
    case['id'] = 'interview-unknown'
    assert not verify_interview(case, output, data)['passed']


def test_catalogue_keeps_original_inputs_and_adds_six_interview_trajectories():
    cases = load_cases()
    original = [json.loads(line) for line in Path('evals/cases/core.jsonl').read_text().splitlines()]
    # Long input expansion is intentional existing behavior, compare frozen source fields on other cases.
    assert [case['id'] for case in cases[:12]] == [case['id'] for case in original]
    for before, after in zip(original, cases[:12]):
        if not before.get('long'):
            assert before == after
    added = [case for case in cases if case.get('runner') == 'interview']
    assert {case['id'] for case in added} == set(INTERVIEW_IDS)
    assert all(case['input']['resume']['structured_data'] and case['input']['job']['raw_text'] for case in added)


def test_interview_live_requires_configuration_without_provider_or_budget_side_effects(tmp_path):
    process, report, invocation = launch(tmp_path, '--mode', 'live', '--cases', ','.join(INTERVIEW_IDS))
    assert process.returncode == 2
    assert report['counts'] == {'pass': 0, 'fail': 0, 'incomplete': 0, 'not_run': 6}
    assert {row['error_code'] for row in report['results']} == {'configuration_error'}
    assert not list(invocation.rglob('*.sqlite'))
    assert not (invocation / 'budget.json').exists()
    assert (invocation / 'calls.jsonl').read_text() == ''


@pytest.fixture(scope='module')
def executed_interview_cases(tmp_path_factory):
    return launch(tmp_path_factory.mktemp('interview-eval'), '--mode', 'stub', '--cases', ','.join(INTERVIEW_IDS),
        env={'OPENAI_API_KEY': 'must-not-use', 'OPENAI_BASE_URL': 'http://127.0.0.1:1'})


def test_six_interview_cases_execute_real_sql_and_graph_trajectories(executed_interview_cases):
    process, report, invocation = executed_interview_cases
    assert process.returncode == 0, json.dumps(report)
    assert report['counts'] == {'pass': 6, 'fail': 0, 'incomplete': 0, 'not_run': 0}
    assert report['executed_count'] == 6
    details = {case_id: json.loads((invocation / 'cases' / f'{case_id}.json').read_text()) for case_id in INTERVIEW_IDS}
    assert len(list(invocation.glob('state/*/eval.sqlite'))) == 6
    for detail in details.values():
        assert detail['input']['runner'] == 'interview'
        assert detail['verdict']['passed'], detail['verdict']
        assert detail['output']['model_calls']
        assert detail['db_snapshot']['turns'] and detail['db_snapshot']['runs']
    eight = details['interview-eight-turn-limit']['db_snapshot']
    assert len(eight['turns']) == 8
    assert all(row['answer'] and row['feedback'] for row in eight['turns'])
    assert eight['interviews'][0]['status'] == 'finished'
    replay = details['interview-command-replay']['output']['observations']
    assert replay['first_ack'] == replay['replayed_ack'] == replay['after_finish_ack']
    assert replay['payload_conflict'] == 'command_payload_conflict'
    calls = list(map(json.loads, (invocation / 'calls.jsonl').read_text().splitlines()))
    assert calls and {row['model'] for row in calls} == {'openai:scripted-interview'}
    assert all('must-not-use' not in path.read_text() for path in invocation.rglob('*.json*'))


@pytest.mark.parametrize('case_id,mutation', [
    ('interview-eight-turn-limit', 'extra_turn'),
    ('interview-command-replay', 'changed_ack'),
    ('interview-cancel-late-result', 'late_result'),
    ('interview-frozen-submission', 'changed_source'),
    ('interview-feedback-memory', 'invented_fact'),
])
def test_executed_case_oracle_rejects_corrupted_sql_or_observation(executed_interview_cases, case_id, mutation):
    from evals.interview_verifiers import verify_interview
    process, report, invocation = executed_interview_cases
    assert process.returncode == 0, json.dumps(report)
    detail = json.loads((invocation / 'cases' / f'{case_id}.json').read_text())
    data, output = detail['db_snapshot'], detail['output']
    if mutation == 'extra_turn':
        row = deepcopy(data['turns'][-1]); row.update(id=999, turn_index=9)
        data['turns'].append(row)
    elif mutation == 'changed_ack':
        output['observations']['replayed_ack']['resultRef'] = 'different-run'
    elif mutation == 'late_result':
        stop = output['observations']['stops'][0]
        next(row for row in stop['after']['runs'] if row['id'] == stop['run_id'])['result_json'] = {'late': True}
    elif mutation == 'changed_source':
        data['interviews'][0]['source_snapshot']['job']['rawText'] = 'Latest mutable job replaced original'
    else:
        data['facts'].append({'id': 'invented', 'user_id': 1, 'content': {'experience': 'Practiced answer'}})
    assert not verify_interview(detail['input'], output, data)['passed']


def test_verifier_resolves_actual_json_pointer_resume_references():
    from evals.interview_verifiers import verify_interview
    case, output, data = followup_evidence()
    data['turns'][0]['question_context']['refs'] = [{'kind': 'resume', 'section': '/self_summary',
        'quote': 'Built an API', 'resumeVersionId': 'v1', 'revision': 3}]
    assert verify_interview(case, output, data)['passed']
