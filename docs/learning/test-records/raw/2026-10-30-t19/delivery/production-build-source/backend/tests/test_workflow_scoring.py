from backend.graph.candidate_workflow import calculate_total_score, recommendation_for_score
from backend.schemas.workflow import CriterionEvaluation, EvidenceChunk


def test_total_score_is_python_weighted_sum():
    evidence = EvidenceChunk(
        chunk_id="chunk-1",
        filename="resume.pdf",
        page_number=1,
        section="Projects",
        text="Built a Milvus RAG workflow.",
        score=0.87,
    )
    evaluations = [
        CriterionEvaluation(
            criterion_id="c1",
            name="RAG",
            weight=60,
            score=5,
            status="strong_match",
            reason="direct evidence",
            evidence=[evidence],
        ),
        CriterionEvaluation(
            criterion_id="c2",
            name="Frontend",
            weight=40,
            score=3,
            status="partial_match",
            reason="partial evidence",
            evidence=[evidence],
        ),
    ]

    assert calculate_total_score(evaluations) == 84
    assert recommendation_for_score(84) == "strong_recommend"
    assert recommendation_for_score(65) == "recommend"
    assert recommendation_for_score(50) == "hold"
    assert recommendation_for_score(49.99) == "reject"
