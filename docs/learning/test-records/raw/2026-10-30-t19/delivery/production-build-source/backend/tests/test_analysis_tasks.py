"""Real SQL task units with deterministic model responses, on SQLite and MySQL."""
from collections import Counter
from importlib.util import find_spec
from types import SimpleNamespace

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import sessionmaker

from backend.db.agent_models import AgentRun, AgentRunEvent, ToolOperation
from backend.db.models import AnalysisCandidate, AnalysisJob, InterviewQuestionSet, JobDescription, MatchResult, Resume
from backend.schemas.agent_runs import RunCreate, RunStatus
from backend.rag.mysql import MySQLRagStore
from backend.schemas.workflow import (AmbiguityFollowupSet, FollowUpAnalysisResponse, InterviewQuestion,
    JobProfile, MatchEvaluation, QuestionBatch, QuestionBlueprint, ResumeProfile)
from backend.services import agent_runs
from backend.tests.career_fixtures import career_db, career_engine


@pytest.fixture
def runtime(career_db, career_engine, monkeypatch):
    assert find_spec('backend.services.analysis_tasks') is not None, 'durable analysis worker is missing'
    from backend.services import analysis_tasks
    monkeypatch.setattr(analysis_tasks, 'SessionLocal', sessionmaker(career_engine, expire_on_commit=False, autoflush=False))
    profile = JobProfile(job_title='Engineer', summary='Build APIs', criteria=[dict(
        criterion_id='api', name='API', description='Build APIs', importance='must', weight=100, evidence_query='API')])
    career_db.get(JobDescription, 1).structured_data = profile.model_dump(mode='json')
    career_db.get(Resume, 1).structured_data = ResumeProfile(candidate_name='First').model_dump(mode='json')
    career_db.add(Resume(id=2, user_id=1, filename='second.txt', structured_data=ResumeProfile(candidate_name='Second').model_dump(mode='json')))
    career_db.commit()
    calls = Counter()
    hooks = {}
    label = ['Original']
    question = lambda text: InterviewQuestion(question=text, question_type='gap_validation', difficulty='medium',
        assessment_points=['API'], related_criteria=['api'], reference_answer_direction='Explain', scoring_rubric=['Concrete'], suggested_followups=['Why?'])
    class Harness:
        def __init__(self, *, user_id, guard=None, progress_callback=None):
            self.guard = guard
        def run_schema(self, *, task, variables, **kwargs):
            self.guard()
            key = variables.get('resume_profile_json', {}).get('candidate_name', task)
            calls[key] += 1
            if key in hooks:
                hooks[key]()
            if task == 'evaluate_match':
                return MatchEvaluation(evaluations=[dict(criterion_id='api', name='API', weight=100, score=0,
                    status='no_evidence', reason='No citation', missing_evidence=['API'], evidence_chunk_ids=[], risk='')])
            if task == 'plan_question_blueprint':
                return QuestionBlueprint(formal_questions=[dict(question_id='q1', question_type='gap_validation',
                    primary_criterion_id='api', objective='API', difficulty='medium')])
            if task == 'generate_question_batch':
                return QuestionBatch(formal_questions=[question(label[0])])
            if task == 'generate_ambiguity_followups':
                return AmbiguityFollowupSet(ambiguity_followups=[question(f'Clarify {i}') for i in range(3)])
            if task == 'followup.analyze_answer':
                return FollowUpAnalysisResponse(follow_up=label[0], reason='Need evidence', current_ability='Pending', next_suggestion='Clarify')
            raise AssertionError(task)
    monkeypatch.setattr(analysis_tasks, 'AgentHarness', Harness)
    monkeypatch.setattr(analysis_tasks, 'get_rag_store', lambda: SimpleNamespace(search_resume_evidence=lambda **kwargs: []))
    return SimpleNamespace(module=analysis_tasks, calls=calls, hooks=hooks, label=label,
                           factory=sessionmaker(career_engine, expire_on_commit=False))


def start(db, request):
    run_id = agent_runs.create_run(db, 1, RunCreate(**request)).id
    epoch = agent_runs.claim_run(db, run_id)
    db.close()
    return run_id, epoch


def run_match(db, runtime, request_id='match', resumes=None):
    rid, epoch = start(db, dict(kind='match_analysis', jdId=1, resumeIds=resumes or [1], requestId=request_id))
    runtime.module.run_match_analysis(rid, epoch)
    return rid, epoch


def test_matching_resumes_only_unfinished_candidates_in_fixed_group(career_db, runtime):
    def fail_once():
        if runtime.calls['Second'] == 1:
            raise RuntimeError('model unavailable')
    runtime.hooks['Second'] = fail_once
    run_id, _ = run_match(career_db, runtime, resumes=[1, 2])
    with runtime.factory() as db:
        run = db.get(AgentRun, run_id)
        assert run.status == RunStatus.FAILED
        job_id = run.input_json['analysisJobId']
        assert db.query(MatchResult).count() == 1
        assert db.query(ToolOperation).count() == 1
        agent_runs.retry_run(db, 1, run_id)
        epoch = agent_runs.claim_run(db, run_id)
    runtime.module.run_match_analysis(run_id, epoch)
    runtime.module.run_match_analysis(run_id, epoch)
    with runtime.factory() as db:
        run = db.get(AgentRun, run_id)
        assert run.status == RunStatus.SUCCEEDED
        assert run.result_json['run_id'] == job_id
        assert run.result_json['taskId'] == run_id
        assert len(run.result_json['candidates']) == 2
        assert db.query(AnalysisJob).count() == 1
        assert db.query(AnalysisCandidate).count() == 2
        assert db.query(ToolOperation).count() == 2
        assert db.query(AgentRunEvent).filter_by(type='artifact.created').count() == 2
    assert runtime.calls == {'First': 1, 'Second': 2}



def test_matching_stops_before_next_embedding_after_cancel(career_db, runtime, monkeypatch):
    job = career_db.get(JobDescription, 1)
    criterion = job.structured_data['criteria'][0]
    job.structured_data = {**job.structured_data, 'criteria': [
        {**criterion, 'weight': 50},
        {**criterion, 'criterion_id': 'second', 'name': 'Second', 'weight': 50, 'evidence_query': 'Second query'},
    ]}
    career_db.commit()
    queries = []

    class Embeddings:
        contract = {'provider': 'test', 'model': 'cancel-test'}

        def embed(self, query):
            queries.append(query)
            if len(queries) == 1:
                with runtime.factory() as db:
                    run = db.query(AgentRun).filter_by(kind='match_analysis').one()
                    agent_runs.cancel_run(db, 1, run.id)
            return [1.0, 0.0]

    rag = MySQLRagStore(session_factory=runtime.factory, embedding_client=Embeddings())
    monkeypatch.setattr(runtime.module, 'get_rag_store', lambda: rag)
    run_id, _ = run_match(career_db, runtime)
    with runtime.factory() as db:
        run = db.get(AgentRun, run_id)
        assert run.status == RunStatus.CANCELLED and run.result_json is None
        assert db.query(MatchResult).count() == 0
    assert queries == ['API']
    assert not runtime.calls


def test_question_replay_returns_its_original_result_after_new_generation(career_db, runtime):
    match_id, _ = run_match(career_db, runtime)
    with runtime.factory() as db:
        match = db.get(AgentRun, match_id)
        job_id, candidate_id = match.input_json['analysisJobId'], match.input_json['candidateIds'][0]
        request = dict(kind='question_generation', analysisJobId=job_id, candidateId=candidate_id, questionCount=1)
        first, first_epoch = start(db, {**request, 'requestId': 'questions-first'})
    runtime.module.run_question_generation(first, first_epoch)
    runtime.label[0] = 'New request'
    with runtime.factory() as db:
        second, second_epoch = start(db, {**request, 'requestId': 'questions-second'})
    runtime.module.run_question_generation(second, second_epoch)
    runtime.module.run_question_generation(first, first_epoch)
    with runtime.factory() as db:
        assert db.get(AgentRun, first).result_json['formal_questions'][0]['question'] == 'Original'
        assert db.get(AgentRun, second).result_json['formal_questions'][0]['question'] == 'New request'
        assert db.query(InterviewQuestionSet).one().questions[0]['question'] == 'New request'
        assert db.query(ToolOperation).filter_by(operation_key='questions').count() == 2
    assert runtime.calls['plan_question_blueprint'] == 2


def test_followup_result_replay_does_not_call_model_again(career_db, runtime):
    run_id, epoch = start(career_db, dict(kind='answer_followup', followup={'question':'Why?', 'answer':'API'}, requestId='followup'))
    runtime.module.run_answer_followup(run_id, epoch)
    runtime.label[0] = 'Would overwrite'
    runtime.module.run_answer_followup(run_id, epoch)
    with runtime.factory() as db:
        assert db.get(AgentRun, run_id).result_json['follow_up'] == 'Original'
        assert db.query(ToolOperation).filter_by(operation_key='answer_followup').count() == 1
        assert db.query(AgentRunEvent).filter_by(type='artifact.created').count() == 1
    assert runtime.calls['followup.analyze_answer'] == 1


@pytest.mark.parametrize('mutation', ['cancel', 'delete_resume', 'delete_jd', 'reassign_resume', 'delete_job'])
def test_match_rechecks_sources_after_model_before_business_write(career_db, runtime, mutation):
    run_id, epoch = start(career_db, dict(kind='match_analysis', jdId=1, resumeIds=[1], requestId='mutation'))
    def change_source():
        with runtime.factory() as db:
            if mutation == 'cancel':
                agent_runs.cancel_run(db, 1, run_id)
            elif mutation == 'delete_resume':
                db.delete(db.get(Resume, 1))
            elif mutation == 'delete_jd':
                db.delete(db.get(JobDescription, 1))
            elif mutation == 'delete_job':
                db.delete(db.get(AnalysisJob, db.get(AgentRun, run_id).input_json['analysisJobId']))
            else:
                db.get(Resume, 1).user_id = 2
            db.commit()
    runtime.hooks['First'] = change_source
    runtime.module.run_match_analysis(run_id, epoch)
    with runtime.factory() as db:
        assert db.get(AgentRun, run_id).status == (RunStatus.CANCELLED if mutation == 'cancel' else RunStatus.FAILED)
        assert db.query(MatchResult).count() == 0
        assert db.query(ToolOperation).count() == 0
        assert db.query(AgentRunEvent).filter_by(type='artifact.created').count() == 0


def test_match_business_report_rolls_back_when_artifact_event_cannot_save(career_db, career_engine, runtime):
    def reject_event(connection, cursor, statement, parameters, context, many):
        if statement.startswith('INSERT INTO agent_run_events') and 'artifact.created' in str(parameters):
            raise RuntimeError('artifact storage failed')
    event.listen(career_engine, 'before_cursor_execute', reject_event)
    try:
        run_id, _ = run_match(career_db, runtime)
    finally:
        event.remove(career_engine, 'before_cursor_execute', reject_event)
    with runtime.factory() as db:
        assert db.get(AgentRun, run_id).status == RunStatus.FAILED
        assert db.query(MatchResult).count() == 0
        assert db.query(ToolOperation).count() == 0
        assert db.query(AnalysisCandidate).one().status != 'completed'


def test_completed_candidates_need_no_model_setup_when_only_terminal_commit_remains(career_db, runtime, monkeypatch):
    real_finish = runtime.module.agent_runs.finish_run
    def stop_before_terminal(db, run_id, epoch, status, **kwargs):
        if status == RunStatus.SUCCEEDED:
            raise RuntimeError('worker lost before terminal')
        return real_finish(db, run_id, epoch, status, **kwargs)
    monkeypatch.setattr(runtime.module.agent_runs, 'finish_run', stop_before_terminal)
    run_id, _ = run_match(career_db, runtime)
    monkeypatch.setattr(runtime.module.agent_runs, 'finish_run', real_finish)
    def no_model_needed(**kwargs):
        raise AssertionError('all candidate results are already saved')
    monkeypatch.setattr(runtime.module, 'AgentHarness', no_model_needed)
    with runtime.factory() as db:
        assert db.query(ToolOperation).count() == 1
        agent_runs.retry_run(db, 1, run_id)
        epoch = agent_runs.claim_run(db, run_id)
    runtime.module.run_match_analysis(run_id, epoch)
    with runtime.factory() as db:
        assert db.get(AgentRun, run_id).status == RunStatus.SUCCEEDED
        assert db.query(MatchResult).count() == 1
    assert runtime.calls['First'] == 1


@pytest.mark.parametrize('cancel_at', ['plan_question_blueprint', 'generate_ambiguity_followups'])
def test_question_cancel_stops_next_call_or_final_write(career_db, runtime, cancel_at):
    match_id, _ = run_match(career_db, runtime)
    with runtime.factory() as db:
        match = db.get(AgentRun, match_id)
        run_id, epoch = start(db, dict(kind='question_generation', analysisJobId=match.input_json['analysisJobId'],
            candidateId=match.input_json['candidateIds'][0], questionCount=1, requestId='questions-cancel'))
    def cancel():
        with runtime.factory() as db:
            agent_runs.cancel_run(db, 1, run_id)
    runtime.hooks[cancel_at] = cancel
    runtime.module.run_question_generation(run_id, epoch)
    with runtime.factory() as db:
        run = db.get(AgentRun, run_id)
        assert run.status == RunStatus.CANCELLED and run.result_json is None
        assert db.query(InterviewQuestionSet).count() == 0
        assert db.query(ToolOperation).filter_by(run_id=run_id).count() == 0
    assert runtime.calls['generate_question_batch'] == (0 if cancel_at == 'plan_question_blueprint' else 1)


def test_question_validation_failure_is_durable_without_saved_questions(career_db, runtime, monkeypatch):
    match_id, _ = run_match(career_db, runtime)
    with runtime.factory() as db:
        match = db.get(AgentRun, match_id)
        run_id, epoch = start(db, dict(kind='question_generation', analysisJobId=match.input_json['analysisJobId'],
            candidateId=match.input_json['candidateIds'][0], questionCount=1, requestId='questions-invalid'))
    def invalid(self, **kwargs):
        raise ValueError('evidence chunk overused: e1')
    monkeypatch.setattr(runtime.module.AnalysisService, '_build_question_set_from_split', invalid)
    runtime.module.run_question_generation(run_id, epoch)
    with runtime.factory() as db:
        run = db.get(AgentRun, run_id)
        assert run.status == RunStatus.FAILED and run.error_code == 'question_generation_failed'
        assert run.result_json is None
        assert db.query(InterviewQuestionSet).count() == 0
        assert db.query(ToolOperation).filter_by(run_id=run_id).count() == 0


@pytest.mark.parametrize('kind', ['question_generation', 'answer_followup'])
def test_final_result_and_business_rows_rollback_with_artifact_event(career_db, career_engine, runtime, kind):
    if kind == 'question_generation':
        match_id, _ = run_match(career_db, runtime)
        with runtime.factory() as db:
            match = db.get(AgentRun, match_id)
            run_id, epoch = start(db, dict(kind=kind, analysisJobId=match.input_json['analysisJobId'],
                candidateId=match.input_json['candidateIds'][0], questionCount=1, requestId='atomic-question'))
        handler = runtime.module.run_question_generation
    else:
        run_id, epoch = start(career_db, dict(kind=kind, followup={'question':'Why?', 'answer':'API'}, requestId='atomic-followup'))
        handler = runtime.module.run_answer_followup
    def reject_event(connection, cursor, statement, parameters, context, many):
        if statement.startswith('INSERT INTO agent_run_events') and 'artifact.created' in str(parameters):
            raise RuntimeError('artifact storage failed')
    event.listen(career_engine, 'before_cursor_execute', reject_event)
    try:
        handler(run_id, epoch)
    finally:
        event.remove(career_engine, 'before_cursor_execute', reject_event)
    with runtime.factory() as db:
        run = db.get(AgentRun, run_id)
        assert run.status == RunStatus.FAILED and run.result_json is None
        assert db.query(InterviewQuestionSet).count() == 0
        assert db.query(ToolOperation).filter_by(run_id=run_id).count() == 0
        assert db.query(AgentRunEvent).filter_by(run_id=run_id, type='artifact.created').count() == 0
        if kind == 'question_generation':
            assert db.query(MatchResult).one().report_json['formal_questions'] == []
