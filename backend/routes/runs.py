from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.db.models import User
from backend.rag.milvus import MilvusRagStore
from backend.repositories.runs import SqlAlchemyRunRepository
from backend.schemas.workflow import AnalyzeRequest, AnalyzeResponse, CandidateReport, EvidenceSearchRequest, EvidenceSearchResponse, RunSummary
from backend.services.analysis import AnalysisService

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("", response_model=AnalyzeResponse)
async def create_run(request: AnalyzeRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return AnalysisService(db=db).analyze_document_ids(
            user_id=current_user.id,
            jd_document_id=request.jd_document_id,
            resume_document_ids=request.resume_document_ids,
            task_id=request.task_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[RunSummary])
async def list_runs(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return SqlAlchemyRunRepository(db).list_runs(user_id=current_user.id)


@router.get("/{run_id}", response_model=RunSummary)
async def get_run(run_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    result = SqlAlchemyRunRepository(db).get_run(user_id=current_user.id, run_id=run_id)
    if not result:
        raise HTTPException(status_code=404, detail="run not found")
    return result


@router.get("/{run_id}/candidates/{candidate_id}", response_model=CandidateReport)
async def get_candidate_report(run_id: int, candidate_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report = SqlAlchemyRunRepository(db).get_candidate_report(user_id=current_user.id, run_id=run_id, candidate_id=candidate_id)
    if not report:
        raise HTTPException(status_code=404, detail="candidate report not found")
    return report


@router.post("/{run_id}/candidates/{candidate_id}/questions", response_model=CandidateReport)
async def generate_candidate_questions(
    run_id: int,
    candidate_id: int,
    task_id: str = Query(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return AnalysisService(db=db).generate_questions(
            user_id=current_user.id,
            run_id=run_id,
            candidate_id=candidate_id,
            task_id=task_id,
        )
    except ValueError as exc:
        status_code = 404 if str(exc) == "candidate report not found" else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{run_id}/candidates/{candidate_id}")
async def delete_candidate_report(run_id: int, candidate_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not SqlAlchemyRunRepository(db).delete_candidate(user_id=current_user.id, run_id=run_id, candidate_id=candidate_id):
        raise HTTPException(status_code=404, detail="candidate report not found")
    MilvusRagStore().delete_candidate_artifacts(user_id=current_user.id, run_id=run_id, candidate_id=candidate_id)
    return {"candidate_id": candidate_id}


@router.post("/{run_id}/candidates/{candidate_id}/evidence/search", response_model=EvidenceSearchResponse)
async def search_candidate_evidence(run_id: int, candidate_id: int, request: EvidenceSearchRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    repository = SqlAlchemyRunRepository(db)
    if not repository.get_candidate_report(user_id=current_user.id, run_id=run_id, candidate_id=candidate_id):
        raise HTTPException(status_code=404, detail="candidate report not found")
    resume_id = repository.get_candidate_resume_id(
        user_id=current_user.id,
        run_id=run_id,
        candidate_id=candidate_id,
    )
    if resume_id is None:
        raise HTTPException(status_code=404, detail="candidate resume not found")
    results = MilvusRagStore().search_resume_evidence(
        user_id=current_user.id,
        document_id=resume_id,
        query=request.query,
        top_k=request.top_k,
    )
    return EvidenceSearchResponse(run_id=run_id, candidate_id=candidate_id, results=results)
