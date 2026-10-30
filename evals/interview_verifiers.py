"""Read-only SQL and actual model-input oracles for the six T16 trajectories."""
import re

INTERVIEW_IDS = {'interview-followup', 'interview-eight-turn-limit', 'interview-command-replay',
                 'interview-cancel-late-result', 'interview-frozen-submission', 'interview-feedback-memory'}


def _contains(value, quote):
    if isinstance(value, str):
        return bool(quote) and quote in value
    if isinstance(value, dict):
        return any(_contains(child, quote) for child in value.values())
    if isinstance(value, list):
        return any(_contains(child, quote) for child in value)
    return False


def _valid_ref(ref, source, turns):
    quote = ref.get('quote')
    if not isinstance(quote, str) or not quote:
        return False
    if ref.get('kind') == 'answer':
        turn = next((row for row in turns if row['turn_index'] == ref.get('turnIndex')), {})
        return (turn.get('id') == ref.get('turnId') and bool(turn.get('answer'))
                and quote in turn['answer'])
    if ref.get('kind') == 'job':
        job = source.get('job', {})
        return (ref.get('jdId') == job.get('jdId') and ref.get('capturedAt') == job.get('capturedAt')
                and _contains([job.get('rawText'), job.get('structuredData')], quote))
    if ref.get('kind') == 'resume':
        value = source.get('structuredContent', {}).get('resume', {})
        path = re.sub(r'\[(\d+)\]', r'.\1', ref.get('section', ''))
        segments = path.lstrip('/').split('/') if path.startswith('/') else path.split('.')
        for segment in segments:
            if isinstance(value, dict):
                value = value.get(segment)
            elif isinstance(value, list) and segment.isdigit() and int(segment) < len(value):
                value = value[int(segment)]
            else:
                return False
        return (ref.get('resumeVersionId') == source.get('resumeVersionId')
                and ref.get('revision') == source.get('revision') and _contains(value, quote))
    return False


def verify_interview(case, output, data):
    checks = []
    def check(name, passed, reason, refs):
        checks.append({'name': name, 'passed': bool(passed), 'reason': reason, 'evidence_refs': refs})
    iid = output.get('interview_id')
    interviews = [row for row in data.get('interviews', []) if row.get('id') == iid]
    interview = interviews[0] if len(interviews) == 1 else {}
    source = interview.get('source_snapshot') or {}
    turns = sorted([row for row in data.get('turns', []) if row.get('interview_id') == iid], key=lambda row: row['turn_index'])
    runs = [row for row in data.get('runs', []) if row.get('input_json', {}).get('interviewId') == iid]
    events = [row for row in data.get('events', []) if row.get('interview_id') == iid]
    run_ids = {row['id'] for row in runs}
    calls = output.get('model_calls') or []
    successes = [row for row in runs if row['status'] == 'succeeded']
    operations = [row for row in data.get('operations', []) if row.get('run_id') in run_ids]
    check('actual_execution', output.get('executed') is True and bool(calls) and bool(runs)
          and all(call.get('run_id') in run_ids and isinstance(call.get('required'), dict) for call in calls)
          and all(any(call.get('run_id') == row['id'] for call in calls) for row in successes),
          'The case reached real generation calls and persisted their Run identities', ['output.model_calls', 'runs'])
    if output.get('evidence_source') == 'sdk_model_inputs':
        by_id = {row['id']: row for row in runs}
        actual_calls = [*calls, *(output.get('summary_calls') or [])]
        identities = bool(actual_calls)
        for call in actual_calls:
            row, required = by_id.get(call.get('run_id'), {}), call.get('required', {})
            identities = identities and bool(row) and call.get('required_block_count') == 1
            identities = identities and required.get('runId') == row.get('id')
            identities = identities and required.get('sessionId') == row.get('session_id')
            identities = identities and required.get('interviewId') == iid
            identities = identities and required.get('expectedTurn') == row.get('input_json', {}).get('expectedTurn')
            identities = identities and call.get('execution_epoch') == row.get('execution_epoch')
            identities = identities and call.get('attempt') == row.get('attempt')
        check('sdk_input_identity', identities,
              'Every main/summary input contains one current required block bound to its Run and execution epoch',
              ['output.model_calls', 'output.summary_calls', 'runs'])
    check('owned_frozen_session', len(interviews) == 1 and interview.get('user_id') == 1 and bool(source)
          and all(row['user_id'] == 1 and row['kind'] == 'interview_generation' for row in runs),
          'An owned interview keeps the accepted frozen source', ['interviews', 'runs'])
    check('bounded_unique_rounds', bool(turns) and [row['turn_index'] for row in turns] == list(range(1, len(turns) + 1))
          and len(turns) <= 8 and all(row.get('question') for row in turns),
          'Persisted rounds are contiguous, unique, and bounded by eight', ['turns'])
    refs = [ref for turn in turns for ref in (turn.get('question_context') or {}).get('refs', [])]
    for turn in turns:
        feedback = turn.get('feedback') or {}
        refs.extend(ref for point in [*feedback.get('strengths', []), *feedback.get('improvements', [])]
                    for ref in point.get('refs', []))
    check('frozen_reference_integrity', bool(refs) and all(_valid_ref(ref, source, turns) for ref in refs)
          and all((turn.get('question_context') or {}).get('refs') for turn in turns),
          'Question and feedback quotes resolve to the exact snapshot or accepted answer', ['turns', 'interviews.source_snapshot'])
    question_events = [row['payload'].get('turnIndex') for row in events if row['type'] == 'question.completed']
    feedback_events = [row['payload'].get('turnIndex') for row in events if row['type'] == 'feedback.ready']
    check('durable_question_feedback_events', sorted(question_events) == [row['turn_index'] for row in turns]
          and sorted(feedback_events) == [row['turn_index'] for row in turns if row.get('feedback')]
          and [row['seq'] for row in events] == list(range(1, len(events) + 1)),
          'Each committed question/feedback has exactly one ordered SQL event', ['turns', 'events'])
    atomic = all(len([op for op in operations if op['run_id'] == row['id']]) == 1
                 and row.get('result_json') is not None for row in successes)
    atomic = atomic and len(operations) == len(successes) and all(
        op.get('operation_key') == 'interview:step' and op.get('status') == 'succeeded' for op in operations)
    atomic = atomic and all(row.get('result_json') is None for row in runs if row['status'] != 'succeeded')
    check('run_result_operation_atomicity', atomic and bool(successes),
          'Successful steps own one immutable result and operation; stopped steps own neither', ['runs', 'operations'])
    answered = [row for row in turns if row.get('answer') is not None]
    case_id = case.get('id')
    observations = output.get('observations', {})
    check('practice_does_not_create_facts', data.get('facts', []) == output.get('baseline_facts', []),
          'Practice answers do not become ProfileFact records', ['facts', 'output.baseline_facts'])
    if case_id == 'interview-followup':
        followups = [row for row in turns if (row.get('question_context') or {}).get('mode') == 'follow_up']
        context_ok = all(any(call['required'].get('expectedTurn') == row['turn_index']
            and (call['required'].get('currentAnswer') or {}).get('answer') == row['answer']
            and any(item.get('turnIndex') == row['turn_index'] and item.get('answer') == row['answer']
                    for item in call.get('context', {}).get('turns', [])) for call in calls) for row in answered)
        check('two_answer_based_followups', len(turns) == 3 and len(answered) == 2 and len(followups) == 2
              and all(row.get('feedback') for row in answered) and context_ok,
              'Two accepted answers reach actual model input and each leads to a persisted follow-up',
              ['turns', 'output.model_calls'])
    elif case_id == 'interview-eight-turn-limit':
        final_runs = [row for row in successes if row['input_json']['expectedTurn'] == 8]
        check('eighth_feedback_finishes_without_ninth_question', len(turns) == len(answered) == 8
              and all(row.get('feedback') for row in turns) and interview.get('status') == 'finished'
              and len(final_runs) == 1 and final_runs[0]['result_json'].get('question') is None
              and final_runs[0]['result_json'].get('feedback') == turns[-1]['feedback']
              and len([row for row in events if row['type'] == 'session.finished']) == 1,
              'The eighth answer owns feedback and a final session state, with no ninth question',
              ['turns', 'runs', 'interviews', 'events'])
    elif case_id == 'interview-command-replay':
        commands = [row for row in data.get('commands', []) if row.get('interview_id') == iid and row['type'] == 'answer.submit']
        first = observations.get('first_ack')
        refreshed = observations.get('refreshed_snapshot', {})
        check('lost_ack_has_one_answer_and_one_generation', bool(first)
              and first == observations.get('replayed_ack') == observations.get('after_finish_ack')
              and len(commands) == 1 and commands[0].get('ack_json') == first
              and commands[0].get('result_ref') == first.get('resultRef')
              and len(runs) == 2 and len(answered) == 1 and len(turns) == 2
              and answered[0]['answer'] == case['input']['answers'][0]
              and observations.get('payload_conflict') == 'command_payload_conflict'
              and observations.get('second_message_rejected', {}).get('code') == 'answer_already_submitted'
              and refreshed.get('currentTurn') == 2 and interview.get('status') == 'finished',
              'Replay after lost ack and after finish returns the original ack without accepting another answer',
              ['commands', 'turns', 'runs', 'output.observations'])
    elif case_id == 'interview-cancel-late-result':
        stops = observations.get('stops', [])
        no_late = len(stops) == 2 and [item.get('type') for item in stops] == ['generation.cancel', 'session.finish']
        for stop in stops:
            before, after = stop.get('before', {}), stop.get('after', {})
            old = next((row for row in before.get('runs', []) if row['id'] == stop.get('run_id')), {})
            stopped = next((row for row in after.get('runs', []) if row['id'] == stop.get('run_id')), {})
            before_business = [row for row in before.get('events', []) if row['type'] in ('question.completed', 'feedback.ready')]
            after_business = [row for row in after.get('events', []) if row['type'] in ('question.completed', 'feedback.ready')]
            no_late = no_late and old.get('status') == 'running' and stopped.get('status') == 'cancelled'
            no_late = no_late and stopped.get('cancel_requested_at') is not None and stopped.get('result_json') is None
            no_late = no_late and before.get('turns') == after.get('turns') and before_business == after_business
            no_late = no_late and not any(row['run_id'] == stop.get('run_id') for row in after.get('operations', []))
            no_late = no_late and stop.get('model_calls_at_stop', 0) > 0 and stop.get('model_calls_after', 0) == stop['model_calls_at_stop']
        retried = next((row for row in runs if row['id'] == observations.get('retry_run_id')), {})
        check('cancel_and_finish_fence_inflight_results', no_late and interview.get('status') == 'finished',
              'Both commands commit after a model response and before delivery; late output adds no business result',
              ['output.observations.stops', 'interviews'])
        check('retry_keeps_original_answer', retried.get('status') == 'succeeded'
              and retried.get('input_json', {}).get('expectedTurn') == 1 and len(answered) == 2
              and answered[0]['answer'] == case['input']['answers'][0],
              'A new generation retries the accepted first answer without replacing it', ['runs', 'turns'])
    elif case_id == 'interview-frozen-submission':
        contexts = [call['context'] for call in calls if 'context' in call]
        mutated = observations.get('mutated_sources', {})
        check('frozen_source_survives_supported_edits_and_deletion', bool(contexts)
              and source == observations.get('frozen_at_start')
              and source.get('structuredContent', {}).get('resume') == case['input']['resume']['structured_data']
              and source.get('job', {}).get('rawText') == case['input']['job']['raw_text']
              and all(context.get('source') == source for context in contexts)
              and any(row.get('raw_text') == case['input']['replacement_resume'] for row in mutated.get('resumes', []))
              and any(row.get('raw_text') == case['input']['replacement_job'] for row in mutated.get('jobs', []))
              and data.get('jobs') == [] and observations.get('after_source_delete_snapshot', {}).get('sourceSnapshot') == source,
              'Models and restored interview retain accepted material after source edits and job deletion',
              ['interviews.source_snapshot', 'jobs', 'output.model_calls', 'output.observations'])
        check('source_ownership_and_missing_source_rejected',
              observations.get('other_owner_read', {}).get('status') == 404
              and observations.get('other_owner_create', {}).get('status') == 404
              and observations.get('missing_source_create', {}).get('status') == 404
              and len(data.get('interviews', [])) == 1,
              'Other owners and a new interview whose required source was deleted cannot create or read it',
              ['interviews', 'output.observations'])
    elif case_id == 'interview-feedback-memory':
        first, repeated = observations.get('first_memory', {}), observations.get('replayed_memory', {})
        memories = data.get('memories', [])
        source_ref = first.get('sourceRef', {})
        first_turn = turns[0] if turns else {}
        memory_contexts = [call.get('context', {}) for call in calls
                           if call.get('run_id') == observations.get('memory_usage_run')]
        check('confirmation_binds_one_real_feedback_memory', observations.get('before_confirmation', {}).get('memories') == []
              and observations.get('unconfirmed_rejection', {}).get('status') == 422
              and observations.get('other_owner_rejection', {}).get('status') == 404
              and bool(first) and first == repeated and len(memories) == 1 and memories[0]['id'] == first.get('id')
              and source_ref == {'kind': 'interview_turn', 'interviewId': iid, 'turnId': first_turn.get('id')}
              and first.get('content') == (first_turn.get('feedback') or {}).get('practiceFocus')
              and any(any(item.get('id') == first['id'] for item in context.get('memories', [])) for context in memory_contexts),
              'Only explicit confirmation creates one source-bound memory used by a later real model call',
              ['memories', 'turns', 'output.observations', 'output.model_calls'])
        check('deletion_cannot_resurrect_practice_memory', len(memories) == 1
              and memories[0].get('deleted_at') is not None and memories[0].get('content') == ''
              and observations.get('after_delete_confirmation', {}).get('code') == 'memory_deleted'
              and observations.get('after_delete_generation', {}).get('code') == 'session_context_invalidated'
              and observations.get('refreshed_snapshot', {}).get('sessionInvalidated') is True,
              'Deletion clears memory content, invalidates the old graph and rejects reconfirmation or another answer',
              ['memories', 'sessions', 'output.observations'])
    else:
        check('scenario_oracle', False, 'Unknown case IDs have no accepted scenario oracle', ['input.id'])
    return {'passed': all(item['passed'] for item in checks), 'checks': checks, 'limitations': [
        'Quoted text existing is not proof of semantic quality; live output requires human review.',
        'This case uses isolated SQLite with real services and Deep Agents, not a process-kill experiment.',
        'Live mode uses the configured SDK model and shared invocation budget; stub mode uses a deterministic model.']}
