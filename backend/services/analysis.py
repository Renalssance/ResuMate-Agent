from __future__ import annotations

from uuid import uuid4

from fastapi import UploadFile

from backend.agents.harness import AgentHarness
from backend.graph.candidate_workflow import CandidateAnalysisGraph
from backend.rag.milvus import MilvusRagStore
from backend.repositories.runs import run_repository
from backend.schemas.workflow import AnalyzeResponse, JobProfile
from backend.services.documents import chunk_pages, extract_upload_pages


class AnalysisService:
    def __init__(self, *, harness: AgentHarness | None = None, rag_store: MilvusRagStore | None = None) -> None:
        self.harness = harness or AgentHarness()
        self.rag_store = rag_store or MilvusRagStore()
        self.graph = CandidateAnalysisGraph(harness=self.harness, rag_store=self.rag_store)

    async def analyze(self, *, jd_file: UploadFile, resume_files: list[UploadFile]) -> AnalyzeResponse:
        if not resume_files:
            raise ValueError("At least one resume file is required")
        run_id = f"run_{uuid4().hex[:12]}"
        jd_pages = await extract_upload_pages(jd_file)
        jd_chunks = chunk_pages(
            pages=jd_pages,
            run_id=run_id,
            candidate_id="",
            document_type="jd",
            filename=jd_file.filename or "jd",
        )

        job_profile: JobProfile | None = None
        for index, resume_file in enumerate(resume_files, start=1):
            candidate_id = f"candidate_{index}_{uuid4().hex[:8]}"
            resume_pages = await extract_upload_pages(resume_file)
            resume_chunks = chunk_pages(
                pages=resume_pages,
                run_id=run_id,
                candidate_id=candidate_id,
                document_type="resume",
                filename=resume_file.filename or f"resume_{index}",
            )
            report = self.graph.run(
                {
                    "run_id": run_id,
                    "candidate_id": candidate_id,
                    "filename": resume_file.filename or f"resume_{index}",
                    "jd_chunks": jd_chunks,
                    "resume_chunks": resume_chunks,
                    **({"job_profile": job_profile} if job_profile else {}),
                }
            )
            job_profile = report.job_profile

        if job_profile is None:
            raise RuntimeError("analysis did not produce a job profile")
        record = run_repository.get(run_id)
        if record is None:
            record = run_repository.create(run_id, job_profile.job_title)
        record.job_title = job_profile.job_title
        return AnalyzeResponse(**record.summary().model_dump())
