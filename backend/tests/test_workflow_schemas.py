import pytest

from backend.schemas.workflow import (
    Criterion,
    EvidenceChunk,
    JobProfile,
    MatchEvaluation,
    QuestionSet,
)


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
