"""Read-only T14 SQL oracles, separate from the original tailoring verifier."""


def verify_task(case, output, data):
    coverage, checks = output['coverage'], []
    ids = set(output['subject_run_ids'])
    runs = [row for row in data['runs'] if row['id'] in ids]
    operations = [row for row in data['operations'] if row['run_id'] in ids]
    artifacts = [row for row in data['events'] if row['run_id'] in ids and row['type']=='artifact.created']
    def check(name, passed, reason, refs):
        checks.append(dict(name=name,passed=bool(passed),reason=reason,evidence_refs=refs))
    expected_status = 'cancelled' if case['id']=='cancel-recovery' else 'failed' if case['id'] in {
        'source-deleted-or-reassigned','business-write-rollback'} else 'succeeded'
    check('owned_terminal_runs', bool(runs) and len(runs)==len(ids) and all(
        row['user_id']==1 and row['status']==expected_status for row in runs),
        f'Every scenario Run terminates as {expected_status} under its accepting owner', ['runs'])
    session_ids={row['session_id'] for row in runs}
    check('released_sessions', all(row['active_run_id'] is None for row in data['sessions'] if row['id'] in session_ids),
          'Terminal task sessions are released', ['sessions'])
    check('operation_artifact_atomicity', len(operations)==len(artifacts) and all(row['status']=='succeeded' for row in operations),
          'Successful business operations and artifact events have equal counts', ['operations','events'])
    if expected_status!='succeeded':
        check('no_success_after_stop', not operations and not artifacts and all(row['result_json'] is None for row in runs),
              'Stopped units publish neither operation nor final result', ['runs','operations','events'])
    else:
        check('immutable_result_present', all(row['result_json'] is not None for row in runs),
              'Successful task responses are stored on their own Run', ['runs.result_json'])
    case_id=case['id']
    if case_id=='parse-upload-stable-identity':
        check('same_accepted_identity',coverage['accepted_id']==coverage['duplicate_accepted_id'] and len(data['resumes'])==3
              and coverage['original_file_count']==1,'Duplicate request reuses one accepted source and one original file',['resumes','output.coverage'])
        check('replay_without_model',coverage['calls_on_replay']==0 and coverage['original_result']==coverage['replay_result']
              and len(operations)==1,'Replay returns the saved upload response without parsing again',['runs','operations','output.coverage'])
        check('upload_response_shape',coverage['original_result']['taskId']==coverage['accepted_id']
              and len(coverage['original_result']['documents'])==1,'Upload returns the accepted UUID and documents array',['output.coverage'])
    elif case_id=='parse-reparse-saved-job':
        check('parse_modes',coverage['file_result']['id'].startswith('resume:') and coverage['text_result']['id']=='jd:1'
              and coverage['text_result']['vectorized'] is False and len(operations)==3,
              'File reparse and pasted job return single document responses; pasted text is not vectorized',['runs','operations','output.coverage'])
        check('reparse_version_and_history',coverage['timestamp_advanced'] and coverage['upload_result']==coverage['immutable_upload'],
              'Reparse advances document timestamp and preserves the older upload response',['resumes','output.coverage'])
    elif case_id=='match-partial-candidate-replay':
        check('partial_recovery_unit',coverage['partial_results']==1 and coverage['candidate_calls']=={'First':1,'Second':2},
              'Only the unfinished candidate repeats after partial commit',['output.coverage'])
        check('fixed_analysis_group',len(data['analysis_jobs'])==1 and len(data['candidates'])==2 and len(data['match_results'])==2
              and len(operations)==2,'The same job and candidate identities own both reports',['analysis_jobs','candidates','match_results','operations'])
    elif case_id=='question-result-replay':
        check('old_response_is_immutable',coverage['original_question']==coverage['replayed_question']
              and coverage['original_question']!=coverage['current_question'] and coverage['calls_on_replay']==0,
              'Older task returns its old question after a new explicit task replaces the current set',['runs','question_sets','output.coverage'])
        check('one_current_question_set',len(data['question_sets'])==len(data['followup_sets'])==1 and len(operations)==2,
              'Current question tables contain one set, while each explicit Run has its own operation',['question_sets','followup_sets','operations'])
    elif case_id=='followup-result-replay':
        check('followup_immutable',coverage['original_result']==coverage['replay_result'] and coverage['calls_on_replay']==0 and len(operations)==1,
              'Repeated followup delivery returns its stored response without another model call',['runs','operations','output.coverage'])
    elif case_id=='cancel-recovery':
        check('queued_stale_question_cancel',len(runs)==3 and coverage['queued_claim_blocked'] and coverage['model_calls_after_cancel']==0,
              'Queued cancellation fences claims, stale cancellation converges, question cancellation stops the next call',['runs','output.coverage'])
        check('no_cancelled_questions',not data['question_sets'] and not data['followup_sets'],
              'No question business rows survive a cancelled task',['question_sets','followup_sets'])
    elif case_id=='source-deleted-or-reassigned':
        check('source_checks_exercised',coverage['mutations']==['delete_jd','reassign_resume'] and len(output['model_calls'])==2
              and not data['match_results'],'Both supported source changes occur after a model call and prevent a report',['match_results','output.coverage','output.model_calls'])
    elif case_id=='business-write-rollback':
        check('four_write_boundaries',coverage['fault_kinds']==['document_parse','match_analysis','question_generation','answer_followup']
              and len(runs)==4,'Artifact insertion failed inside all four actual business transactions',['runs','output.coverage'])
        check('business_rows_rolled_back',len(data['match_results'])==1 and not data['question_sets'] and not data['followup_sets']
              and all(not row['structured_data'] and not row['raw_text'] for row in data['resumes'] if row['id']>2),
              'Only the setup match remains; failed reports, parsed output and question tables roll back',['resumes','match_results','question_sets','followup_sets'])
    return {'passed':all(check['passed'] for check in checks),'checks':checks,'limitations':[
        'Deterministic service execution is not a real worker process kill or real-model quality measurement.',
        'Legacy model telemetry remains user-level; interrupted provider usage is unknown, never assumed zero.',
        'This invocation uses isolated SQLite; focused integration tests separately cover disposable MySQL.']}
