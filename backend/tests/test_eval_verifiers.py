"""Independent snapshot checks must reject corrupt outputs, even outside SQL constraints."""
from copy import deepcopy

import pytest

from evals.verifiers import verify, semantic_review


def valid_snapshot():
    resume = {'id': 1, 'user_id': 1, 'raw_text': '负责接口开发。',
              'structured_data': {'self_summary': '负责接口开发。', 'source_refs': ['page:1']}}
    fact = {'id': 'fact-1', 'user_id': 1, 'fact_key': 'scope', 'kind': 'experience',
            'content': {'text': '只在测试环境测量。'}, 'source_document_id': 1, 'revision': 1,
            'confirmed_at': '2026-10-01T00:00:00', 'deleted_at': None}
    refs = [{'kind': 'resume', 'resumeId': 1, 'inputVersion': 'frozen-v1',
             'section': '/self_summary', 'sourceRefs': ['page:1']},
            {'kind': 'profile_fact', 'factId': 'fact-1', 'revision': 1},
            {'kind': 'applicant_answer', 'actionId': 'action-1'}]
    snapshot = {'baseline': {'resume': deepcopy(resume), 'facts': [deepcopy(fact)], 'memories': []},
        'resume': resume, 'facts': [fact], 'memories': [],
        'run': {'id': 'run-1', 'user_id': 1, 'session_id': 'session-1', 'status': 'succeeded',
                'attempt': 1, 'execution_epoch': 2, 'output_refs': [{'kind': 'resume_version', 'id': 'draft-1'}],
                'input_versions': {'resume': 'frozen-v1', 'jd': 'job-v1'},
                'input_json': {'resumeId': 1, 'jdId': 1, 'contextSnapshot': {
                    'resume': {'id': 1, 'inputVersion': 'frozen-v1', 'structured': deepcopy(resume['structured_data'])},
                    'facts': [{'id': 'fact-1', 'revision': 1, 'content': fact['content']}]}}},
        'session': {'id': 'session-1', 'user_id': 1, 'active_run_id': None},
        'versions': [{'id': 'draft-1', 'run_id': 'run-1', 'user_id': 1, 'resume_id': 1, 'jd_id': 1,
            'status': 'draft', 'revision': 1, 'fact_refs': deepcopy(refs), 'structured_content': {
                'resume': deepcopy(resume['structured_data']), 'inputVersions': {'resume': 'frozen-v1', 'jd': 'job-v1'},
                'changes': [{'id': 'change-1', 'section': '/self_summary', 'before': '负责接口开发。',
                    'after': '负责测试环境接口开发。', 'reason': '突出已确认的开发职责。',
                    'requires_input': False, 'status': 'pending', 'fact_refs': refs}]}}],
        'operations': [{'run_id': 'run-1', 'operation_key': 'draft:1:initial', 'tool_name': 'create_resume_draft',
                       'status': 'succeeded', 'result_ref': 'draft-1'}],
        'events': [{'run_id': 'run-1', 'seq': 1, 'type': 'artifact.created',
                    'payload': {'artifact_id': 'draft-1', 'kind': 'resume_version'}}],
        'actions': [{'id': 'action-1', 'run_id': 'run-1', 'kind': 'input', 'status': 'answered',
                     'response': {'decision': 'submit', 'answers': {'text': '只在测试环境。'}},
                     'answered_at': '2026-10-02T00:00:00'}]}
    case = {'id': 'test', 'expected': {'statuses': ['succeeded'], 'draft_count': 1,
                                     'requires_answer': True, 'requires_fact': True}}
    output = {'run_id': 'run-1', 'status': 'succeeded', 'coverage': {'checkpoint_reopened': True}}
    return case, output, snapshot


def fail_names(verdict):
    return {check['name'] for check in verdict['checks'] if not check['passed']}


def test_correct_snapshot_passes_without_mutation():
    case, output, snapshot = valid_snapshot()
    original = deepcopy(snapshot)
    assert verify(case, output, snapshot)['passed']
    assert snapshot == original


@pytest.mark.parametrize('mutation,expected', [
    ('duplicate_version', 'draft_count'), ('wrong_output_ref', 'artifact_consistency'),
    ('wrong_before', 'before_matches'), ('wrong_fact_revision', 'source_identity'),
    ('wrong_resume_version', 'source_identity'), ('wrong_fact_owner', 'source_identity'),
    ('wrong_source_marks', 'source_identity'), ('answer_other_run', 'answer_persistence'),
    ('missing_answer', 'answer_persistence'), ('unanswered_action', 'answer_persistence'),
    ('auto_confirmed', 'pending_review'), ('main_resume_overwrite', 'original_resume_unchanged'),
    ('new_fact', 'facts_unchanged'), ('duplicate_operation', 'operation_count'),
    ('duplicate_artifact_event', 'artifact_event_count'),
])
def test_corrupt_snapshot_is_rejected(mutation, expected):
    case, output, data = valid_snapshot()
    version = data['versions'][0]
    change = version['structured_content']['changes'][0]
    if mutation == 'duplicate_version':
        extra = deepcopy(version)
        extra['id'] = 'draft-2'
        data['versions'].append(extra)
    elif mutation == 'wrong_output_ref':
        data['run']['output_refs'][0]['id'] = 'wrong'
    elif mutation == 'wrong_before':
        change['before'] = 'invented original'
    elif mutation == 'wrong_fact_revision':
        change['fact_refs'][1]['revision'] = 2
    elif mutation == 'wrong_resume_version':
        change['fact_refs'][0]['inputVersion'] = 'newer-v2'
    elif mutation == 'wrong_fact_owner':
        data['facts'][0]['user_id'] = 2
    elif mutation == 'wrong_source_marks':
        change['fact_refs'][0]['sourceRefs'] = ['page:999']
    elif mutation == 'answer_other_run':
        data['actions'][0]['run_id'] = 'someone-else'
    elif mutation == 'missing_answer':
        data['actions'] = []
    elif mutation == 'unanswered_action':
        data['actions'][0]['status'] = 'pending'
    elif mutation == 'auto_confirmed':
        version['status'] = 'confirmed'
    elif mutation == 'main_resume_overwrite':
        data['resume']['structured_data']['self_summary'] = change['after']
    elif mutation == 'new_fact':
        data['facts'].append({**data['facts'][0], 'id': 'unrequested-fact'})
    elif mutation == 'duplicate_operation':
        data['operations'].append(deepcopy(data['operations'][0]))
    elif mutation == 'duplicate_artifact_event':
        data['events'].append({**data['events'][0], 'seq': 2})
    verdict = verify(case, output, data)
    assert not verdict['passed']
    assert expected in fail_names(verdict)
    if mutation == 'duplicate_version':
        assert next(c for c in verdict['checks'] if c['name'] == expected)['reason'] == 'draft_count=2; expected=1'


def test_long_context_cannot_pass_from_a_large_input_alone():
    case, output, data = valid_snapshot()
    case['long'] = True
    output['coverage'] = {}
    verdict = verify(case, output, data)
    assert {'actual_summary', 'file_paging', 'checkpoint_reopened', 'required_context_preserved'} <= fail_names(verdict)


def test_rollback_requires_no_artifact_operation_or_event_residue():
    case, output, data = valid_snapshot()
    case['fault'] = 'write'
    case['expected'] = {'statuses': ['failed'], 'draft_count': 0}
    data['run']['status'] = output['status'] = 'failed'
    output['coverage']['fault_injected'] = True
    assert {'draft_count', 'operation_count', 'artifact_event_count'} <= fail_names(verify(case, output, data))


def test_cancel_requires_observed_pause_and_no_followup_calls():
    case, output, data = valid_snapshot()
    case['cancel'] = True
    case['expected'] = {'statuses': ['cancelled'], 'draft_count': 0, 'requires_waiting': True}
    data['run']['status'] = output['status'] = 'cancelled'
    output['coverage'] = {'cancel_claim_blocked': False, 'model_calls_after_cancel': 1}
    assert {'waiting_observed', 'cancel_claim_blocked', 'cancel_stops_calls'} <= fail_names(verify(case, output, data))


def test_semantics_are_never_claimed_from_stub_or_id_checks():
    stub, live = semantic_review('stub'), semantic_review('live')
    assert {item['status'] for item in stub['items']} == {'not_applicable'}
    assert {item['status'] for item in live['items']} == {'unreviewed'}
    assert len(stub['items']) == 4


def test_truthful_no_draft_refusal_is_not_mislabeled_success():
    case, output, data = valid_snapshot()
    case.update(allow_no_draft=True, expected={'statuses': ['succeeded', 'failed'], 'draft_count': 1})
    output['status'] = data['run']['status'] = 'failed'
    data['run']['error_code'] = 'no_draft'
    data['run']['output_refs'] = []
    data['versions'] = data['operations'] = data['events'] = []
    assert verify(case, output, data)['passed']
    data['run']['error_code'] = 'agent_failed'
    assert not verify(case, output, data)['passed']


@pytest.mark.parametrize('section', ['work_experience', 'projects'])
@pytest.mark.parametrize('correct_marks', [True, False])
def test_whole_entry_source_uses_its_own_marks(section, correct_marks):
    case, output, data = valid_snapshot()
    entry = {'description': '负责测试环境接口开发。', 'source_refs': ['page:2:entry:0']}
    version = data['versions'][0]
    for structured in (data['resume']['structured_data'], data['baseline']['resume']['structured_data'],
                       data['run']['input_json']['contextSnapshot']['resume']['structured'],
                       version['structured_content']['resume']):
        structured[section] = [deepcopy(entry)]
    change = version['structured_content']['changes'][0]
    change['fact_refs'][0].update(section=f'/{section}/0',
                                 sourceRefs=entry['source_refs'] if correct_marks else ['page:1'])
    version['fact_refs'] = deepcopy(change['fact_refs'])
    verdict = verify(case, output, data)
    if correct_marks:
        assert verdict['passed'], fail_names(verdict)
    else:
        assert fail_names(verdict) == {'source_identity'}
    # A whole entry is a legal evidence source, but never a legal change target.
    change['section'] = f'/{section}/0'
    assert 'suggestion_shape' in fail_names(verify(case, output, data))


@pytest.mark.parametrize('attempt,epoch', [(2, 2), (3, 3), (3, 4)])
def test_successful_automatic_retry_is_valid(attempt, epoch):
    case, output, data = valid_snapshot()
    data['run'].update(attempt=attempt, execution_epoch=epoch)
    verdict = verify(case, output, data)
    assert verdict['passed'], fail_names(verdict)


@pytest.mark.parametrize('attempt,epoch', [(0, 1), (-1, 1), (4, 4), (1, 0), (2, -1)])
def test_invalid_automatic_attempt_or_unclaimed_epoch_is_rejected(attempt, epoch):
    case, output, data = valid_snapshot()
    data['run'].update(attempt=attempt, execution_epoch=epoch)
    assert fail_names(verify(case, output, data)) == {'run_attempt'}
