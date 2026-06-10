from typing import List, Optional

from pydantic import BaseModel, Field


class AnalysisJobCreateRequest(BaseModel):
    title: str = Field(default="", max_length=255)
    jd_id: Optional[int] = None
    summary: str = ""
    config: dict = Field(default_factory=dict)


class AnalysisJobUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    jd_id: Optional[int] = None
    status: Optional[str] = None
    summary: Optional[str] = None
    config: Optional[dict] = None


class AnalysisCandidateAddRequest(BaseModel):
    resume_ids: List[int] = Field(default_factory=list, min_length=1)


class AnalysisCandidateInfo(BaseModel):
    id: int
    resume_id: int
    filename: str
    candidate_name: str = ""
    status: str
    note: str = ""
    created_at: str
    updated_at: str


class AnalysisJobInfo(BaseModel):
    id: int
    title: str
    jd_id: Optional[int] = None
    jd_title: str = ""
    status: str
    summary: str = ""
    candidate_count: int = 0
    created_at: str
    updated_at: str


class AnalysisJobDetailResponse(AnalysisJobInfo):
    config: dict = Field(default_factory=dict)
    candidates: List[AnalysisCandidateInfo] = Field(default_factory=list)


class AnalysisJobCreateResponse(BaseModel):
    id: int
    title: str
    jd_id: Optional[int] = None
    message: str


class AnalysisJobListResponse(BaseModel):
    jobs: List[AnalysisJobInfo]


class AnalysisJobDeleteResponse(BaseModel):
    id: int
    message: str


class AnalysisCandidateAddResponse(BaseModel):
    job_id: int
    added_count: int
    skipped_count: int
    candidates: List[AnalysisCandidateInfo]
    message: str


class AnalysisResumeUploadResult(BaseModel):
    filename: str
    status: str
    resume_id: Optional[int] = None
    candidate_id: Optional[int] = None
    candidate_name: str = ""
    error: str = ""


class AnalysisResumeBatchUploadResponse(BaseModel):
    job_id: int
    uploaded_count: int
    failed_count: int
    added_count: int
    skipped_count: int
    results: List[AnalysisResumeUploadResult]
    candidates: List[AnalysisCandidateInfo]
    message: str


class AnalysisCandidateDeleteResponse(BaseModel):
    id: int
    message: str
