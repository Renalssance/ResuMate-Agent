"""Real interview trajectories with either a deterministic or budgeted live SDK model."""
from copy import deepcopy
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch
from uuid import uuid4


def execute_interview_case(request):
    # Imported only inside the already isolated per-case subprocess.
    from sqlalchemy import select, update
    from backend.db.database import Base, engine, SessionLocal
    from backend.db.agent_models import AgentRun, AgentRunEvent, AgentSession, ToolOperation
    from backend.db.career_models import (BusinessMemory, InterviewCommand, InterviewEvent,
        InterviewSession, InterviewTurn, ProfileFact, ResumeVersion)
    from backend.db.models import JobApplication, JobDescription, Resume, User
    from backend.schemas.interviews import InterviewCreate, INTERVIEW_COMMAND_ADAPTER
    from backend.schemas.resume_versions import VersionStatus
    from backend.services import agent_runs, interview_commands, interviews, memory
    from backend.services.agent_runs import RunError
    from backend.services.applications import attach_submission
    from backend.agent_runtime import factory, interviews as runtime
    from evals.interview_verifiers import verify_interview
    from evals.records import write_json
    from evals.interview_records import InterviewCallRecorder, InterviewBudgetRecorder
    from evals.verifiers import semantic_review

    case, invocation = request['case'], Path(request['invocation'])
    inputs = case['input']
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.add_all([User(id=1, username='interview-eval', password_hash='synthetic-not-a-login'),
                    User(id=2, username='other-eval', password_hash='synthetic-not-a-login')])
        db.flush()
        db.add_all([Resume(id=1, user_id=1, filename='synthetic-resume.txt',
                          raw_text=inputs['resume']['raw_text'], structured_data=deepcopy(inputs['resume']['structured_data'])),
                    JobDescription(id=1, user_id=1, title=inputs['job']['title'], company='Synthetic',
                                   raw_text=inputs['job']['raw_text'], structured_data={})])
        db.flush()
        version = ResumeVersion(id=str(uuid4()), user_id=1, resume_id=1, jd_id=1, revision=3,
            status=VersionStatus.CONFIRMED,
            structured_content={'resume': deepcopy(inputs['resume']['structured_data']), 'changes': []}, fact_refs=[])
        db.add(version)
        db.flush()
        db.add(JobApplication(id=1, user_id=1, company='Synthetic', position=inputs['job']['title'],
                             applied_date=date(2026, 10, 30)))
        db.flush()
        attach_submission(db, 1, 1, 1, version.id)
        db.commit()

    def value(item):
        if isinstance(item, Enum):
            return item.value
        if isinstance(item, (datetime, date)):
            return item.isoformat()
        return deepcopy(item)

    tables = {'interviews': InterviewSession, 'turns': InterviewTurn, 'commands': InterviewCommand,
        'events': InterviewEvent, 'runs': AgentRun, 'sessions': AgentSession, 'operations': ToolOperation,
        'run_events': AgentRunEvent, 'facts': ProfileFact, 'memories': BusinessMemory,
        'applications': JobApplication, 'versions': ResumeVersion, 'resumes': Resume, 'jobs': JobDescription}
    def snapshot():
        with SessionLocal() as db:
            return {name: [{column.name: value(getattr(row, column.name)) for column in row.__table__.columns}
                for row in db.scalars(select(model).order_by(model.id))] for name, model in tables.items()}

    mode = request['mode']
    if mode == 'live':
        from evals.budget import BudgetConfig
        from evals.run import make_live_model
        budget = BudgetConfig.from_dict(request['config'])
        recorder = InterviewBudgetRecorder(budget, invocation / 'budget.json', invocation / 'calls.jsonl', case_id=case['id'])
        model = make_live_model(budget, recorder, case)
    else:
        from backend.tests.interview_model_fixture import ScriptedInterviewModel
        recorder = InterviewCallRecorder(invocation / 'calls.jsonl', case_id=case['id'], model='openai:scripted-interview')
        model = ScriptedInterviewModel(model_name='openai:scripted-interview', callbacks=[recorder])
    class GenerationStopped(Exception):
        def __init__(self, code):
            self.code = code
    generation_error = None
    observations, trajectory = {}, []
    baseline_facts = snapshot()['facts']
    with SessionLocal() as db:
        created = interviews.create_interview(db, 1, InterviewCreate(requestId='interview-eval-start', applicationId=1))
    iid = created['interviewId']
    trajectory.append({'action': 'created', **created})

    def view(user_id=1):
        with SessionLocal() as db:
            return interviews.interview_snapshot(db, user_id, iid)

    def command(kind, turn, payload, *, message_id=None, user_id=1):
        data = {'clientMessageId': message_id or str(uuid4()), 'type': kind,
                'expectedTurn': turn, 'payload': payload}
        with SessionLocal() as db:
            ack = interview_commands.handle_command(db, user_id, iid, INTERVIEW_COMMAND_ADAPTER.validate_python(data))
        trajectory.append({'action': 'command.accepted', 'command': data, 'ack': deepcopy(ack)})
        return ack

    def answer(turn, *, message_id=None):
        return command('answer.submit', turn, {'text': inputs['answers'][turn - 1]}, message_id=message_id)

    def execute(run_id, *, cancelled_is_expected=False):
        with SessionLocal() as db:
            epoch = agent_runs.claim_run(db, run_id)
            if epoch is None:
                raise RuntimeError('Interview eval could not claim accepted generation')
            row = db.get(AgentRun, run_id)
            recorder.business_run_id, recorder.attempt, recorder.epoch = run_id, row.attempt, epoch
        trajectory.append({'action': 'claimed', 'run_id': run_id, 'epoch': epoch})
        runtime.run_interview_generation(run_id, epoch)
        with SessionLocal() as db:
            row = db.get(AgentRun, run_id)
            status, error = row.status.value, row.error_code
        trajectory.append({'action': 'handler.returned', 'run_id': run_id, 'epoch': epoch,
                           'status': status, 'error_code': error})
        if status != 'succeeded' and not (cancelled_is_expected and status == 'cancelled'):
            raise GenerationStopped(error or 'interview_generation_failed')
        return epoch

    def rejected(call):
        try:
            call()
        except RunError as error:
            return {'code': error.code, 'status': error.status}
        return {'code': None, 'status': 200}

    def stop_inflight(run_id, turn, kind):
        entered, release, ready = Event(), Event(), Event()
        if mode == 'live':
            entries = list(recorder.ledger['calls'].values())
            remaining = min(budget.max_model_calls - len(entries), budget.max_case_model_calls
                            - sum(item['case_id'] == case['id'] for item in entries))
            # Each context/summary/structured-output call uses this same budget.
            response_wait = max(1, remaining) * budget.request_timeout_seconds + 20
            finish_wait = budget.request_timeout_seconds + 20
        else:
            response_wait, finish_wait = 15, 20
        failures = []
        stopped_step = {}
        def block(record):
            if record['run_id'] == run_id and not entered.is_set():
                stopped_step.update(deepcopy(record['step']))
                entered.set()
                ready.set()
                if not release.wait(15):
                    raise RuntimeError('Interview evaluation cancellation barrier timed out')
        def work():
            try:
                execute(run_id, cancelled_is_expected=True)
            except Exception as error:
                failures.append(error)
            finally:
                ready.set()
        recorder.after_response = block
        thread = Thread(target=work, name='interview-eval-generation')
        thread.start()
        try:
            if not ready.wait(response_wait):
                # Fence any outstanding response before bounded request/SQL cleanup.
                command('generation.cancel', turn, {'runId': run_id})
                raise GenerationStopped('interview_response_timeout')
            if not entered.is_set():
                if failures:
                    raise failures[0]
                raise GenerationStopped('interview_response_missing')
            before = snapshot()
            at_stop = len(recorder.calls)
            settled_at_stop = sum(call.get('ended_at') is not None for call in recorder.calls.values())
            payload = {'runId': run_id} if kind == 'generation.cancel' else {}
            ack = command(kind, turn, payload)
        finally:
            release.set()
            thread.join(finish_wait)
            recorder.after_response = None
            if thread.is_alive():
                raise RuntimeError('Interview evaluation handler did not finish after cancellation')
        if failures:
            raise failures[0]
        return {'type': kind, 'run_id': run_id, 'before': before, 'after': snapshot(),
                'ack': ack, 'model_calls_at_stop': at_stop, 'model_calls_after': len(recorder.calls),
                'settled_calls_at_stop': settled_at_stop, 'public_step_at_stop': stopped_step,
                'barrier': 'after_model_response_before_delivery', 'response_wait_seconds': response_wait}

    try:
        with patch.object(factory, 'model_for_user', lambda _user_id: model):
            if case['id'] == 'interview-frozen-submission':
                observations['frozen_at_start'] = deepcopy(view()['sourceSnapshot'])
                with SessionLocal() as db:
                    db.execute(update(Resume).where(Resume.id == 1).values(raw_text=inputs['replacement_resume'],
                        structured_data={'self_summary': inputs['replacement_resume']}))
                    db.execute(update(JobDescription).where(JobDescription.id == 1).values(raw_text=inputs['replacement_job']))
                    db.commit()
                observations['mutated_sources'] = snapshot()
                observations['other_owner_read'] = rejected(lambda: view(2))
                def wrong_owner_create():
                    with SessionLocal() as db:
                        return interviews.create_interview(db, 2, InterviewCreate(requestId='other-owner', applicationId=1))
                observations['other_owner_create'] = rejected(wrong_owner_create)
            execute(created['runId'])
            if case['id'] in ('interview-followup', 'interview-eight-turn-limit', 'interview-frozen-submission'):
                for index in range(1, len(inputs['answers']) + 1):
                    execute(answer(index)['resultRef'])
                observations['refreshed_snapshot'] = view()
                if case['id'] == 'interview-frozen-submission':
                    with SessionLocal() as db:
                        db.delete(db.get(JobDescription, 1))
                        db.commit()
                    def missing_source_create():
                        with SessionLocal() as db:
                            return interviews.create_interview(db, 1, InterviewCreate(requestId='missing-source', applicationId=1))
                    observations['missing_source_create'] = rejected(missing_source_create)
                    observations['after_source_delete_snapshot'] = view()
            elif case['id'] == 'interview-command-replay':
                first = answer(1, message_id='same-answer')
                observations['first_ack'] = deepcopy(first)
                observations['replayed_ack'] = answer(1, message_id='same-answer')
                observations['payload_conflict'] = rejected(lambda: command('answer.submit', 1,
                    {'text': 'A different answer must not overwrite the first.'}, message_id='same-answer'))['code']
                observations['second_message_rejected'] = rejected(lambda: answer(1, message_id='other-answer'))
                execute(first['resultRef'])
                observations['refreshed_snapshot'] = view()
                command('session.finish', 2, {}, message_id='finish')
                observations['after_finish_ack'] = answer(1, message_id='same-answer')
            elif case['id'] == 'interview-cancel-late-result':
                first = answer(1)
                stops = [stop_inflight(first['resultRef'], 1, 'generation.cancel')]
                retry = command('generation.retry', 1, {'runId': first['resultRef']})
                observations['retry_run_id'] = retry['resultRef']
                execute(retry['resultRef'])
                second = answer(2)
                stops.append(stop_inflight(second['resultRef'], 2, 'session.finish'))
                observations['stops'] = stops
            elif case['id'] == 'interview-feedback-memory':
                execute(answer(1)['resultRef'])
                observations['before_confirmation'] = snapshot()
                def confirm(*, user_id=1, confirmed=True):
                    with SessionLocal() as db:
                        return interviews.confirm_feedback_memory(db, user_id, iid, 1, confirmed=confirmed)
                observations['unconfirmed_rejection'] = rejected(lambda: confirm(confirmed=False))
                observations['other_owner_rejection'] = rejected(lambda: confirm(user_id=2))
                observations['first_memory'] = confirm()
                observations['replayed_memory'] = confirm()
                observations['memory_usage_run'] = answer(2)['resultRef']
                execute(observations['memory_usage_run'])
                with SessionLocal() as db:
                    observations['deletion'] = memory.delete_memory(db, 1, observations['first_memory']['id'])
                observations['after_delete_confirmation'] = rejected(confirm)
                observations['after_delete_generation'] = rejected(lambda: command('answer.submit', 3,
                    {'text': 'This invalidated graph must not accept another answer.'}))
                observations['refreshed_snapshot'] = view()
            else:
                raise ValueError('Unknown interview case')
    except GenerationStopped as error:
        generation_error = error.code

    data = snapshot()
    output = {'executed': bool(recorder.calls), 'interview_id': iid, 'model': recorder.model,
        'mode': mode, 'evidence_source': 'sdk_model_inputs', 'error_code': generation_error,
        'model_calls': deepcopy(recorder.interview_calls),
        'public_model_output': deepcopy(recorder.outputs), 'summary_calls': deepcopy(recorder.interview_summaries),
        'observations': observations, 'trajectory': trajectory, 'baseline_facts': baseline_facts,
        'checkpoint_files': [path.name for path in (Path(engine.url.database).parent / 'agent').glob('checkpoints.sqlite*')]}
    verdict = verify_interview(case, output, data)
    evaluation_error = recorder.summary()['stop_reason'] if mode == 'live' else None
    incomplete = bool(evaluation_error) or generation_error in {'budget_exhausted', 'budget_config_mismatch'}
    result = {'case_id': case['id'], 'category': case['category'], 'mode': request['mode'],
        'status': 'incomplete' if incomplete else ('pass' if verdict['passed'] and not generation_error else 'fail'),
        'error_code': evaluation_error or generation_error, 'input': case, 'output': output,
        'db_snapshot': data, 'verdict': verdict, 'semantic': semantic_review(request['mode'])}
    if mode == 'live':
        result['cost'] = recorder.summary()
    write_json(invocation / 'cases' / f'{case["id"]}.json', result)
    return result
