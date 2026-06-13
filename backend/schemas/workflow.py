from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


Importance = Literal["must", "important", "bonus"]
MatchStatus = Literal["strong_match", "match", "partial_match", "no_evidence", "conflict"]
Recommendation = Literal["strong_recommend", "recommend", "hold", "reject"]
QuestionType = Literal[
    "resume_experience",
    "jd_core_capability",
    "scenario_design",
    "gap_validation",
    "behavior_review",
]


class Criterion(BaseModel):
    criterion_id: str
    name: str
    description: str
    importance: Importance
    weight: float = Field(ge=0, le=100)
    evidence_query: str


class JobProfile(BaseModel):
    job_title: str
    summary: str
    responsibilities: list[str] = Field(default_factory=list)
    criteria: list[Criterion] = Field(min_length=1)
    interview_focus: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _weights_sum_to_100(self) -> "JobProfile":
        total = sum(item.weight for item in self.criteria)
        if round(total, 2) != 100:
            raise ValueError("JobProfile criteria weights must sum to 100")
        return self


class SourceRef(BaseModel):
    page_number: int = Field(ge=0)
    section: str
    text: str
    chunk_id: str


class EducationItem(BaseModel):
    school: str = ""
    degree: str = ""
    major: str = ""
    years: str = ""
    source_refs: list[SourceRef] = Field(default_factory=list)


class WorkItem(BaseModel):
    company: str = ""
    title: str = ""
    duration: str = ""
    description: str = ""
    source_refs: list[SourceRef] = Field(default_factory=list)


class ProjectItem(BaseModel):
    name: str = ""
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)


class ResumeProfile(BaseModel):
    candidate_name: str
    contact: dict[str, str] = Field(default_factory=dict)
    education: list[EducationItem] = Field(default_factory=list)
    work_experience: list[WorkItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)


class EvidenceChunk(BaseModel):
    chunk_id: str
    filename: str
    page_number: int
    section: str
    text: str
    score: float = 0


class CriterionEvaluation(BaseModel):
    criterion_id: str
    name: str
    weight: float = Field(ge=0, le=100)
    score: int = Field(ge=0, le=5)
    status: MatchStatus
    reason: str
    evidence: list[EvidenceChunk] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    risk: str = ""


class MatchEvaluation(BaseModel):
    evaluations: list[CriterionEvaluation]

    @model_validator(mode="after")
    def _positive_scores_need_evidence(self) -> "MatchEvaluation":
        for item in self.evaluations:
            if item.score > 0 and not item.evidence:
                raise ValueError(f"score > 0 requires at least one evidence chunk: {item.criterion_id}")
        return self


class InterviewQuestion(BaseModel):
    question: str
    question_type: QuestionType
    difficulty: Literal["easy", "medium", "hard"]
    assessment_points: list[str]
    related_criteria: list[str]
    evidence: list[EvidenceChunk]
    reference_answer_direction: str
    scoring_rubric: list[str]
    suggested_followups: list[str]


class QuestionSet(BaseModel):
    formal_questions: list[InterviewQuestion] = Field(min_length=10, max_length=10)
    ambiguity_followups: list[InterviewQuestion] = Field(min_length=3, max_length=5)

    @model_validator(mode="after")
    def _formal_distribution(self) -> "QuestionSet":
        expected = {
            "resume_experience": 3,
            "jd_core_capability": 2,
            "scenario_design": 2,
            "gap_validation": 2,
            "behavior_review": 1,
        }
        actual = {key: 0 for key in expected}
        for question in self.formal_questions:
            actual[question.question_type] = actual.get(question.question_type, 0) + 1
        if actual != expected:
            raise ValueError(f"formal question distribution must be {expected}, got {actual}")
        return self


class CandidateReport(BaseModel):
    run_id: str
    candidate_id: str
    candidate_name: str
    filename: str
    job_profile: JobProfile
    resume_profile: ResumeProfile
    evaluations: list[CriterionEvaluation]
    total_score: float = Field(ge=0, le=100)
    recommendation: Recommendation
    top_strengths: list[str] = Field(default_factory=list)
    summary: str
    formal_questions: list[InterviewQuestion] = Field(min_length=10, max_length=10)
    ambiguity_followups: list[InterviewQuestion] = Field(min_length=3, max_length=5)


class CandidateSummary(BaseModel):
    candidate_id: str
    candidate_name: str
    filename: str
    total_score: float
    recommendation: Recommendation
    top_strengths: list[str] = Field(default_factory=list)


class RunSummary(BaseModel):
    run_id: str
    job_title: str
    candidates: list[CandidateSummary]


class AnalyzeResponse(RunSummary):
    pass


class EvidenceSearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=4, ge=1, le=20)


class EvidenceSearchResponse(BaseModel):
    run_id: str
    candidate_id: str
    results: list[EvidenceChunk]


DocumentType = Literal["jd", "resume"]


class DocumentParseResult(BaseModel):
    id: str
    type: DocumentType
    filename: str
    size: int
    raw_text: str
    parsed_content: dict[str, Any]
    vectorized: bool = True
    local_stored: bool = True


class DocumentParseResponse(BaseModel):
    documents: list[DocumentParseResult]


class FollowUpAnalysisRequest(BaseModel):
    question: str
    answer: str
    jd_context: dict[str, Any] = Field(default_factory=dict)
    resume_context: dict[str, Any] = Field(default_factory=dict)
    question_context: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, Any]] = Field(default_factory=list)


class FollowUpAnalysisResponse(BaseModel):
    follow_up: str
    reason: str
    evidence: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    current_ability: str
    next_suggestion: str
