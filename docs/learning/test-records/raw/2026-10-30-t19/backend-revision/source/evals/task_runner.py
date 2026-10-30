"""T14 deterministic scenarios run actual acceptance, claims, handlers and SQL writes."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4


def execute_task_case(request):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from sqlalchemy import event, select
    from backend.auth.security import get_current_user
    from backend.db.database import Base, engine, SessionLocal, get_db
    from backend.db.agent_models import AgentRun, AgentRunEvent, AgentSession, ToolOperation
    from backend.db.models import (User, Resume, JobDescription, AnalysisJob, AnalysisCandidate,
                                   MatchResult, InterviewQuestionSet, FollowUpQuestionSet, utcnow)
    from backend.rag.mysql import MySQLRagStore, DocumentEmbeddingChunk
    from backend.routes import documents
    from backend.schemas.agent_runs import RunCreate
    from backend.services import agent_runs, analysis_tasks, document_tasks, background_tasks
    from backend.services.documents import store_upload
    from evals.records import write_json
    from evals.run import json_value
    from evals.task_fixtures import JOB_PROFILE, TaskEmbedding, TaskModel
    from evals.task_verifiers import verify_task
    from evals.verifiers import semantic_review

    case, mode = request['case'], request['mode']
    recorder = None
    if mode == 'live':
        from evals.budget import BudgetCallback, BudgetConfig
        from evals.task_live_model import LiveTaskModel
        budget = BudgetConfig.from_dict(request['config'])
        recorder = BudgetCallback(budget, Path(request['invocation']) / 'budget.json',
                                  Path(request['invocation']) / 'calls.jsonl', case_id=case['id'])
        model = LiveTaskModel(budget, recorder)
    else:
        model = TaskModel()
    class CaseStopped(Exception):
        pass
    accepted_runs = []
    directory = Path(engine.url.database).parent
    originals = directory / 'originals'
    rag = MySQLRagStore(session_factory=SessionLocal, embedding_client=TaskEmbedding())
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.add_all([User(id=1, username='task-eval', password_hash='not-a-login'), User(id=2, username='other', password_hash='not-a-login')])
        db.flush()
        db.add_all([Resume(id=1, user_id=1, filename='first.txt', raw_text=case['input']['resume_text'], structured_data={'candidate_name':'First'}),
                    Resume(id=2, user_id=1, filename='second.txt', raw_text=case['input']['resume_text'], structured_data={'candidate_name':'Second'}),
                    JobDescription(id=1, user_id=1, title='API Engineer', raw_text=case['input']['job_text'], structured_data=deepcopy(JOB_PROFILE))])
        db.commit()
    def accept(kind, **inputs):
        with SessionLocal() as db:
            rid = agent_runs.create_run(db, 1, RunCreate(kind=kind, requestId=str(uuid4()), **inputs)).id
            accepted_runs.append(rid)
            return rid
    def run(run_id, *, expected_status='succeeded'):
        with SessionLocal() as db:
            epoch = agent_runs.claim_run(db, run_id)
            current = db.get(AgentRun, run_id)
            kind = current.kind
            if recorder is not None:
                recorder.business_run_id, recorder.attempt, recorder.epoch = run_id, current.attempt, epoch
        handler = {'document_parse': document_tasks.run_document_parse, 'match_analysis': analysis_tasks.run_match_analysis,
                   'question_generation': analysis_tasks.run_question_generation, 'answer_followup': analysis_tasks.run_answer_followup}[kind]
        handler(run_id, epoch)
        if recorder is not None and recorder.summary()['stop_reason']:
            raise CaseStopped(recorder.summary()['stop_reason'])
        with SessionLocal() as db:
            current = db.get(AgentRun, run_id)
            if current.status != expected_status:
                raise CaseStopped(current.error_code or 'unexpected_task_status')
        return epoch
    def result(run_id):
        with SessionLocal() as db:
            return deepcopy(db.get(AgentRun, run_id).result_json)
    def match(resumes=None, *, expected_status='succeeded'):
        rid = accept('match_analysis', jdId=1, resumeIds=resumes or [1]); run(rid, expected_status=expected_status)
        return rid
    def questions(match_id):
        with SessionLocal() as db:
            inputs = db.get(AgentRun, match_id).input_json
            return accept('question_generation', analysisJobId=inputs['analysisJobId'], candidateId=inputs['candidateIds'][0], questionCount=1)
    def followup():
        return accept('answer_followup', followup={'question':'How?', 'answer':'Validated API fields in a test environment.'})
    async def isolated_upload(file):
        return await store_upload(file, storage_root=originals)
    def request_db():
        with SessionLocal() as db:
            yield db
    app = FastAPI()
    app.include_router(documents.router)
    # Durable SQL/replay scenarios isolate admission, just as they isolate the
    # external model. Real multi-process Redis limits have their own T20 suite.
    app.state.rate_limiter = SimpleNamespace(allow_request=AsyncMock(return_value=(True, 0)))
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    app.dependency_overrides[get_db] = request_db
    coverage, subject_runs, execution_error = {}, [], None
    with ExitStack() as stack:
        if recorder is not None:
            stack.callback(model.close)
        stack.enter_context(patch.object(analysis_tasks, 'AgentHarness', model.harness))
        stack.enter_context(patch.object(document_tasks, 'AgentHarness', model.harness))
        stack.enter_context(patch.object(analysis_tasks, 'get_rag_store', lambda: rag))
        stack.enter_context(patch.object(document_tasks, 'get_rag_store', lambda: rag))
        stack.enter_context(patch.object(documents, 'store_upload', isolated_upload))
        stack.enter_context(patch.object(background_tasks, 'publish_run', lambda rid: False))
        client = stack.enter_context(TestClient(app))
        def upload(key='upload'):
            response = client.post('/api/documents', data={'document_type':'resume','task_id':key},
                files={'files':('synthetic-resume.txt', case['input']['resume_text'].encode())}, headers={'Prefer':'respond-async'})
            if response.status_code != 202:
                raise RuntimeError(f'Upload acceptance failed (HTTP {response.status_code})')
            rid = response.json()['taskId']
            if rid not in accepted_runs:
                accepted_runs.append(rid)
            return rid
        try:
            if case['id'] == 'parse-upload-stable-identity':
                rid = upload(); same = upload()
                coverage.update(accepted_id=rid, duplicate_accepted_id=same)
                epoch = run(rid); original = result(rid); before = len(model.calls)
                document_tasks.run_document_parse(rid, epoch)
                coverage.update(original_result=original, replay_result=result(rid), calls_on_replay=len(model.calls)-before,
                                original_file_count=len(list(originals.iterdir())))
                subject_runs = [rid]
            elif case['id'] == 'parse-reparse-saved-job':
                upload_id = upload(); run(upload_id); uploaded = result(upload_id)
                document_id = uploaded['documents'][0]['id']
                with SessionLocal() as db:
                    stamp = db.get(Resume, int(document_id.split(':')[1])).updated_at
                if mode == 'stub':
                    model.label = 'Reparsed value'
                file_id = accept('document_parse', documentId=document_id, parseMode='reparse'); run(file_id)
                text_id = accept('document_parse', documentId='jd:1', parseMode='saved_job'); run(text_id)
                with SessionLocal() as db:
                    coverage['timestamp_advanced'] = db.get(Resume, int(document_id.split(':')[1])).updated_at > stamp
                coverage.update(upload_result=uploaded, immutable_upload=result(upload_id), file_result=result(file_id), text_result=result(text_id))
                subject_runs = [upload_id, file_id, text_id]
            elif case['id'] == 'match-partial-candidate-replay':
                def fail_once():
                    if model.candidate_calls()['Second'] == 1:
                        raise agent_runs.RunError(503, 'eval_interrupted_candidate', 'Synthetic interrupted candidate')
                model.hooks['Second'] = fail_once
                rid = match([1,2], expected_status='failed')
                with SessionLocal() as db:
                    coverage['partial_results'] = db.query(MatchResult).count()
                    agent_runs.retry_run(db, 1, rid)
                epoch = run(rid)
                analysis_tasks.run_match_analysis(rid, epoch)
                coverage['candidate_calls'] = model.candidate_calls()
                subject_runs = [rid]
            elif case['id'] == 'question-result-replay':
                matched = match(); first = questions(matched); first_epoch = run(first)
                original = result(first)
                if mode == 'stub':
                    model.label = 'New explicit question'
                second = questions(matched); run(second); before = len(model.calls)
                replayed = analysis_tasks.run_question_generation(first, first_epoch)
                with SessionLocal() as db:
                    current = db.query(InterviewQuestionSet).one().questions[0]['question']
                coverage.update(original_question=original['formal_questions'][0]['question'],
                    current_question=current, second_question=result(second)['formal_questions'][0]['question'], replayed_question=replayed['formal_questions'][0]['question'], calls_on_replay=len(model.calls)-before)
                subject_runs = [first,second]
            elif case['id'] == 'followup-result-replay':
                rid = followup(); epoch = run(rid); original = result(rid); before = len(model.calls)
                if mode == 'stub':
                    model.label = 'Must not overwrite'
                replayed = analysis_tasks.run_answer_followup(rid, epoch)
                coverage.update(original_result=original,replay_result=replayed,calls_on_replay=len(model.calls)-before)
                subject_runs = [rid]
            elif case['id'] == 'cancel-recovery':
                from backend.worker_tasks import execution_lock
                queued = followup(); stale = followup()
                with SessionLocal() as db:
                    agent_runs.cancel_run(db,1,queued)
                    coverage['queued_claim_blocked'] = agent_runs.claim_run(db,queued) is None
                    agent_runs.claim_run(db,stale); agent_runs.cancel_run(db,1,stale)
                    db.get(AgentRun,stale).heartbeat_at = utcnow() - timedelta(seconds=100); db.commit()
                    with execution_lock() as acquired:
                        if not acquired:
                            raise RuntimeError('Evaluation execution lock unavailable')
                        agent_runs.recover_stale_runs(db)
                matched = match(); question_id = questions(matched)
                def cancel_question():
                    with SessionLocal() as db:
                        agent_runs.cancel_run(db,1,question_id)
                    coverage['calls_at_cancel'] = len(model.calls)
                model.hooks['plan_question_blueprint'] = cancel_question
                run(question_id, expected_status='cancelled')
                coverage['model_calls_after_cancel'] = len(model.calls) - coverage['calls_at_cancel']
                subject_runs = [queued,stale,question_id]
            elif case['id'] == 'source-deleted-or-reassigned':
                coverage['mutations'] = []
                for mutation in ('delete_jd','reassign_resume'):
                    def change_source():
                        with SessionLocal() as db:
                            if mutation == 'delete_jd':
                                db.delete(db.get(JobDescription,1))
                            else:
                                db.get(Resume,1).user_id=2
                            db.commit()
                        coverage['mutations'].append(mutation)
                    model.hooks['First'] = change_source
                    rid = match(expected_status='failed'); subject_runs.append(rid)
                    if mutation not in coverage['mutations']:
                        raise CaseStopped('source_fault_not_exercised')
                    if mutation == 'delete_jd':
                        with SessionLocal() as db:
                            db.add(JobDescription(id=1,user_id=1,title='API Engineer',raw_text=case['input']['job_text'],structured_data=deepcopy(JOB_PROFILE)))
                            db.commit()
            elif case['id'] == 'business-write-rollback':
                matched = match()
                question_id = questions(matched)
                parse_id = upload()
                match_id = accept('match_analysis',jdId=1,resumeIds=[2])
                followup_id = followup()
                coverage['fault_kinds'] = []
                def reject_artifact(connection,cursor,statement,parameters,context,many):
                    if statement.startswith('INSERT INTO agent_run_events') and 'artifact.created' in str(parameters):
                        coverage['fault_kinds'].append(fault_kind)
                        raise RuntimeError('Synthetic final artifact transaction failure')
                event.listen(engine,'before_cursor_execute',reject_artifact)
                try:
                    for fault_kind, rid in zip(
                            ('document_parse','match_analysis','question_generation','answer_followup'),
                            (parse_id,match_id,question_id,followup_id)):
                        run(rid, expected_status='failed')
                finally:
                    event.remove(engine,'before_cursor_execute',reject_artifact)
                subject_runs = [parse_id,match_id,question_id,followup_id]
            else:
                raise ValueError('Unsupported durable scenario')
        except CaseStopped as error:
            execution_error = str(error)
            subject_runs = subject_runs or accepted_runs
    def row(item):
        return {column.name:json_value(getattr(item,column.name)) for column in item.__table__.columns}
    with SessionLocal() as db:
        models = [('runs',AgentRun),('sessions',AgentSession),('operations',ToolOperation),('events',AgentRunEvent),
                  ('resumes',Resume),('jobs',JobDescription),('analysis_jobs',AnalysisJob),('candidates',AnalysisCandidate),
                  ('match_results',MatchResult),('question_sets',InterviewQuestionSet),('followup_sets',FollowUpQuestionSet),
                  ('embedding_chunks',DocumentEmbeddingChunk)]
        snapshot = {name:[row(item) for item in db.scalars(select(entity))] for name,entity in models}
    output = {'subject_run_ids':subject_runs,'coverage':coverage,'model_calls':model.calls,'model':request['config']['model'] if mode == 'live' else 'synthetic-durable-task-fixture', 'mode':mode,
              'database':'isolated SQLite','source_directory':str(originals),
              'admission':'controlled fixture; real Redis limiting is verified separately'}
    if recorder is not None:
        output.update(public_model_output=recorder.outputs, business_calls=model.business_calls,
                      retrieval='deterministic four-dimensional embedding; generation uses live provider boundary')
    verdict = (verify_task(case,output,snapshot) if execution_error is None else {
        'passed':False, 'checks':[{'name':'scenario_execution','passed':False,'reason':execution_error,
                                'evidence_refs':['runs','output.model_calls']}], 'limitations':[]})
    cost = recorder.summary() if recorder is not None else None
    stop = cost['stop_reason'] if cost else None
    detail = dict(case_id=case['id'],category=case['category'],mode=mode,
                  status='incomplete' if stop else 'pass' if verdict['passed'] else 'fail',
                  input=case,output=output,db_snapshot=snapshot,verdict=verdict,semantic=semantic_review(mode))
    if cost is not None:
        detail['cost'] = cost
    if stop or execution_error:
        detail['error_code'] = stop or execution_error
    write_json(Path(request['invocation'])/'cases'/(case['id']+'.json'),detail)
    return detail
