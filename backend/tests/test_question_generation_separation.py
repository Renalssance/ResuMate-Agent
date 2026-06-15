from types import SimpleNamespace
from collections import Counter

import pytest
from fastapi import HTTPException

from backend.graph.candidate_workflow import CandidateAnalysisGraph
from backend.routes import runs as runs_route
from backend.schemas.workflow import (
    AmbiguityFollowupSet,
    CandidateReport,
    Criterion,
    CriterionEvaluation,
    JobProfile,
    MatchEvaluation,
    QuestionBatch,
    QuestionBlueprint,
    QuestionBlueprintItem,
    QuestionSet,
    InterviewQuestion,
    ResumeProfile,
)
from backend.services.analysis import AnalysisService


class RecordingHarness:
    def __init__(self):
        self.tasks = []

    def run_schema(self, *, task, **_kwargs):
        self.tasks.append(task)
        if task == "evaluate_match":
            return MatchEvaluation(
                evaluations=[
                    {
                        "criterion_id": "api",
                        "name": "API",
                        "weight": 100,
                        "score": 0,
                        "status": "no_evidence",
                        "reason": "No supplied evidence supports this criterion.",
                        "evidence_chunk_ids": [],
                        "missing_evidence": ["API implementation evidence"],
                        "risk": "",
                    }
                ]
            )
        if task == "generate_questions":
            raise AssertionError("matching must not generate questions")
        raise AssertionError(f"unexpected task: {task}")


class RecordingRagStore:
    def __init__(self, job_profile, resume_profile):
        self.job_profile = job_profile
        self.resume_profile = resume_profile

    def load_document_profile(self, *, document_type, **_kwargs):
        profile = self.job_profile if document_type == "jd" else self.resume_profile
        return profile.model_dump(mode="json")

    def search_resume_evidence(self, **_kwargs):
        return []

    def persist_artifact(self, **_kwargs):
        pass


class RecordingRepository:
    def __init__(self, report=None):
        self.report = report
        self.saved_reports = []
        self.saved_question_sets = []

    def save_report(self, **kwargs):
        self.saved_reports.append(kwargs["report"])

    def get_candidate_report(self, **_kwargs):
        return self.report

    def save_questions(self, **kwargs):
        self.saved_question_sets.append(kwargs["question_set"])
        return self.report.model_copy(
            update={
                "formal_questions": kwargs["question_set"].formal_questions,
                "ambiguity_followups": kwargs["question_set"].ambiguity_followups,
            }
        )


def _profiles():
    job_profile = JobProfile(
        job_title="Backend Engineer",
        summary="Build APIs",
        criteria=[
            Criterion(
                criterion_id="api",
                name="API",
                description="Build APIs",
                importance="must",
                weight=100,
                evidence_query="API",
            )
        ],
    )
    return job_profile, ResumeProfile(candidate_name="Candidate")


def _question(index: int, question_type: str, criterion_id: str, evidence_chunk_ids: list[str]) -> InterviewQuestion:
    return InterviewQuestion(
        question=f"Question {index}?",
        question_type=question_type,
        difficulty="medium",
        assessment_points=["point"],
        related_criteria=[criterion_id],
        evidence_chunk_ids=evidence_chunk_ids,
        reference_answer_direction="Answer direction.",
        scoring_rubric=["rubric"],
        suggested_followups=["Follow up?"],
    )


def test_matching_graph_does_not_generate_questions():
    job_profile, resume_profile = _profiles()
    harness = RecordingHarness()
    repository = RecordingRepository()
    graph = CandidateAnalysisGraph(
        harness=harness,
        rag_store=RecordingRagStore(job_profile, resume_profile),
        repository=repository,
    )

    report = graph.run(
        {
            "user_id": 1,
            "run_id": 2,
            "candidate_id": 3,
            "jd_document_id": 4,
            "resume_document_id": 5,
            "filename": "candidate.pdf",
            "job": SimpleNamespace(),
            "candidate": SimpleNamespace(),
        }
    )

    assert harness.tasks == ["evaluate_match"]
    assert report.formal_questions == []
    assert report.ambiguity_followups == []


def test_question_generation_only_runs_generate_questions_and_persists_result():
    job_profile, resume_profile = _profiles()
    report = CandidateReport.model_construct(
        run_id=2,
        candidate_id=3,
        candidate_name="Candidate",
        filename="candidate.pdf",
        job_profile=job_profile,
        resume_profile=resume_profile,
        evaluations=[],
        total_score=0,
        recommendation="reject",
        top_strengths=[],
        summary="Candidate matched Backend Engineer.",
        formal_questions=[],
        ambiguity_followups=[],
    )
    blueprint = QuestionBlueprint.model_construct(formal_questions=[], ambiguity_sources=[])
    batch = QuestionBatch.model_construct(formal_questions=[])
    followups = AmbiguityFollowupSet.model_construct(ambiguity_followups=[])
    question_set = QuestionSet.model_construct(formal_questions=[], ambiguity_followups=[])
    repository = RecordingRepository(report)
    harness = SimpleNamespace(tasks=[])

    def run_schema(**kwargs):
        harness.tasks.append(kwargs["task"])
        if kwargs["task"] == "plan_question_blueprint":
            return blueprint
        if kwargs["task"] == "generate_question_batch":
            return batch
        if kwargs["task"] == "generate_ambiguity_followups":
            return followups
        raise AssertionError(kwargs["task"])

    harness.run_schema = run_schema
    service = object.__new__(AnalysisService)
    service.harness = harness
    service.repository = repository
    service._build_question_set_from_split = lambda **_kwargs: question_set

    updated = service.generate_questions(user_id=1, run_id=2, candidate_id=3)

    assert harness.tasks == [
        "plan_question_blueprint",
        "generate_question_batch",
        "generate_question_batch",
        "generate_ambiguity_followups",
    ]
    assert repository.saved_question_sets == [question_set]
    assert updated.formal_questions == []


def test_question_generation_backfills_non_gap_questions_from_report_evidence():
    job_profile = JobProfile(
        job_title="AI Builder",
        summary="Build AI workflows",
        criteria=[
            Criterion(
                criterion_id=f"c{i}",
                name=f"Criterion {i}",
                description=f"Criterion {i}",
                importance="must" if i < 4 else "important",
                weight=25,
                evidence_query=f"criterion {i}",
            )
            for i in range(1, 5)
        ],
    )
    report = CandidateReport.model_construct(
        run_id=1,
        candidate_id=2,
        candidate_name="Candidate",
        filename="candidate.pdf",
        job_profile=job_profile,
        resume_profile=ResumeProfile(candidate_name="Candidate"),
        evaluations=[
            CriterionEvaluation(
                criterion_id="c1",
                name="Criterion 1",
                weight=25,
                score=2,
                status="partial_match",
                reason="Partial evidence.",
                evidence_chunk_ids=["e1"],
                missing_evidence=["depth"],
            ),
            CriterionEvaluation(
                criterion_id="c2",
                name="Criterion 2",
                weight=25,
                score=3,
                status="partial_match",
                reason="Some evidence.",
                evidence_chunk_ids=["e2"],
            ),
            CriterionEvaluation(
                criterion_id="c3",
                name="Criterion 3",
                weight=25,
                score=3,
                status="partial_match",
                reason="Some evidence.",
                evidence_chunk_ids=["e3"],
            ),
            CriterionEvaluation(
                criterion_id="c4",
                name="Criterion 4",
                weight=25,
                score=3,
                status="partial_match",
                reason="Some evidence.",
                evidence_chunk_ids=["e4"],
            ),
        ],
        total_score=70,
        recommendation="recommend",
        top_strengths=[],
        summary="Candidate matched.",
        formal_questions=[],
        ambiguity_followups=[],
    )
    specs = [
        ("resume_experience", "c1", ["e1"]),
        ("resume_experience", "c2", ["e2"]),
        ("resume_experience", "c4", ["e4"]),
        ("jd_core_capability", "c2", []),
        ("jd_core_capability", "c3", []),
        ("scenario_design", "c3", []),
        ("scenario_design", "c4", []),
        ("gap_validation", "c1", []),
        ("gap_validation", "c1", []),
        ("behavior_review", "c1", ["e1"]),
    ]
    blueprint = QuestionBlueprint(
        formal_questions=[
            QuestionBlueprintItem(
                question_id=f"q{index:02d}",
                question_type=question_type,
                primary_criterion_id=criterion_id,
                evidence_chunk_ids=evidence_chunk_ids,
                objective=f"objective {index}",
                difficulty="medium",
            )
            for index, (question_type, criterion_id, evidence_chunk_ids) in enumerate(specs, start=1)
        ],
        ambiguity_sources=[],
    )
    questions = [
        _question(index, question_type, criterion_id, evidence_chunk_ids)
        for index, (question_type, criterion_id, evidence_chunk_ids) in enumerate(specs, start=1)
    ]
    service = object.__new__(AnalysisService)

    question_set = service._build_question_set_from_split(
        report=report,
        blueprint=blueprint,
        batches=[QuestionBatch(formal_questions=questions[:5]), QuestionBatch(formal_questions=questions[5:])],
        followups=AmbiguityFollowupSet(
            ambiguity_followups=[
                _question(11, "gap_validation", "c1", []),
                _question(12, "gap_validation", "c1", []),
                _question(13, "gap_validation", "c1", []),
            ]
        ),
    )

    assert question_set.formal_questions[3].evidence_chunk_ids == ["e2"]
    assert question_set.formal_questions[4].evidence_chunk_ids == ["e3"]
    assert question_set.formal_questions[5].evidence_chunk_ids == ["e3"]
    assert question_set.formal_questions[6].evidence_chunk_ids == ["e4"]


def test_question_generation_normalizes_llm_criterion_names_before_validation():
    job_profile = JobProfile(
        job_title="AI Builder",
        summary="Build AI workflows",
        criteria=[
            Criterion(
                criterion_id="c1",
                name="Model Alignment",
                description="Alignment work",
                importance="must",
                weight=50,
                evidence_query="alignment",
            ),
            Criterion(
                criterion_id="c2",
                name="Deployment",
                description="Deployment work",
                importance="must",
                weight=50,
                evidence_query="deployment",
            ),
        ],
    )
    report = CandidateReport.model_construct(
        run_id=1,
        candidate_id=2,
        candidate_name="Candidate",
        filename="candidate.pdf",
        job_profile=job_profile,
        resume_profile=ResumeProfile(candidate_name="Candidate"),
        evaluations=[
            CriterionEvaluation(
                criterion_id="c1",
                name="Model Alignment",
                weight=50,
                score=3,
                status="partial_match",
                reason="Some evidence.",
                evidence_chunk_ids=["e1"],
            ),
            CriterionEvaluation(
                criterion_id="c2",
                name="Deployment",
                weight=50,
                score=0,
                status="no_evidence",
                reason="No evidence.",
                evidence_chunk_ids=[],
                missing_evidence=["deployment"],
            ),
        ],
        total_score=50,
        recommendation="hold",
        top_strengths=[],
        summary="Candidate partially matched.",
        formal_questions=[],
        ambiguity_followups=[],
    )
    specs = [
        ("resume_experience", "c1", ["e1"]),
        ("resume_experience", "c1", ["e1"]),
        ("resume_experience", "c1", ["e1"]),
        ("jd_core_capability", "c1", ["e1"]),
        ("jd_core_capability", "c1", ["e1"]),
        ("scenario_design", "c1", ["e1"]),
        ("scenario_design", "c1", ["e1"]),
        ("gap_validation", "c2", []),
        ("gap_validation", "c2", []),
        ("behavior_review", "c1", ["e1"]),
    ]
    blueprint = QuestionBlueprint(
        formal_questions=[
            QuestionBlueprintItem(
                question_id=f"q{index:02d}",
                question_type=question_type,
                primary_criterion_id=criterion_id,
                evidence_chunk_ids=evidence_chunk_ids,
                objective=f"objective {index}",
                difficulty="medium",
            )
            for index, (question_type, criterion_id, evidence_chunk_ids) in enumerate(specs, start=1)
        ],
        ambiguity_sources=[],
    )
    questions = [
        _question(index, question_type, "Model Alignment" if criterion_id == "c1" else "Deployment", evidence_chunk_ids)
        for index, (question_type, criterion_id, evidence_chunk_ids) in enumerate(specs, start=1)
    ]
    service = object.__new__(AnalysisService)

    question_set = service._build_question_set_from_split(
        report=report,
        blueprint=blueprint,
        batches=[QuestionBatch(formal_questions=questions[:5]), QuestionBatch(formal_questions=questions[5:])],
        followups=AmbiguityFollowupSet(
            ambiguity_followups=[
                _question(11, "behavior_review", "Model Alignment", ["missing"]),
                _question(12, "gap_validation", "Deployment", []),
                _question(13, "behavior_review", "Unknown Criterion", ["missing"]),
            ]
        ),
    )

    assert question_set.formal_questions[0].related_criteria == ["c1"]
    assert question_set.formal_questions[7].related_criteria == ["c2"]
    assert question_set.ambiguity_followups[0].related_criteria == ["c1"]
    assert question_set.ambiguity_followups[0].evidence_chunk_ids == ["e1"]
    assert question_set.ambiguity_followups[2].related_criteria == ["c1"]
    assert question_set.ambiguity_followups[2].evidence_chunk_ids == ["e1"]


def test_question_generation_allows_gap_validation_when_report_has_no_low_score_gaps():
    job_profile = JobProfile(
        job_title="AI Builder",
        summary="Build AI workflows",
        criteria=[
            Criterion(
                criterion_id=f"c{i}",
                name=f"Criterion {i}",
                description=f"Criterion {i}",
                importance="must" if i < 4 else "important",
                weight=25,
                evidence_query=f"criterion {i}",
            )
            for i in range(1, 5)
        ],
    )
    report = CandidateReport.model_construct(
        run_id=1,
        candidate_id=2,
        candidate_name="Candidate",
        filename="candidate.pdf",
        job_profile=job_profile,
        resume_profile=ResumeProfile(candidate_name="Candidate"),
        evaluations=[
            CriterionEvaluation(
                criterion_id="c1",
                name="Criterion 1",
                weight=25,
                score=5,
                status="strong_match",
                reason="Strong evidence.",
                evidence_chunk_ids=["e1"],
            ),
            CriterionEvaluation(
                criterion_id="c2",
                name="Criterion 2",
                weight=25,
                score=4,
                status="match",
                reason="Good evidence.",
                evidence_chunk_ids=["e1"],
            ),
            CriterionEvaluation(
                criterion_id="c3",
                name="Criterion 3",
                weight=25,
                score=3,
                status="partial_match",
                reason="Some evidence.",
                evidence_chunk_ids=["e2"],
            ),
            CriterionEvaluation(
                criterion_id="c4",
                name="Criterion 4",
                weight=25,
                score=4,
                status="match",
                reason="Good evidence.",
                evidence_chunk_ids=["e2", "e1"],
            ),
        ],
        total_score=80,
        recommendation="strong_recommend",
        top_strengths=[],
        summary="Candidate matched.",
        formal_questions=[],
        ambiguity_followups=[],
    )
    specs = [
        ("resume_experience", "c1", ["e1"]),
        ("resume_experience", "c2", ["e1"]),
        ("resume_experience", "c4", ["e2"]),
        ("jd_core_capability", "c1", ["e1"]),
        ("jd_core_capability", "c2", ["e1"]),
        ("scenario_design", "c1", ["e1"]),
        ("scenario_design", "c3", ["e2"]),
        ("gap_validation", "c2", []),
        ("gap_validation", "c3", []),
        ("behavior_review", "c1", ["e1"]),
    ]
    blueprint = QuestionBlueprint(
        formal_questions=[
            QuestionBlueprintItem(
                question_id=f"q{index:02d}",
                question_type=question_type,
                primary_criterion_id=criterion_id,
                evidence_chunk_ids=evidence_chunk_ids,
                objective=f"objective {index}",
                difficulty="medium",
            )
            for index, (question_type, criterion_id, evidence_chunk_ids) in enumerate(specs, start=1)
        ],
        ambiguity_sources=[],
    )
    questions = [
        _question(index, question_type, criterion_id, evidence_chunk_ids)
        for index, (question_type, criterion_id, evidence_chunk_ids) in enumerate(specs, start=1)
    ]
    service = object.__new__(AnalysisService)

    question_set = service._build_question_set_from_split(
        report=report,
        blueprint=blueprint,
        batches=[QuestionBatch(formal_questions=questions[:5]), QuestionBatch(formal_questions=questions[5:])],
        followups=AmbiguityFollowupSet(
            ambiguity_followups=[
                _question(11, "gap_validation", "c2", []),
                _question(12, "gap_validation", "c3", []),
                _question(13, "gap_validation", "c4", []),
            ]
        ),
    )

    assert [question.question_type for question in question_set.formal_questions[7:9]] == ["gap_validation", "gap_validation"]


def test_question_generation_backfills_non_gap_question_from_any_report_evidence_when_criterion_has_none():
    job_profile = JobProfile(
        job_title="AI Builder",
        summary="Build AI workflows",
        criteria=[
            Criterion(
                criterion_id=f"c{i}",
                name=f"Criterion {i}",
                description=f"Criterion {i}",
                importance="must" if i < 4 else "important",
                weight=25,
                evidence_query=f"criterion {i}",
            )
            for i in range(1, 5)
        ],
    )
    report = CandidateReport.model_construct(
        run_id=1,
        candidate_id=2,
        candidate_name="Candidate",
        filename="candidate.pdf",
        job_profile=job_profile,
        resume_profile=ResumeProfile(candidate_name="Candidate"),
        evaluations=[
            CriterionEvaluation(
                criterion_id="c1",
                name="Criterion 1",
                weight=25,
                score=2,
                status="partial_match",
                reason="Partial evidence.",
                evidence_chunk_ids=["e1"],
                missing_evidence=["depth"],
            ),
            CriterionEvaluation(
                criterion_id="c2",
                name="Criterion 2",
                weight=25,
                score=3,
                status="partial_match",
                reason="Some evidence.",
                evidence_chunk_ids=["e2"],
            ),
            CriterionEvaluation(
                criterion_id="c3",
                name="Criterion 3",
                weight=25,
                score=3,
                status="partial_match",
                reason="Some evidence.",
                evidence_chunk_ids=["e3"],
            ),
            CriterionEvaluation(
                criterion_id="c4",
                name="Criterion 4",
                weight=25,
                score=0,
                status="no_evidence",
                reason="No evidence.",
                evidence_chunk_ids=[],
                missing_evidence=["collaboration"],
            ),
        ],
        total_score=70,
        recommendation="recommend",
        top_strengths=[],
        summary="Candidate matched.",
        formal_questions=[],
        ambiguity_followups=[],
    )
    specs = [
        ("resume_experience", "c1", ["e1"]),
        ("resume_experience", "c2", ["e2"]),
        ("resume_experience", "c3", ["e3"]),
        ("jd_core_capability", "c1", []),
        ("jd_core_capability", "c2", []),
        ("scenario_design", "c2", []),
        ("scenario_design", "c3", []),
        ("gap_validation", "c1", []),
        ("gap_validation", "c4", []),
        ("behavior_review", "c4", []),
    ]
    blueprint = QuestionBlueprint(
        formal_questions=[
            QuestionBlueprintItem(
                question_id=f"q{index:02d}",
                question_type=question_type,
                primary_criterion_id=criterion_id,
                evidence_chunk_ids=evidence_chunk_ids,
                objective=f"objective {index}",
                difficulty="medium",
            )
            for index, (question_type, criterion_id, evidence_chunk_ids) in enumerate(specs, start=1)
        ],
        ambiguity_sources=[],
    )
    questions = [
        _question(index, question_type, criterion_id, evidence_chunk_ids)
        for index, (question_type, criterion_id, evidence_chunk_ids) in enumerate(specs, start=1)
    ]
    service = object.__new__(AnalysisService)

    question_set = service._build_question_set_from_split(
        report=report,
        blueprint=blueprint,
        batches=[QuestionBatch(formal_questions=questions[:5]), QuestionBatch(formal_questions=questions[5:])],
        followups=AmbiguityFollowupSet(
            ambiguity_followups=[
                _question(11, "gap_validation", "c1", []),
                _question(12, "gap_validation", "c4", []),
                _question(13, "gap_validation", "c4", []),
            ]
        ),
    )

    assert question_set.formal_questions[9].evidence_chunk_ids


def test_question_generation_rebalances_overused_primary_evidence_from_blueprint():
    job_profile = JobProfile(
        job_title="AI Builder",
        summary="Build AI workflows",
        criteria=[
            Criterion(
                criterion_id=f"c{i}",
                name=f"Criterion {i}",
                description=f"Criterion {i}",
                importance="must" if i < 4 else "important",
                weight=25,
                evidence_query=f"criterion {i}",
            )
            for i in range(1, 5)
        ],
    )
    report = CandidateReport.model_construct(
        run_id=1,
        candidate_id=2,
        candidate_name="Candidate",
        filename="candidate.pdf",
        job_profile=job_profile,
        resume_profile=ResumeProfile(candidate_name="Candidate"),
        evaluations=[
            CriterionEvaluation(
                criterion_id=f"c{i}",
                name=f"Criterion {i}",
                weight=25,
                score=3 if i > 1 else 2,
                status="partial_match",
                reason="Some evidence.",
                evidence_chunk_ids=[f"e{i}"],
                missing_evidence=["depth"] if i == 1 else [],
            )
            for i in range(1, 5)
        ],
        total_score=70,
        recommendation="recommend",
        top_strengths=[],
        summary="Candidate matched.",
        formal_questions=[],
        ambiguity_followups=[],
    )
    specs = [
        ("resume_experience", "c1", ["e1"]),
        ("resume_experience", "c1", ["e1"]),
        ("resume_experience", "c2", ["e2"]),
        ("jd_core_capability", "c2", ["e2"]),
        ("jd_core_capability", "c3", ["e3"]),
        ("scenario_design", "c3", ["e3"]),
        ("scenario_design", "c4", ["e4"]),
        ("gap_validation", "c1", []),
        ("gap_validation", "c1", []),
        ("behavior_review", "c4", ["e4"]),
    ]
    blueprint = QuestionBlueprint(
        formal_questions=[
            QuestionBlueprintItem(
                question_id=f"q{index:02d}",
                question_type=question_type,
                primary_criterion_id=criterion_id,
                evidence_chunk_ids=evidence_chunk_ids,
                objective=f"objective {index}",
                difficulty="medium",
            )
            for index, (question_type, criterion_id, evidence_chunk_ids) in enumerate(specs, start=1)
        ],
        ambiguity_sources=[],
    )
    questions = [
        _question(index, question_type, criterion_id, ["e1"] if question_type != "gap_validation" else [])
        for index, (question_type, criterion_id, _evidence_chunk_ids) in enumerate(specs, start=1)
    ]
    service = object.__new__(AnalysisService)

    question_set = service._build_question_set_from_split(
        report=report,
        blueprint=blueprint,
        batches=[QuestionBatch(formal_questions=questions[:5]), QuestionBatch(formal_questions=questions[5:])],
        followups=AmbiguityFollowupSet(
            ambiguity_followups=[
                _question(11, "gap_validation", "c1", []),
                _question(12, "gap_validation", "c1", []),
                _question(13, "gap_validation", "c1", []),
            ]
        ),
    )

    primary_counts = Counter(
        question.evidence_chunk_ids[0]
        for question in question_set.formal_questions
        if question.evidence_chunk_ids
    )
    assert primary_counts
    assert max(primary_counts.values()) <= 2


def test_question_generation_uses_report_evidence_when_local_primary_candidates_are_exhausted():
    job_profile = JobProfile(
        job_title="AI Builder",
        summary="Build AI workflows",
        criteria=[
            Criterion(
                criterion_id=f"c{i}",
                name=f"Criterion {i}",
                description=f"Criterion {i}",
                importance="must" if i < 4 else "important",
                weight=25,
                evidence_query=f"criterion {i}",
            )
            for i in range(1, 5)
        ],
    )
    report = CandidateReport.model_construct(
        run_id=1,
        candidate_id=2,
        candidate_name="Candidate",
        filename="candidate.pdf",
        job_profile=job_profile,
        resume_profile=ResumeProfile(candidate_name="Candidate"),
        evaluations=[
            CriterionEvaluation(
                criterion_id="c1",
                name="Criterion 1",
                weight=25,
                score=2,
                status="partial_match",
                reason="Some evidence.",
                evidence_chunk_ids=["e1"],
                missing_evidence=["depth"],
            ),
            CriterionEvaluation(
                criterion_id="c2",
                name="Criterion 2",
                weight=25,
                score=2,
                status="partial_match",
                reason="Some evidence.",
                evidence_chunk_ids=["e1"],
                missing_evidence=["scope"],
            ),
            CriterionEvaluation(
                criterion_id="c3",
                name="Criterion 3",
                weight=25,
                score=3,
                status="partial_match",
                reason="Some evidence.",
                evidence_chunk_ids=["e2", "e3"],
            ),
            CriterionEvaluation(
                criterion_id="c4",
                name="Criterion 4",
                weight=25,
                score=3,
                status="partial_match",
                reason="Some evidence.",
                evidence_chunk_ids=["e4"],
            ),
        ],
        total_score=70,
        recommendation="recommend",
        top_strengths=[],
        summary="Candidate matched.",
        formal_questions=[],
        ambiguity_followups=[],
    )
    specs = [
        ("resume_experience", "c1", ["e1"]),
        ("resume_experience", "c1", ["e1"]),
        ("resume_experience", "c1", ["e1"]),
        ("behavior_review", "c2", ["e1"]),
        ("jd_core_capability", "c3", ["e2"]),
        ("jd_core_capability", "c3", ["e3"]),
        ("scenario_design", "c4", ["e4"]),
        ("scenario_design", "c4", ["e4"]),
        ("gap_validation", "c1", []),
        ("gap_validation", "c2", []),
    ]
    blueprint = QuestionBlueprint(
        formal_questions=[
            QuestionBlueprintItem(
                question_id=f"q{index:02d}",
                question_type=question_type,
                primary_criterion_id=criterion_id,
                evidence_chunk_ids=evidence_chunk_ids,
                objective=f"objective {index}",
                difficulty="medium",
            )
            for index, (question_type, criterion_id, evidence_chunk_ids) in enumerate(specs, start=1)
        ],
        ambiguity_sources=[],
    )
    questions = [
        _question(index, question_type, criterion_id, evidence_chunk_ids)
        for index, (question_type, criterion_id, evidence_chunk_ids) in enumerate(specs, start=1)
    ]
    service = object.__new__(AnalysisService)

    question_set = service._build_question_set_from_split(
        report=report,
        blueprint=blueprint,
        batches=[QuestionBatch(formal_questions=questions[:5]), QuestionBatch(formal_questions=questions[5:])],
        followups=AmbiguityFollowupSet(
            ambiguity_followups=[
                _question(11, "gap_validation", "c1", []),
                _question(12, "gap_validation", "c1", []),
                _question(13, "gap_validation", "c2", []),
            ]
        ),
    )

    primary_counts = Counter(
        question.evidence_chunk_ids[0]
        for question in question_set.formal_questions
        if question.evidence_chunk_ids
    )
    assert max(primary_counts.values()) <= 2


def test_question_generation_allows_dynamic_primary_evidence_cap_when_evidence_is_sparse():
    job_profile = JobProfile(
        job_title="AI Builder",
        summary="Build AI workflows",
        criteria=[
            Criterion(
                criterion_id=f"c{i}",
                name=f"Criterion {i}",
                description=f"Criterion {i}",
                importance="must" if i < 4 else "important",
                weight=25,
                evidence_query=f"criterion {i}",
            )
            for i in range(1, 5)
        ],
    )
    report = CandidateReport.model_construct(
        run_id=4,
        candidate_id=4,
        candidate_name="Candidate",
        filename="candidate.pdf",
        job_profile=job_profile,
        resume_profile=ResumeProfile(candidate_name="Candidate"),
        evaluations=[
            CriterionEvaluation(
                criterion_id="c1",
                name="Criterion 1",
                weight=25,
                score=2,
                status="partial_match",
                reason="Some evidence.",
                evidence_chunk_ids=["e0", "e2"],
                missing_evidence=["depth"],
            ),
            CriterionEvaluation(
                criterion_id="c2",
                name="Criterion 2",
                weight=25,
                score=3,
                status="partial_match",
                reason="Some evidence.",
                evidence_chunk_ids=["e0", "e1"],
            ),
            CriterionEvaluation(
                criterion_id="c3",
                name="Criterion 3",
                weight=25,
                score=2,
                status="partial_match",
                reason="Some evidence.",
                evidence_chunk_ids=["e1", "e2"],
                missing_evidence=["prototype"],
            ),
            CriterionEvaluation(
                criterion_id="c4",
                name="Criterion 4",
                weight=25,
                score=3,
                status="partial_match",
                reason="Some evidence.",
                evidence_chunk_ids=["e0", "e2"],
            ),
        ],
        total_score=70,
        recommendation="recommend",
        top_strengths=[],
        summary="Candidate matched.",
        formal_questions=[],
        ambiguity_followups=[],
    )
    specs = [
        ("resume_experience", "c1", ["e0"]),
        ("resume_experience", "c2", ["e0"]),
        ("resume_experience", "c4", ["e1"]),
        ("jd_core_capability", "c1", ["e2"]),
        ("jd_core_capability", "c3", ["e1"]),
        ("scenario_design", "c2", ["e0"]),
        ("scenario_design", "c3", ["e2"]),
        ("gap_validation", "c1", []),
        ("gap_validation", "c3", []),
        ("behavior_review", "c4", ["e0"]),
    ]
    blueprint = QuestionBlueprint(
        formal_questions=[
            QuestionBlueprintItem(
                question_id=f"q{index:02d}",
                question_type=question_type,
                primary_criterion_id=criterion_id,
                secondary_criterion_ids=["c3"] if index == 6 else [],
                evidence_chunk_ids=evidence_chunk_ids,
                objective=f"objective {index}",
                difficulty="medium",
            )
            for index, (question_type, criterion_id, evidence_chunk_ids) in enumerate(specs, start=1)
        ],
        ambiguity_sources=[],
    )
    questions = [
        _question(index, question_type, criterion_id, evidence_chunk_ids)
        for index, (question_type, criterion_id, evidence_chunk_ids) in enumerate(specs, start=1)
    ]
    service = object.__new__(AnalysisService)

    question_set = service._build_question_set_from_split(
        report=report,
        blueprint=blueprint,
        batches=[QuestionBatch(formal_questions=questions[:5]), QuestionBatch(formal_questions=questions[5:])],
        followups=AmbiguityFollowupSet(
            ambiguity_followups=[
                _question(11, "gap_validation", "c1", []),
                _question(12, "gap_validation", "c1", []),
                _question(13, "gap_validation", "c3", []),
            ]
        ),
    )

    primary_counts = Counter(
        question.evidence_chunk_ids[0]
        for question in question_set.formal_questions
        if question.evidence_chunk_ids
    )
    assert sum(primary_counts.values()) == 8
    assert max(primary_counts.values()) <= 3


@pytest.mark.asyncio
async def test_question_generation_validation_error_returns_bad_request(monkeypatch):
    class FailingAnalysisService:
        def __init__(self, *, db):
            pass

        def generate_questions(self, **_kwargs):
            raise ValueError("evidence chunk overused: e1")

    monkeypatch.setattr(runs_route, "AnalysisService", FailingAnalysisService)

    with pytest.raises(HTTPException) as exc_info:
        await runs_route.generate_candidate_questions(
            run_id=1,
            candidate_id=2,
            current_user=SimpleNamespace(id=3),
            db=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "evidence chunk overused: e1"
