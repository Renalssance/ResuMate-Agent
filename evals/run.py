"""Explicit local eval CLI. Project imports happen only after database isolation."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
MODEL_ENV_KEYS = {'OPENAI_API_KEY', 'ARK_API_KEY', 'OPENAI_BASE_URL', 'BASE_URL', 'LLM_MODEL', 'MODEL'}


def load_model_env(path):
    from dotenv import dotenv_values
    values = dotenv_values(path, interpolate=False)
    return {key: value for key, value in values.items() if key in MODEL_ENV_KEYS and value is not None}


def isolated_environment(directory, model_env=None):
    directory = Path(directory).resolve()
    # Do not pass storage, broker, tracing or model credentials through implicitly.
    keep = {'PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR', 'SYSTEMROOT', 'WINDIR', 'VIRTUAL_ENV'}
    environment = {key: value for key, value in os.environ.items() if key in keep}
    environment.update(model_env or {})
    environment.update(DATABASE_URL='sqlite:///' + str(directory / 'eval.sqlite'),
                       AGENT_STATE_DIR=str(directory / 'agent'), PYTHON_DOTENV_DISABLED='1',
                       JWT_SECRET_KEY='synthetic-evaluation-only', TOKENIZERS_PARALLELISM='false')
    return environment


def json_value(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def snapshot_case(seed, run_id):
    from sqlalchemy import select
    from backend.db.database import SessionLocal
    from backend.db.agent_models import AgentAction, AgentRun, AgentRunEvent, AgentSession, ToolOperation
    from backend.db.career_models import BusinessMemory, ProfileFact, ResumeVersion
    from backend.db.models import Resume
    def row(item):
        return {column.name: json_value(getattr(item, column.name)) for column in item.__table__.columns}
    with SessionLocal() as db:
        run = db.get(AgentRun, run_id)
        snapshot = dict(run=row(run), session=row(db.get(AgentSession, run.session_id)),
                        resume=row(db.get(Resume, seed['resume_id'])), baseline=seed['baseline'])
        for name, model in [('versions', ResumeVersion), ('operations', ToolOperation),
                            ('events', AgentRunEvent), ('actions', AgentAction)]:
            snapshot[name] = [row(item) for item in db.scalars(select(model).where(model.run_id == run_id))]
        for name, model in [('facts', ProfileFact), ('memories', BusinessMemory)]:
            snapshot[name] = [row(item) for item in db.scalars(select(model).where(model.user_id == seed['user_id']))]
        return snapshot


@contextmanager
def case_injections(case, coverage, mode):
    """Only the harness injects failures/replay; production has no eval switches."""
    from contextlib import ExitStack
    from unittest.mock import patch
    from backend.agent_runtime import tools
    from backend.services import resume_versions
    from backend.services.agent_runs import RunError
    with ExitStack() as stack:
        if case.get('fault') == 'read':
            original = tools._tool_execution
            @contextmanager
            def fail_read(run_id, epoch, tool_name, *args, **kwargs):
                with original(run_id, epoch, tool_name, *args, **kwargs) as result:
                    if tool_name == 'get_application_context' and not coverage['fault_injected']:
                        coverage['fault_injected'] = True
                        raise RunError(503, 'eval_context_unavailable', 'Synthetic context read failure')
                    yield result
            stack.enter_context(patch.object(tools, '_tool_execution', fail_read))
        if case.get('fault') == 'write':
            original_event = resume_versions.append_event
            def fail_commit(db, run_id, event_type, payload):
                result = original_event(db, run_id, event_type, payload)
                if event_type == 'artifact.created' and not coverage['fault_injected']:
                    db.flush()
                    coverage['fault_injected'] = True
                    raise RuntimeError('Synthetic draft transaction failure')
                return result
            stack.enter_context(patch.object(resume_versions, 'append_event', fail_commit))
        if case.get('repeat') and mode == 'live':
            original_save = tools.save_draft
            def replay(run_id, epoch, changes):
                first = original_save(run_id, epoch, changes)
                second = original_save(run_id, epoch, changes)
                coverage['duplicate_result_refs'].extend([first, second])
                coverage['duplicate_replay_source'] = 'harness replay of actual live tool arguments'
                return first
            stack.enter_context(patch.object(tools, 'save_draft', replay))
        yield


def make_live_model(config, recorder, case):
    from langchain_openai import ChatOpenAI
    key = os.getenv('OPENAI_API_KEY') or os.getenv('ARK_API_KEY')
    base_url = os.getenv('OPENAI_BASE_URL') or os.getenv('BASE_URL')
    # A narrow working context forces real SDK summarization in the long case.
    # It must never reduce provider_max_input_tokens used for monetary reserve.
    capacity = min(config.context_window_tokens, 30000) if case.get('long') else config.context_window_tokens
    return ChatOpenAI(model=config.model, api_key=key, base_url=base_url,
                      profile={'max_input_tokens': capacity}, max_tokens=config.max_output_tokens,
                      timeout=config.request_timeout_seconds, max_retries=0, stream_usage=True,
                      extra_body={'enable_thinking': config.enable_thinking}, callbacks=[recorder])


def execute_case(request):
    # The subprocess environment is already isolated before any project import.
    from sqlalchemy import select
    from unittest.mock import patch
    from backend.db.database import SessionLocal
    from backend.db.agent_models import AgentAction, AgentRun
    from backend.db.career_models import ResumeVersion
    from backend.agent_runtime import factory, runner
    from backend.schemas.agent_runs import ActionResponse, RunCreate, RunStatus
    from backend.services import agent_runs
    from evals.fixtures import make_model, seed_case
    from evals.records import CallRecorder, write_json
    from evals.verifiers import semantic_review, verify
    case, mode = request['case'], request['mode']
    invocation = Path(request['invocation'])
    coverage = dict(waiting_observed=False, waiting_draft_count=None, checkpoint_reopened=False,
                    summary_calls=0, file_reads=[], cancel_claim_blocked=False, model_calls_after_cancel=0,
                    fault_injected=False, duplicate_result_refs=[], required_context_preserved=False)
    seed = seed_case(case)
    if mode == 'live':
        from evals.budget import BudgetCallback, BudgetConfig
        budget = BudgetConfig.from_dict(request['config'])
        recorder = BudgetCallback(budget, invocation / 'budget.json', invocation / 'calls.jsonl', case_id=case['id'])
        model = make_live_model(budget, recorder, case)
    else:
        model = make_model(case, seed)
        recorder = CallRecorder(invocation / 'calls.jsonl', case_id=case['id'], model=model.model_name)
        model.callbacks = [recorder]
    with SessionLocal() as db:
        run = agent_runs.create_run(db, seed['user_id'], RunCreate(kind='tailoring', jd_id=seed['jd_id'],
            resume_id=seed['resume_id'], session_id=seed['session_id'], request_id=str(uuid4())))
        run_id = run.id
        from backend.agent_runtime.context import build_context
        required = build_context(db, run).required
        baseline = {key: required[key] for key in ('runId', 'inputVersions', 'constraints', 'facts', 'memories')}
    def expected_context():
        # Snapshot availability at this actual model call, before any provider I/O.
        with SessionLocal() as db:
            return {**baseline,
                'applicantAnswers': [{'actionId': action_id} for action_id in db.scalars(select(AgentAction.id).where(
                    AgentAction.run_id == run_id, AgentAction.kind == 'input', AgentAction.status == 'answered'))],
                'outputs': [{'id': version_id} for version_id in db.scalars(select(ResumeVersion.id).where(
                    ResumeVersion.run_id == run_id))]}
    recorder.context_expectations = expected_context
    recorder.business_run_id = run_id
    invocations, answers = 0, 0
    with patch.object(factory, 'model_for_user', lambda user_id: model), case_injections(case, coverage, mode):
        # Product retries are bounded at three attempts; synthetic input permits
        # one clarification. A second clarification is reported, never fabricated.
        while True:
            with SessionLocal() as db:
                current = db.get(AgentRun, run_id)
                if current.status != RunStatus.QUEUED:
                    break
                epoch = agent_runs.claim_run(db, run_id)
                if epoch is None:
                    break
                recorder.attempt, recorder.epoch = current.attempt, epoch
            invocations += 1
            runner.run_agent(run_id, epoch)
            if invocations > 1 and answers:
                coverage['checkpoint_reopened'] = True
            with SessionLocal() as db:
                current = db.get(AgentRun, run_id)
                if current.status == RunStatus.WAITING_INPUT:
                    coverage['waiting_observed'] = True
                    coverage['waiting_draft_count'] = len(list(db.scalars(select(ResumeVersion).where(ResumeVersion.run_id == run_id))))
                    if case.get('cancel'):
                        calls_before = len(recorder.calls)
                        agent_runs.cancel_run(db, seed['user_id'], run_id)
                        coverage['cancel_claim_blocked'] = agent_runs.claim_run(db, run_id) is None
                        coverage['model_calls_after_cancel'] = len(recorder.calls) - calls_before
                        break
                    if not case.get('answer') or answers:
                        break
                    pending = list(db.scalars(select(AgentAction).where(AgentAction.run_id == run_id, AgentAction.status == 'pending')))
                    for action in pending:
                        agent_runs.answer_action(db, seed['user_id'], run_id, action.id,
                            ActionResponse(decision='submit', answers=case['answer'], expected_revision=1))
                    answers += 1
                elif current.status != RunStatus.QUEUED:
                    break
    snapshot = snapshot_case(seed, run_id)
    coverage['summary_calls'] = recorder.summary_calls()
    coverage['file_reads'] = recorder.file_reads
    if mode == 'stub':
        coverage['duplicate_result_refs'] = list(getattr(model, 'draft_results', []))
    coverage['required_context_preserved'] = bool(recorder.required_contexts) and all(
        proof['passed'] for proof in recorder.required_contexts)
    output = dict(run_id=run_id, status=snapshot['run']['status'], error_code=snapshot['run']['error_code'],
                  coverage=coverage, required_context_checks=recorder.required_contexts,
                  public_model_output=recorder.outputs, model=model.model_name)
    verdict = verify(case, output, snapshot)
    evaluation_error = recorder.summary()['stop_reason'] if mode == 'live' else None
    incomplete = bool(evaluation_error) or output['error_code'] in {'budget_exhausted', 'budget_config_mismatch'}
    result = dict(case_id=case['id'], category=case['category'], mode=mode,
                  status='incomplete' if incomplete else 'pass' if verdict['passed'] else 'fail',
                  input=case, output=output, db_snapshot=snapshot, verdict=verdict,
                  semantic=semantic_review(mode))
    if mode == 'live':
        result['cost'] = recorder.summary()
        if evaluation_error:
            result['error_code'] = evaluation_error
    write_json(invocation / 'cases' / (case['id'] + '.json'), result)
    return result


def write_report(invocation, mode, results, *, error_code=None, configuration_error=None):
    from evals.records import write_json
    counts = {status: sum(item['status'] == status for item in results) for status in ('pass', 'fail', 'incomplete', 'not_run')}
    report = dict(mode=mode, results=results, counts=counts, error_code=error_code,
                  semantic_status='not_applicable' if mode == 'stub' else 'unreviewed',
                  note='Exit code 0 means deterministic checks passed; it does not approve semantic quality.')
    if configuration_error:
        report['configuration_error'] = configuration_error
    if (invocation / 'budget.json').exists():
        from decimal import Decimal
        ledger = json.loads((invocation / 'budget.json').read_text())
        calls = list(ledger['calls'].values())
        report['cost'] = dict(currency=ledger['currency'], model_calls=len(calls), stop_reason=ledger['stop_reason'],
            observed_cost=str(sum((Decimal(call['observed_cost']) for call in calls if call['observed_cost'] is not None), Decimal(0))),
            reserved_cost=str(sum((Decimal(call['reserved_cost']) for call in calls if call['observed_cost'] is None), Decimal(0))),
            unknown_usage_calls=sum(call['observed_cost'] is None for call in calls))
    write_json(invocation / 'report.json', report)
    lines = [f'# {mode} evaluation', '', report['note'], '', f"Semantic review: {report['semantic_status']}", '',
             '| Case | Category | Deterministic result | Reason |', '| --- | --- | --- | --- |']
    lines.extend(f"| {item['case_id']} | {item.get('category', '')} | {item['status']} | {item.get('error_code') or ''} |" for item in results)
    if report.get('cost'):
        lines += ['', 'Costs (reported usage is not a settled invoice):', '', '```json', json.dumps(report['cost'], indent=2), '```']
    if configuration_error:
        lines += ['', configuration_error]
    (invocation / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return 2 if error_code or counts['not_run'] or counts['incomplete'] else 1 if counts['fail'] else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', default='core', choices=['core'])
    parser.add_argument('--mode', choices=['stub', 'live'], default='stub')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cases', help='Comma separated case IDs, for example normal-api')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--_worker', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args._worker:
        # Child gets only an explicit safe environment from the parent.
        request = json.loads(args._worker.read_text())
        try:
            execute_case(request)
            return 0
        except Exception as error:
            from evals.records import write_json
            # Preserve controlled diagnosis without provider text, keys or SQL binds.
            write_json(Path(request['invocation']) / 'cases' / (request['case']['id'] + '.json'),
                dict(case_id=request['case']['id'], category=request['case']['category'], status='incomplete',
                     error_code='harness_error', error_type=type(error).__name__))
            return 2
    invocation = args.output.resolve() / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + str(uuid4())[:8])
    invocation.mkdir(parents=True)
    (invocation / 'calls.jsonl').touch()
    # Even config validation imports RunError; isolate the parent first too.
    model_env = {key: os.environ[key] for key in MODEL_ENV_KEYS if key in os.environ} if args.mode == 'live' else {}
    os.environ.update(DATABASE_URL='sqlite:///:memory:', AGENT_STATE_DIR=str(invocation / 'parent-state'), PYTHON_DOTENV_DISABLED='1')
    from evals.fixtures import load_cases
    from evals.records import write_json
    cases = load_cases(args.suite)
    chosen = args.cases.split(',') if args.cases else [case['id'] for case in cases]
    cases = [case for case in cases if case['id'] in chosen]
    try:
        revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        revision = None
    manifest = dict(suite=args.suite, suite_version=1, mode=args.mode, case_ids=chosen, created_at=datetime.now(timezone.utc).isoformat(),
                    git_commit=revision, dependencies={name: importlib.metadata.version(name) for name in
                    ('deepagents', 'langchain-core', 'langchain-openai', 'langgraph', 'openai')},
                    synthetic_inputs=True, model='synthetic eval stub', tracing='disabled in isolated harness',
                    checkpoint_retention='stub retained; live removed after child exit, including failures',
                    failure_injection='Harness-only read failure, transactional rollback and live duplicate tool replay',
                    rubric_version='v1', config=None)
    config = None
    error = None
    if set(chosen) != {case['id'] for case in cases}:
        error = 'Unknown case ID in --cases'
    if args.mode == 'live' and not error:
        try:
            from evals.budget import BudgetConfig
            if args.config is None:
                raise ValueError('Live mode requires --config with explicit verified capacity, prices and budget')
            config = BudgetConfig.from_dict(json.loads(args.config.read_text())).public()
            if args.env_file:
                if not args.env_file.is_file():
                    raise ValueError('Explicit --env-file was not found')
                model_env = load_model_env(args.env_file)
            if not (model_env.get('OPENAI_API_KEY') or model_env.get('ARK_API_KEY')):
                raise ValueError('Explicit model API key is required')
            if not (model_env.get('OPENAI_BASE_URL') or model_env.get('BASE_URL')):
                raise ValueError('Explicit model base URL is required')
            selected_model = model_env.get('LLM_MODEL') or model_env.get('MODEL')
            if selected_model and selected_model != config['model']:
                raise ValueError('Credential model and verified config model do not match')
            manifest.update(config=config, model=config['model'])
        except (ValueError, OSError, TypeError) as failure:
            error = str(failure) if isinstance(failure, ValueError) and not isinstance(failure, json.JSONDecodeError) else 'Invalid or unreadable live configuration'
    manifest['preflight'] = 'failed' if error else 'passed'
    write_json(invocation / 'manifest.json', manifest)
    if error:
        results = [dict(case_id=case_id, status='not_run', error_code='configuration_error') for case_id in chosen]
        code = write_report(invocation, args.mode, results, error_code='configuration_error', configuration_error=error)
        print(str(invocation))
        return code
    results, stop_reason = [], None
    for case in cases:
        if stop_reason:
            results.append(dict(case_id=case['id'], category=case['category'], status='not_run', error_code=stop_reason))
            continue
        case_directory = invocation / 'state' / case['id']
        case_directory.mkdir(parents=True)
        request_path = case_directory / 'request.json'
        write_json(request_path, dict(case=case, mode=args.mode, config=config, invocation=str(invocation)))
        environment = isolated_environment(case_directory, model_env if args.mode == 'live' else None)
        process = subprocess.run([sys.executable, '-m', 'evals.run', '--output', str(invocation), '--_worker', str(request_path)],
                                 cwd=ROOT, env=environment, capture_output=True, text=True)
        # Checkpoints serve pause/resume only; exclude raw provider message metadata
        # from retained live artifacts after the child closes its real saver.
        if args.mode == 'live':
            for checkpoint in (case_directory / 'agent').glob('checkpoints.sqlite*'):
                checkpoint.unlink()
        # Never persist subprocess stderr: dependencies may include provider bodies.
        result_path = invocation / 'cases' / (case['id'] + '.json')
        if result_path.exists():
            detail = json.loads(result_path.read_text())
            item = {key: detail[key] for key in ('case_id', 'category', 'status')}
            item['error_code'] = detail.get('error_code') or detail.get('output', {}).get('error_code')
            item['artifact'] = 'cases/' + result_path.name
        else:
            item = dict(case_id=case['id'], category=case['category'], status='incomplete', error_code='worker_failed')
        results.append(item)
        if (invocation / 'budget.json').exists():
            stop_reason = json.loads((invocation / 'budget.json').read_text())['stop_reason']
        if process.returncode != 0 and not stop_reason:
            stop_reason = 'harness_error'
    code = write_report(invocation, args.mode, results)
    print(str(invocation))
    return code


if __name__ == '__main__':
    # Libraries can log arbitrary errors; reports retain controlled error codes.
    logging.disable(logging.CRITICAL)
    raise SystemExit(main())
