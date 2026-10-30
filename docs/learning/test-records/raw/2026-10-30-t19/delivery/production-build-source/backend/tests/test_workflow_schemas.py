import pytest

from backend.schemas.workflow import (
    CandidateReport,
    Criterion,
    EvidenceChunk,
    JobProfile,
    MatchEvaluation,
    QuestionSet,
)
from backend.services.llm_validation import validate_question_set


def test_job_profile_requires_weights_sum_to_100():
    with pytest.raises(ValueError, match="weights must sum to 100"):
        JobProfile(
            job_title="Backend Engineer",
            summary="Build APIs",
            responsibilities=["Build services"],
            criteria=[
                Criterion(
                    criterion_id="c1",
                    name="Python",
                    description="Python service experience",
                    importance="must",
                    weight=90,
                    evidence_query="Python FastAPI projects",
                )
            ],
            interview_focus=["API design"],
        )


def test_job_profile_accepts_minor_weight_rounding_drift():
    profile = JobProfile(
        job_title="Backend Engineer",
        summary="Build APIs",
        responsibilities=["Build services"],
        criteria=[
            Criterion(
                criterion_id=f"c{i}",
                name=f"Criterion {i}",
                description=f"Criterion {i}",
                importance="must",
                weight=33.33,
                evidence_query=f"criterion {i}",
            )
            for i in range(1, 4)
        ],
        interview_focus=["API design"],
    )

    assert [criterion.weight for criterion in profile.criteria] == [33.34, 33.33, 33.33]


def test_positive_evaluation_requires_evidence():
    with pytest.raises(ValueError, match="score > 0 requires"):
        MatchEvaluation(
            evaluations=[
                {
                    "criterion_id": "c1",
                    "name": "Python",
                    "weight": 100,
                    "score": 3,
                    "status": "partial_match",
                    "reason": "mentions Python",
                    "evidence": [],
                    "missing_evidence": [],
                    "risk": "",
                }
            ]
        )


def test_question_set_requires_formal_distribution():
    evidence = EvidenceChunk(
        chunk_id="chunk-1",
        filename="resume.pdf",
        page_number=1,
        section="Projects",
        text="Built FastAPI services.",
        score=0.9,
    )
    question = {
        "question": "Tell me about the project.",
        "difficulty": "medium",
        "assessment_points": ["depth"],
        "related_criteria": ["c1"],
        "evidence": [evidence.model_dump()],
        "reference_answer_direction": "Explain role and result.",
        "scoring_rubric": ["clear context", "specific contribution"],
        "suggested_followups": ["What was hardest?"],
    }
    formal = [{**question, "question_type": "resume_experience"} for _ in range(10)]
    followups = [{**question, "question_type": "gap_validation"} for _ in range(3)]

    with pytest.raises(ValueError, match="formal question distribution"):
        QuestionSet(formal_questions=formal, ambiguity_followups=followups)


def test_candidate_report_trims_legacy_question_evidence_ids_to_schema_limit():
    question = {
        "question": "Tell me about the project.",
        "question_type": "resume_experience",
        "difficulty": "medium",
        "assessment_points": ["depth"],
        "related_criteria": ["c1"],
        "evidence_chunk_ids": ["chunk-1", "chunk-2", "chunk-3"],
        "reference_answer_direction": "Explain role and result.",
        "scoring_rubric": ["clear context", "specific contribution"],
        "suggested_followups": ["What was hardest?"],
    }
    report = CandidateReport.model_validate(
        {
            "run_id": 1,
            "candidate_id": 2,
            "candidate_name": "Ada",
            "filename": "ada.pdf",
            "job_profile": {
                "job_title": "Backend Engineer",
                "summary": "Build APIs",
                "criteria": [
                    {
                        "criterion_id": "c1",
                        "name": "Python",
                        "description": "Python service experience",
                        "importance": "must",
                        "weight": 100,
                        "evidence_query": "Python FastAPI projects",
                    }
                ],
            },
            "resume_profile": {"candidate_name": "Ada"},
            "evaluations": [],
            "total_score": 80,
            "recommendation": "recommend",
            "top_strengths": [],
            "summary": "Good match.",
            "formal_questions": [question],
            "ambiguity_followups": [{**question, "question_type": "gap_validation"}],
        }
    )

    assert report.formal_questions[0].evidence_chunk_ids == ["chunk-1", "chunk-2"]
    assert report.ambiguity_followups[0].evidence_chunk_ids == ["chunk-1", "chunk-2"]


def test_question_validation_allows_missing_evidence_when_report_has_no_allowed_evidence():
    profile = JobProfile(
        job_title="Backend Engineer",
        summary="Build APIs",
        criteria=[
            Criterion(
                criterion_id="c1",
                name="Python",
                description="Python service experience",
                importance="must",
                weight=100,
                evidence_query="Python FastAPI projects",
            )
        ],
    )
    base_question = {
        "question": "Tell me about a relevant project.",
        "difficulty": "medium",
        "assessment_points": ["depth"],
        "related_criteria": ["c1"],
        "evidence_chunk_ids": [],
        "reference_answer_direction": "Explain role and result.",
        "scoring_rubric": ["clear context", "specific contribution"],
        "suggested_followups": ["What was hardest?"],
    }
    formal_types = [
        "resume_experience",
        "resume_experience",
        "resume_experience",
        "jd_core_capability",
        "jd_core_capability",
        "scenario_design",
        "scenario_design",
        "gap_validation",
        "gap_validation",
        "behavior_review",
    ]
    question_set = QuestionSet(
        formal_questions=[
            {**base_question, "question": f"Question {index}", "question_type": question_type}
            for index, question_type in enumerate(formal_types, start=1)
        ],
        ambiguity_followups=[
            {**base_question, "question": f"Follow-up {index}", "question_type": "gap_validation"}
            for index in range(1, 4)
        ],
    )

    validate_question_set(
        question_set,
        job_profile=profile,
        allowed_evidence_chunk_ids=set(),
        gap_criterion_ids={"c1"},
    )
