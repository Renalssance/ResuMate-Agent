"""Read-only checks over independently collected SQL rows; no production validators."""
import re


EDITABLE = re.compile(r'^/(self_summary|summary|work_experience/(0|[1-9][0-9]*)/description|projects/(0|[1-9][0-9]*)/description)$')


def _field(document, path):
    value, refs = document, []
    for part in path.removeprefix('/').split('/'):
        if isinstance(value, dict):
            refs = value.get('source_refs', refs)
            value = value[part]
        else:
            value = value[int(part)]
    if isinstance(value, dict):
        refs = value.get('source_refs', refs)
    return value, refs


def _same_rows(before, after):
    # Compare the baseline's explicit business columns, including additions/deletions.
    current = {row['id']: row for row in after}
    return len(before) == len(after) and all(
        row['id'] in current and all(current[row['id']].get(key) == value for key, value in row.items())
        for row in before)


def verify(case, output, db_snapshot):
    """Return individual invariants, never a semantic quality score."""
    data, expected, checks = db_snapshot, case['expected'], []
    run, session, baseline = data['run'], data['session'], data['baseline']
    run_id = output['run_id']
    frozen = run['input_json']['contextSnapshot']
    base = frozen['resume']['structured']
    versions = [row for row in data['versions'] if row['run_id'] == run_id]
    operations = [row for row in data['operations'] if row['run_id'] == run_id]
    events = [row for row in data['events'] if row['run_id'] == run_id]
    artifacts = [row for row in events if row['type'] == 'artifact.created']
    actions = {row['id']: row for row in data['actions']}
    facts = {row['id']: row for row in data['facts']}
    frozen_facts = {row['id']: row for row in frozen.get('facts', [])}
    coverage = output.get('coverage', {})

    def check(name, passed, reason, refs=()):
        checks.append({'name': name, 'passed': bool(passed), 'reason': reason, 'evidence_refs': list(refs)})

    refused_without_draft = bool(case.get('allow_no_draft') and run['status'] == 'failed' and run.get('error_code') == 'no_draft')
    count = 0 if refused_without_draft else expected['draft_count']
    check('run_identity', run['id'] == run_id and run['user_id'] == session['user_id']
          and run['session_id'] == session['id'], 'SQL Run and session belong to the evaluated user', ['run', 'session'])
    check('run_status', run['status'] in expected['statuses'] and output['status'] == run['status']
          and (run['status'] != 'failed' or not case.get('allow_no_draft') or refused_without_draft),
          f"status={run['status']}; expected={expected['statuses']}", ['run.status'])
    if expected.get('error_code'):
        check('error_code', run.get('error_code') == expected['error_code'],
              f"error_code={run.get('error_code')}; expected={expected['error_code']}", ['run.error_code'])
    check('run_attempt', 1 <= run['attempt'] <= 3 and run['execution_epoch'] >= 1,
          f"attempt={run['attempt']}; epoch={run['execution_epoch']}", ['run'])
    check('session_released', session['active_run_id'] is None, 'Terminal Run releases its session', ['session.active_run_id'])
    check('draft_count', len(versions) == count, f'draft_count={len(versions)}; expected={count}', ['versions'])
    check('operation_count', len(operations) == count, f'operation_count={len(operations)}; expected={count}', ['operations'])
    check('artifact_event_count', len(artifacts) == count, f'artifact_event_count={len(artifacts)}; expected={count}', ['events'])
    ids = [row['id'] for row in versions]
    check('artifact_consistency',
          sorted(ref['id'] for ref in run['output_refs']) == sorted(ids)
          and all(ref.get('type', ref.get('kind')) == 'resume_version' for ref in run['output_refs'])
          and sorted(row['result_ref'] for row in operations) == sorted(ids)
          and all(row['status'] == 'succeeded' and row['tool_name'] == 'create_resume_draft'
                  and row['operation_key'] == f"draft:{run['input_json']['jdId']}:initial" for row in operations)
          and sorted(row['payload']['artifact_id'] for row in artifacts) == sorted(ids)
          and all(row['payload']['kind'] == 'resume_version' for row in artifacts),
          'Run, saved operation and artifact event reference exactly the persisted versions', ['run.output_refs', 'operations', 'events'])
    check('original_resume_unchanged', all(data['resume'].get(key) == value for key, value in baseline['resume'].items()),
          'Original resume business fields match the pre-run baseline', ['resume', 'baseline.resume'])
    check('facts_unchanged', _same_rows(baseline['facts'], data['facts']),
          'No fact was inserted, confirmed, edited or deleted by the agent', ['facts', 'baseline.facts'])
    check('memories_unchanged', _same_rows(baseline['memories'], data['memories']),
          'No preference was silently inserted or changed', ['memories', 'baseline.memories'])

    changes = [change for row in versions for change in row['structured_content'].get('changes', [])]
    check('version_identity', all(row['user_id'] == run['user_id']
          and row['resume_id'] == run['input_json']['resumeId'] and row['jd_id'] == run['input_json']['jdId']
          and row['structured_content'].get('inputVersions') == run['input_versions']
          and row['structured_content'].get('resume') == base for row in versions),
          'Draft keeps the owned resume, job, frozen versions and unchanged review base', ['versions', 'run.input_versions'])
    check('pending_review', all(row['status'] == 'draft' and row['revision'] == 1 for row in versions)
          and all(change['status'] == 'pending' for change in changes),
          'All suggested changes remain pending in an unconfirmed draft', ['versions'])
    check('nonempty_suggestions', not versions or all(row['structured_content'].get('changes') for row in versions),
          'Expected drafts contain reviewable field suggestions', ['versions.structured_content.changes'])
    before_ok, shape_ok, source_ok = True, True, True
    all_refs, answer_refs, fact_refs = [], [], []
    for version in versions:
        proposed = version['structured_content'].get('changes', [])
        shape_ok &= len({change['section'] for change in proposed}) == len(proposed)
        version_refs = []
        for change in proposed:
            section = change['section']
            shape_ok &= bool(EDITABLE.fullmatch(section)) and bool(change['reason'].strip())
            shape_ok &= (change['after'] is None if change['requires_input'] else
                         isinstance(change['after'], str) and bool(change['fact_refs']))
            try:
                before_ok &= _field(base, section)[0] == change['before']
            except (KeyError, IndexError, TypeError, ValueError):
                before_ok = False
            for ref in change['fact_refs']:
                if ref not in version_refs:
                    version_refs.append(ref)
                all_refs.append(ref)
                kind = ref['kind']
                if kind == 'resume':
                    source_ok &= ref['resumeId'] == frozen['resume']['id'] and ref['inputVersion'] == frozen['resume']['inputVersion']
                    source_ok &= data['resume']['user_id'] == run['user_id']
                    try:
                        source_ok &= ref['sourceRefs'] == _field(base, ref['section'])[1]
                    except (KeyError, IndexError, TypeError, ValueError):
                        source_ok = False
                elif kind == 'profile_fact':
                    fact_refs.append(ref)
                    fact, captured = facts.get(ref['factId']), frozen_facts.get(ref['factId'])
                    source_ok &= bool(fact and captured and ref['revision'] == fact['revision'] == captured['revision']
                        and fact['user_id'] == run['user_id'] and fact['confirmed_at'] and not fact['deleted_at']
                        and fact['source_document_id'] in (None, run['input_json']['resumeId']))
                elif kind == 'applicant_answer':
                    answer_refs.append(ref)
                    action = actions.get(ref['actionId'])
                    source_ok &= bool(action and action['run_id'] == run_id and action['kind'] == 'input'
                        and action['status'] == 'answered' and action['answered_at'] and action.get('response')
                        and action['response'].get('decision') == 'submit' and action['response'].get('answers'))
                else:
                    source_ok = False
        source_ok &= version['fact_refs'] == version_refs
    check('suggestion_shape', shape_ok, 'Editable fields occur once and missing information has no invented replacement', ['versions'])
    check('before_matches', before_ok, 'Every before value equals its actual frozen resume field', ['versions', 'run.input_json.contextSnapshot.resume'])
    check('source_identity', source_ok, 'Source IDs, owner, frozen version, source marks and answer ownership agree; this does not establish textual truth', ['versions.fact_refs', 'facts', 'actions'])
    valid_answers = [a for a in actions.values() if a['run_id'] == run_id and a['kind'] == 'input'
                     and a['status'] == 'answered' and a.get('answered_at') and a.get('response')
                     and a['response'].get('decision') == 'submit' and a['response'].get('answers')]
    if expected.get('requires_answer'):
        check('answer_persistence', bool(valid_answers) and bool(answer_refs)
              and all(any(a['id'] == ref['actionId'] for a in valid_answers) for ref in answer_refs),
              'The submitted answer remains in this Run and is cited by the draft', ['actions', 'versions.fact_refs'])
    if expected.get('requires_fact'):
        check('confirmed_fact_used', bool(fact_refs), 'The case-specific confirmed fact is cited', ['versions.fact_refs'])
    if expected.get('requires_waiting'):
        check('waiting_observed', coverage.get('waiting_observed') is True and coverage.get('waiting_draft_count') == 0,
              'A real waiting_input phase occurred before any draft was written', ['output.coverage'])
    if case.get('fault'):
        tool = 'get_application_context' if case['fault'] == 'read' else 'create_resume_draft'
        check('fault_exercised', coverage.get('fault_injected') is True,
              'The selected failure was injected inside actual tool execution', ['output.coverage'])
        starts = [e for e in events if e['type'] == 'tool.started' and e['payload']['tool_name'] == tool]
        failures = [e for e in events if e['type'] == 'tool.failed' and e['payload']['tool_name'] == tool]
        check('tool_failure_recorded', bool(starts and failures and min(e['seq'] for e in starts) < min(e['seq'] for e in failures)),
              'A real tool.started precedes tool.failed', ['events'])
    if case.get('repeat'):
        refs = coverage.get('duplicate_result_refs', [])
        check('duplicate_idempotent', len(refs) >= 2 and len(set(refs)) == 1 and refs[0] in ids,
              f'repeated execution results={refs}', ['output.coverage', 'versions'])
    if case.get('cancel'):
        check('cancel_claim_blocked', coverage.get('cancel_claim_blocked') is True,
              'The cancelled Run could not be claimed again', ['output.coverage'])
        check('cancel_stops_calls', coverage.get('model_calls_after_cancel') == 0,
              'No model invocation occurred after cancellation', ['output.coverage'])
    if expected.get('requires_answer') or case.get('long'):
        check('checkpoint_reopened', coverage.get('checkpoint_reopened') is True,
              'Resume used a reopened persisted checkpoint', ['output.coverage'])
    if case.get('long'):
        check('actual_summary', coverage.get('summary_calls', 0) > 0,
              f"actual SDK summary calls={coverage.get('summary_calls', 0)}", ['output.coverage'])
        check('file_paging', len(coverage.get('file_reads', [])) >= 3,
              'At least three actual input file reads occurred', ['output.coverage'])
        check('required_context_preserved', coverage.get('required_context_preserved') is True,
              'Actual context retained constraints, versions, answer and artifact references across resume', ['output.coverage'])
    return {'passed': all(item['passed'] for item in checks), 'checks': checks,
            'limitations': ['Legal source identity does not prove that natural-language claims are true.',
                            'Stub outputs do not measure real-model quality or latency.']}


def semantic_review(mode):
    titles = [('factual_grounding', '事实依据'), ('task_usefulness', '岗位任务有效性'),
              ('missing_information', '缺信息处理'), ('expression_and_review', '表达与审阅')]
    return {'rubric_version': 't13-v1', 'items': [
        {'id': key, 'title': title, 'status': 'not_applicable' if mode == 'stub' else 'unreviewed',
         'evidence': [], 'reason': '确定性 stub 不评价真实模型语义。' if mode == 'stub' else '等待人工逐项审阅实际输入与输出。'}
        for key, title in titles]}
