from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
TaskStatus = Literal["pending", "running", "success", "failed"]
Difficulty = Literal["easy", "medium", "hard"]
SkillEvidenceLevel = Literal["demonstrated", "self_claimed", "course_only", "mentioned"]


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class SseProgressEvent(ApiModel):
    task_id: str = Field(alias="taskId")
    document_id: str | None = Field(default=None, alias="documentId")
    filename: str | None = None
    stage: str
    status: TaskStatus
    progress: int = Field(ge=0, le=100)
    overall_progress: int | None = Field(default=None, ge=0, le=100, alias="overallProgress")
    stage_progress: int | None = Field(default=None, ge=0, le=100, alias="stageProgress")
    current: int | None = None
    total: int | None = None
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


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
        total = round(sum(item.weight for item in self.criteria), 2)
        drift = round(100 - total, 2)
        if total != 100 and abs(drift) <= 0.05 and self.criteria:
            self.criteria[0].weight = round(self.criteria[0].weight + drift, 2)
            total = round(sum(item.weight for item in self.criteria), 2)
        if total != 100:
            raise ValueError("JobProfile criteria weights must sum to 100")
        return self


class SourceRef(BaseModel):
    page_number: int = Field(ge=0)
    section: str
    text: str
    chunk_id: str


class MetricItem(BaseModel):
    name: str = ""
    value: str = ""
    unit: str = ""
    raw_text: str = ""
    source_refs: list[SourceRef] = Field(default_factory=list)


class ResumeBullet(BaseModel):
    raw_text: str = ""
    action: str = ""
    technologies: list[str] = Field(default_factory=list)
    metrics: list[MetricItem] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)


class EducationItem(BaseModel):
    school: str = ""
    degree: str = ""
    major: str = ""
    years: str = ""
    start_date: str = ""
    end_date: str = ""
    courses: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)


class WorkItem(BaseModel):
    company: str = ""
    title: str = ""
    duration: str = ""
    start_date: str = ""
    end_date: str = ""
    description: str = ""
    bullets: list[ResumeBullet] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    metrics: list[MetricItem] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)


class ProjectItem(BaseModel):
    name: str = ""
    role: str = ""
    duration: str = ""
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    bullets: list[ResumeBullet] = Field(default_factory=list)
    metrics: list[MetricItem] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)


class SkillItem(BaseModel):
    name: str = ""
    category: str = ""
    evidence_level: SkillEvidenceLevel = "mentioned"
    proficiency_claim: str = ""
    source_refs: list[SourceRef] = Field(default_factory=list)


class AchievementItem(BaseModel):
    name: str = ""
    level: str = ""
    category: str = ""
    source_refs: list[SourceRef] = Field(default_factory=list)


class ResumeProfile(BaseModel):
    candidate_name: str
    contact: dict[str, str] = Field(default_factory=dict)
    education: list[EducationItem] = Field(default_factory=list)
    work_experience: list[WorkItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    skills: list[SkillItem] = Field(default_factory=list)
    achievements: list[AchievementItem] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    self_summary: str = ""
    certifications: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    quality: dict[str, Any] = Field(default_factory=dict)
    structured_ambiguities: list[dict[str, Any]] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_skill_and_achievement_lists(cls, data):
        if not isinstance(data, dict):
            return data
        data = dict(data)
        data["skills"] = [
            {"name": item} if isinstance(item, str) else item
            for item in data.get("skills") or []
        ]
        data["achievements"] = [
            {"name": item} if isinstance(item, str) else item
            for item in data.get("achievements") or []
        ]
        return data


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
    evidence_chunk_ids: list[str] = Field(default_factory=list, max_length=5)
    missing_evidence: list[str] = Field(default_factory=list)
    risk: str = ""

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_evidence_ids(cls, data):
        if isinstance(data, dict) and "evidence_chunk_ids" not in data and "evidence" in data:
            data = dict(data)
            data["evidence_chunk_ids"] = [
                item.get("chunk_id") if isinstance(item, dict) else getattr(item, "chunk_id", None)
                for item in data.get("evidence") or []
                if (item.get("chunk_id") if isinstance(item, dict) else getattr(item, "chunk_id", None))
            ]
        return data

    @model_validator(mode="after")
    def _score_status_evidence_consistency(self) -> "CriterionEvaluation":
        expected_status = {
            5: "strong_match",
            4: "match",
            3: "partial_match",
            2: "partial_match",
            1: "partial_match",
        }
        if self.score == 0:
            if self.status not in {"no_evidence", "conflict"}:
                raise ValueError("score=0 requires no_evidence or conflict")
            if self.evidence_chunk_ids:
                raise ValueError("score=0 requires empty evidence")
        else:
            if self.status != expected_status[self.score]:
                raise ValueError("score/status mismatch")
            if not self.evidence_chunk_ids:
                raise ValueError(f"score > 0 requires evidence: {self.criterion_id}")
        return self


class HydratedCriterionEvaluation(CriterionEvaluation):
    evidence: list[EvidenceChunk] = Field(default_factory=list)


class MatchEvaluation(BaseModel):
    evaluations: list[CriterionEvaluation]


class InterviewQuestion(BaseModel):
    question: str
    question_type: QuestionType
    difficulty: Difficulty
    assessment_points: list[str]
    related_criteria: list[str]
    evidence_chunk_ids: list[str] = Field(default_factory=list, max_length=2)
    reference_answer_direction: str
    scoring_rubric: list[str]
    suggested_followups: list[str]

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_evidence_ids(cls, data):
        if isinstance(data, dict):
            data = dict(data)
            if "evidence_chunk_ids" not in data and "evidence" in data:
                data["evidence_chunk_ids"] = [
                    item.get("chunk_id") if isinstance(item, dict) else getattr(item, "chunk_id", None)
                    for item in data.get("evidence") or []
                    if (item.get("chunk_id") if isinstance(item, dict) else getattr(item, "chunk_id", None))
                ]
            data["evidence_chunk_ids"] = list(data.get("evidence_chunk_ids") or [])[:2]
        return data


class QuestionBlueprintItem(BaseModel):
    question_id: str
    question_type: QuestionType
    primary_criterion_id: str
    secondary_criterion_ids: list[str] = Field(default_factory=list, max_length=1)
    evidence_chunk_ids: list[str] = Field(default_factory=list, max_length=2)
    objective: str
    difficulty: Difficulty


class AmbiguitySource(BaseModel):
    source_id: str
    related_criterion_id: str = ""
    evidence_chunk_ids: list[str] = Field(default_factory=list, max_length=2)
    reason: str


class QuestionBlueprint(BaseModel):
    formal_questions: list[QuestionBlueprintItem] = Field(min_length=1, max_length=10)
    ambiguity_sources: list[AmbiguitySource] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def _formal_distribution(self) -> "QuestionBlueprint":
        expected = {
            "resume_experience": 3,
            "jd_core_capability": 2,
            "scenario_design": 2,
            "gap_validation": 2,
            "behavior_review": 1,
        }
        if len(self.formal_questions) != 10:
            return self
        actual = {key: 0 for key in expected}
        for question in self.formal_questions:
            actual[question.question_type] = actual.get(question.question_type, 0) + 1
        if actual != expected:
            raise ValueError(f"formal question distribution must be {expected}, got {actual}")
        ids = [item.question_id for item in self.formal_questions]
        if len(ids) != len(set(ids)):
            raise ValueError("question_id values must be unique")
        return self


class QuestionBatch(BaseModel):
    formal_questions: list[InterviewQuestion] = Field(min_length=0, max_length=5)


class AmbiguityFollowupSet(BaseModel):
    ambiguity_followups: list[InterviewQuestion] = Field(min_length=3, max_length=5)


class QuestionSet(BaseModel):
    formal_questions: list[InterviewQuestion] = Field(min_length=1, max_length=10)
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
        if len(self.formal_questions) != 10:
            return self
        actual = {key: 0 for key in expected}
        for question in self.formal_questions:
            actual[question.question_type] = actual.get(question.question_type, 0) + 1
        if actual != expected:
            raise ValueError(f"formal question distribution must be {expected}, got {actual}")
        return self


class CandidateReport(BaseModel):
    run_id: int
    candidate_id: int
    candidate_name: str
    filename: str
    job_profile: JobProfile
    resume_profile: ResumeProfile
    evaluations: list[HydratedCriterionEvaluation]
    total_score: float = Field(ge=0, le=100)
    recommendation: Recommendation
    top_strengths: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary: str
    formal_questions: list[InterviewQuestion] = Field(default_factory=list, max_length=10)
    ambiguity_followups: list[InterviewQuestion] = Field(default_factory=list, max_length=5)


class CandidateSummary(BaseModel):
    candidate_id: int
    candidate_name: str
    filename: str
    total_score: float
    recommendation: Recommendation
    top_strengths: list[str] = Field(default_factory=list)


class RunSummary(ApiModel):
    run_id: int
    job_title: str
    candidates: list[CandidateSummary]


class AnalyzeResponse(RunSummary):
    task_id: str = Field(default="", alias="taskId")


class AnalyzeRequest(ApiModel):
    jd_document_id: str
    resume_document_ids: list[str] = Field(min_length=1)
    task_id: str = Field(default="", alias="taskId")


class EvidenceSearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=4, ge=1, le=20)


class EvidenceSearchResponse(BaseModel):
    run_id: int
    candidate_id: int
    results: list[EvidenceChunk]


DocumentType = Literal["jd", "resume"]


class DocumentParseResult(BaseModel):
    id: str
    type: DocumentType
    filename: str
    size: int
    raw_text: str
    parsed_content: dict[str, Any]
    parse_status: str = "success"
    created_at: str = ""
    vectorized: bool = True
    local_stored: bool = True


class DocumentParseResponse(ApiModel):
    documents: list[DocumentParseResult]
    task_id: str = Field(default="", alias="taskId")


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
