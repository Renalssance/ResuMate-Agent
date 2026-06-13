from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.rag.milvus import MilvusRagStore
from backend.repositories.runs import run_repository
from backend.schemas.workflow import (
    AnalyzeResponse,
    CandidateReport,
    EvidenceSearchRequest,
    EvidenceSearchResponse,
    RunSummary,
)
from backend.services.analysis import AnalysisService

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_run(
    jd_file: UploadFile = File(...),
    resume_files: list[UploadFile] = File(...),
):
    try:
        service = AnalysisService()
        return await service.analyze(jd_file=jd_file, resume_files=resume_files)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{run_id}", response_model=RunSummary)
async def get_run(run_id: str):
    record = run_repository.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="run not found")
    return record.summary()


@router.get("/{run_id}/candidates/{candidate_id}", response_model=CandidateReport)
async def get_candidate_report(run_id: str, candidate_id: str):
    record = run_repository.get(run_id)
    if record is None or candidate_id not in record.reports:
        raise HTTPException(status_code=404, detail="candidate report not found")
    return record.reports[candidate_id]


@router.post("/{run_id}/candidates/{candidate_id}/evidence/search", response_model=EvidenceSearchResponse)
async def search_candidate_evidence(run_id: str, candidate_id: str, request: EvidenceSearchRequest):
    record = run_repository.get(run_id)
    if record is None or candidate_id not in record.reports:
        raise HTTPException(status_code=404, detail="candidate report not found")
    try:
        results = MilvusRagStore().search_resume_evidence(
            run_id=run_id,
            candidate_id=candidate_id,
            query=request.query,
            top_k=request.top_k,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return EvidenceSearchResponse(run_id=run_id, candidate_id=candidate_id, results=results)
