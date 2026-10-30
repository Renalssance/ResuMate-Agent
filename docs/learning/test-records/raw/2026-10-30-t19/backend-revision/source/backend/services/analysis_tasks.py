"""Durable candidate, interview-question and answer-followup business units."""
from copy import deepcopy
import logging

from sqlalchemy import select

from backend.agents.harness import AgentHarness
from backend.db.agent_models import AgentRun, ToolOperation
from backend.db.database import SessionLocal
from backend.db.models import AnalysisCandidate, AnalysisJob
from backend.graph.candidate_workflow import CandidateAnalysisGraph
from backend.rag import get_rag_store
from backend.repositories.runs import SqlAlchemyRunRepository
from backend.schemas.agent_runs import RunStatus
from backend.schemas.workflow import AnalyzeResponse, CandidateReport, FollowUpAnalysisRequest, FollowUpAnalysisResponse
from backend.services import agent_runs
from backend.services.agent_runs import RunError
from backend.services.analysis import AnalysisService
from backend.services.progress import TaskProgress, append_progress
from backend.services.run_events import append_event

logger = logging.getLogger(__name__)


def _guard(db, run_id: str, epoch: int) -> AgentRun:
    agent_runs.guard_execution(db, run_id, epoch)
    run = db.get(AgentRun, run_id, populate_existing=True)
    agent_runs.require_task_sources(db, run)
    return run


def _model_guard(run_id: str, epoch: int):
    def guard():
        with SessionLocal() as db:
            _guard(db, run_id, epoch)
            db.commit()
    return guard


def _successful_operation(db, run_id: str, key: str) -> ToolOperation | None:
    return db.scalar(select(ToolOperation).where(
        ToolOperation.run_id == run_id, ToolOperation.operation_key == key,
        ToolOperation.status == 'succeeded'))


def _save_operation(db, run_id: str, key: str, kind: str, result_ref: str) -> None:
    db.add(ToolOperation(run_id=run_id, operation_key=key, tool_name=kind,
                         status='succeeded', result_ref=result_ref))
    db.flush()
    append_event(db, run_id, 'artifact.created', {'artifact_id': result_ref, 'kind': kind})


def _finished_result(run_id: str):
    with SessionLocal() as db:
        run = db.get(AgentRun, run_id)
        if run and run.status == RunStatus.SUCCEEDED:
            return deepcopy(run.result_json)
    return None


def _fail(run_id: str, epoch: int, error: Exception, default_code: str) -> None:
    code = error.code if isinstance(error, RunError) else default_code
    with SessionLocal() as db:
        agent_runs.finish_run(db, run_id, epoch, RunStatus.FAILED, error_code=code)
    logger.warning('Analysis task %s stopped (%s)', run_id, code)


def run_match_analysis(run_id: str, epoch: int):
    saved = _finished_result(run_id)
    if saved is not None:
        return saved
    try:
        with SessionLocal() as db:
            run = _guard(db, run_id, epoch)
            user_id, job_id = run.user_id, run.input_json['analysisJobId']
            candidate_ids = list(run.input_json['candidateIds'])
            db.commit()
        progress = TaskProgress(run_id, epoch, SessionLocal)
        graph = None
        for index, candidate_id in enumerate(candidate_ids):
            key = f'match:{candidate_id}'
            with SessionLocal() as db:
                _guard(db, run_id, epoch)
                job = db.get(AnalysisJob, job_id)
                candidate = db.get(AnalysisCandidate, candidate_id)
                if _successful_operation(db, run_id, key) and candidate.match_result:
                    db.commit()
                    continue
                # Carry values, never live ORM objects or an open SQL transaction, into the graph.
                state = {'user_id': user_id, 'run_id': job_id, 'candidate_id': candidate_id,
                         'jd_document_id': job.jd_id, 'resume_document_id': candidate.resume_id,
                         'filename': candidate.resume.filename, 'job_data': deepcopy(job.jd.structured_data),
                         'resume_data': deepcopy(candidate.resume.structured_data), 'task_id': run_id}
                db.commit()
            if graph is None:
                harness = AgentHarness(user_id=user_id, guard=_model_guard(run_id, epoch), progress_callback=progress.publish)
                graph = CandidateAnalysisGraph(harness=harness, rag_store=get_rag_store(), progress_callback=progress.publish,
                                               guard=harness.guard)
            report = graph.run(state)
            with SessionLocal() as db:
                _guard(db, run_id, epoch)
                job, candidate = db.get(AnalysisJob, job_id), db.get(AnalysisCandidate, candidate_id)
                SqlAlchemyRunRepository(db).save_report(job=job, candidate=candidate, report=report)
                _save_operation(db, run_id, key, 'match_report', f'{job_id}:{candidate_id}')
                append_progress(db, run_id, epoch, stage='save', progress=94, message='Saved candidate report',
                                current=index + 1, total=len(candidate_ids), data={'run_id': job_id, 'candidate_id': candidate_id})
                db.commit()
        with SessionLocal() as db:
            _guard(db, run_id, epoch)
            summary = SqlAlchemyRunRepository(db).get_run(user_id=user_id, run_id=job_id)
            response = AnalyzeResponse(**summary.model_dump(), task_id=run_id).model_dump(mode='json', by_alias=True)
            agent_runs.finish_run(db, run_id, epoch, RunStatus.SUCCEEDED, result_json=response,
                                  output_refs=[{'type': 'match_analysis', 'id': job_id}])
        return response
    except Exception as error:
        _fail(run_id, epoch, error, 'match_analysis_failed')


def run_question_generation(run_id: str, epoch: int):
    saved = _finished_result(run_id)
    if saved is not None:
        return saved
    try:
        with SessionLocal() as db:
            run = _guard(db, run_id, epoch)
            user_id, inputs = run.user_id, deepcopy(run.input_json)
            report = CandidateReport.model_validate(inputs['reportSnapshot'])
            db.commit()
        progress = TaskProgress(run_id, epoch, SessionLocal)
        harness = AgentHarness(user_id=user_id, guard=_model_guard(run_id, epoch), progress_callback=progress.publish)
        questions = AnalysisService(harness=harness, progress_callback=progress.publish).generate_questions(
            user_id=user_id, report=report, task_id=run_id, question_count=inputs['questionCount'])
        with SessionLocal() as db:
            _guard(db, run_id, epoch)
            updated = SqlAlchemyRunRepository(db).save_questions(
                user_id=user_id, run_id=inputs['analysisJobId'], candidate_id=inputs['candidateId'], question_set=questions)
            result = updated.model_dump(mode='json', by_alias=True)
            ref = f"{inputs['analysisJobId']}:{inputs['candidateId']}"
            _save_operation(db, run_id, 'questions', 'interview_questions', ref)
            agent_runs.finish_run(db, run_id, epoch, RunStatus.SUCCEEDED, result_json=result,
                                  output_refs=[{'type': 'interview_questions', 'id': ref}])
        return result
    except Exception as error:
        _fail(run_id, epoch, error, 'question_generation_failed')


def run_answer_followup(run_id: str, epoch: int):
    saved = _finished_result(run_id)
    if saved is not None:
        return saved
    try:
        with SessionLocal() as db:
            run = _guard(db, run_id, epoch)
            user_id = run.user_id
            request = FollowUpAnalysisRequest.model_validate(run.input_json['followup'])
            db.commit()
        progress = TaskProgress(run_id, epoch, SessionLocal)
        harness = AgentHarness(user_id=user_id, guard=_model_guard(run_id, epoch), progress_callback=progress.publish)
        result = harness.run_schema(task='followup.analyze_answer', prompt_name='generate_followup',
                                    schema=FollowUpAnalysisResponse, variables=request.model_dump(mode='json'),
                                    task_id=run_id, progress_stage='analyze_answer', progress=50)
        response = result.model_dump(mode='json', by_alias=True)
        with SessionLocal() as db:
            _guard(db, run_id, epoch)
            _save_operation(db, run_id, 'answer_followup', 'answer_followup', run_id)
            agent_runs.finish_run(db, run_id, epoch, RunStatus.SUCCEEDED, result_json=response,
                                  output_refs=[{'type': 'answer_followup', 'id': run_id}])
        return response
    except Exception as error:
        _fail(run_id, epoch, error, 'answer_followup_failed')
