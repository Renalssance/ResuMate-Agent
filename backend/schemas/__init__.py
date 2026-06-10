"""API Schema 定义 — 按业务域分模块，统一导出。"""

from backend.schemas.auth import (
    AuthResponse,
    CurrentUserResponse,
    LoginRequest,
    RegisterRequest,
)
from backend.schemas.chat import (
    ChatRequest,
)
from backend.schemas.resume import (
    ResumeDeleteResponse,
    ResumeDetailResponse,
    ResumeInfo,
    ResumeListResponse,
    ResumeUploadResponse,
)
from backend.schemas.jd import (
    JDCreateRequest,
    JDCreateResponse,
    JDDeleteResponse,
    JDDetailResponse,
    JDInfo,
    JDListResponse,
)
from backend.schemas.analysis import (
    AnalysisCandidateAddRequest,
    AnalysisCandidateAddResponse,
    AnalysisCandidateDeleteResponse,
    AnalysisCandidateInfo,
    AnalysisJobCreateRequest,
    AnalysisJobCreateResponse,
    AnalysisJobDeleteResponse,
    AnalysisJobDetailResponse,
    AnalysisJobInfo,
    AnalysisJobListResponse,
    AnalysisJobUpdateRequest,
    AnalysisResumeBatchUploadResponse,
    AnalysisResumeUploadResult,
)

__all__ = [
    # auth
    "AuthResponse",
    "CurrentUserResponse",
    "LoginRequest",
    "RegisterRequest",
    # chat
    "ChatRequest",
    # resume
    "ResumeDeleteResponse",
    "ResumeDetailResponse",
    "ResumeInfo",
    "ResumeListResponse",
    "ResumeUploadResponse",
    # jd
    "JDCreateRequest",
    "JDCreateResponse",
    "JDDeleteResponse",
    "JDDetailResponse",
    "JDInfo",
    "JDListResponse",
    # analysis
    "AnalysisCandidateAddRequest",
    "AnalysisCandidateAddResponse",
    "AnalysisCandidateDeleteResponse",
    "AnalysisCandidateInfo",
    "AnalysisJobCreateRequest",
    "AnalysisJobCreateResponse",
    "AnalysisJobDeleteResponse",
    "AnalysisJobDetailResponse",
    "AnalysisJobInfo",
    "AnalysisJobListResponse",
    "AnalysisJobUpdateRequest",
    "AnalysisResumeBatchUploadResponse",
    "AnalysisResumeUploadResult",
]
