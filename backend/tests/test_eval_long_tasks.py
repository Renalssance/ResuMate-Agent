"""T14 eval routing and evidence identity: no provider or Compose process is started here."""
import json
from pathlib import Path

from backend.tests.test_eval_runner import launch
from evals.fixtures import load_cases


CRASH_IDS = ['recovery-model-before-return', 'recovery-draft-after-commit',
             'recovery-checkpoint-before-terminal', 'recovery-answer-before-delivery']
TASK_IDS = ['parse-upload-stable-identity', 'parse-reparse-saved-job', 'match-partial-candidate-replay',
            'question-result-replay', 'followup-result-replay', 'cancel-recovery',
            'source-deleted-or-reassigned', 'business-write-rollback']


def test_core_keeps_t14_runner_identities_when_interviews_are_added():
    cases = load_cases()
    originals = [json.loads(line) for line in Path('evals/cases/core.jsonl').read_text().splitlines()]
    assert len(cases) == 30
    assert [case['id'] for case in cases[:12]] == [case['id'] for case in originals]
    assert {case['id'] for case in cases if case.get('runner') == 'compose'} == set(CRASH_IDS)
    assert {case['id'] for case in cases if case.get('runner') == 'durable'} == set(TASK_IDS)


def test_crash_cases_without_this_invocation_evidence_remain_not_run(tmp_path):
    process, report, invocation = launch(tmp_path, '--mode', 'stub', '--cases', ','.join(CRASH_IDS))
    assert process.returncode == 2
    assert report['counts'] == {'pass': 0, 'fail': 0, 'incomplete': 0, 'not_run': 4}
    assert {item['error_code'] for item in report['results']} == {'requires_compose'}
    assert report['executed_count'] == 0
    assert not list(invocation.glob('state/*/eval.sqlite'))


def test_eight_task_cases_save_actual_sql_oracles_and_replay_results(tmp_path):
    process, report, invocation = launch(tmp_path, '--mode', 'stub', '--cases', ','.join(TASK_IDS))
    assert process.returncode == 0, json.dumps(report)
    assert report['executed_count'] == report['counts']['pass'] == 8
    details = {case: json.loads((invocation / 'cases' / f'{case}.json').read_text()) for case in TASK_IDS}
    assert all(detail['db_snapshot']['runs'] and detail['verdict']['passed'] for detail in details.values())
    assert all(detail['input']['runner'] == 'durable' for detail in details.values())
    match = details['match-partial-candidate-replay']
    assert len(match['db_snapshot']['analysis_jobs']) == 1
    assert len(match['db_snapshot']['match_results']) == 2
    assert match['output']['coverage']['candidate_calls'] == {'First': 1, 'Second': 2}
    question = details['question-result-replay']
    assert question['output']['coverage']['original_question'] != question['output']['coverage']['current_question']
    assert question['output']['coverage']['replayed_question'] == question['output']['coverage']['original_question']
    assert details['business-write-rollback']['output']['coverage']['fault_kinds'] == ['document_parse', 'match_analysis', 'question_generation', 'answer_followup']
    assert details['cancel-recovery']['output']['coverage']['model_calls_after_cancel'] == 0
    assert len(list(invocation.glob('state/*/eval.sqlite'))) == 8
    assert all('interrupted provider usage is unknown' in ' '.join(detail['verdict']['limitations']) for detail in details.values())


def test_new_task_live_mode_is_explicitly_unimplemented_without_provider_calls(tmp_path):
    process, report, invocation = launch(tmp_path, '--mode', 'live', '--cases', 'followup-result-replay')
    assert process.returncode == 2
    assert report['results'][0]['error_code'] == 'durable_live_not_implemented'
    assert report['results'][0]['status'] == 'not_run'
    assert not list(invocation.glob('state/*/eval.sqlite'))


def test_evidence_from_other_invocation_or_different_input_is_rejected(tmp_path):
    cases = [case for case in load_cases() if case.get('runner') == 'compose']
    context = {'invocation_id': 'current-evaluation', 'cases': [{'id': case['id'], 'input': case['input']} for case in cases]}
    context_path = tmp_path / 'context.json'
    context_path.write_text(json.dumps(context))
    evidence_path = tmp_path / 'evidence.json'
    evidence_path.write_text(json.dumps({'invocation_id': 'older-evaluation', 'results': []}))
    process, report, _ = launch(tmp_path, '--mode', 'stub', '--cases', ','.join(CRASH_IDS),
        '--recovery-context', str(context_path), '--recovery-evidence', str(evidence_path))
    assert process.returncode == 2
    assert all(item['status'] == 'not_run' and item['error_code'] == 'recovery_evidence_mismatch' for item in report['results'])


def test_matching_evidence_is_accepted_but_changed_case_input_is_not():
    """Synthetic evidence exercises the importer only; it is never an eval artifact."""
    from copy import deepcopy
    from evals.recovery_evidence import merge_case
    case = next(item for item in load_cases() if item['id']=='recovery-model-before-return')
    context = {'invocation_id':'contract-unit-test'}
    row = {'invocation_id':'contract-unit-test','case_id':case['id'],'input':case['input'],'executed':True,'status':'pass',
           'observed':{'kill_signal':'SIGKILL','killed_state':{'ExitCode':137},
                       'run_before':{'status':'running','attempt':1,'execution_epoch':1},
                       'run_after':{'status':'succeeded','attempt':2,'execution_epoch':2},
                       'version_ids':['version-1'],'operation_rows':[{'result_ref':'version-1'}],
                       'events':[{'type':'artifact.created'}],'model_starts_before':1,'model_starts_after':2}}
    evidence = {'invocation_id':'contract-unit-test','results':[row]}
    merged = merge_case(case,context,evidence)
    assert merged['status']=='pass' and merged['verdict']['passed'] is True
    changed = deepcopy(evidence)
    changed['results'][0]['input']['resume']['raw_text']='different synthetic source'
    assert merge_case(case,context,changed) is None
    missing_process = deepcopy(evidence)
    missing_process['results'][0]['observed']['kill_signal']='none'
    assert merge_case(case,context,missing_process)['status']=='fail'


def test_full_core_without_compose_evidence_executes_twenty_six_and_leaves_four_unrun(tmp_path):
    """Root runs this once with the full backend suite; no imported historical evidence."""
    process, report, invocation = launch(tmp_path, '--mode', 'stub')
    assert process.returncode == 2, json.dumps(report)
    assert report['counts'] == {'pass':26,'fail':0,'incomplete':0,'not_run':4}
    assert report['executed_count'] == 26
    missing = [item for item in report['results'] if item['status']=='not_run']
    assert {item['case_id'] for item in missing} == set(CRASH_IDS)
    assert {item['error_code'] for item in missing} == {'requires_compose'}
    assert len(list((invocation/'cases').glob('*.json'))) == 26
    assert len(list(invocation.glob('state/*/eval.sqlite'))) == 26
