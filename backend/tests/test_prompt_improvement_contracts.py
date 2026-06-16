from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.graph.candidate_workflow import CandidateAnalysisGraph
from backend.agents.harness import AgentHarness
from backend.schemas.workflow import (
    AmbiguityFollowupSet,
    Criterion,
    EvidenceChunk,
    JobProfile,
    MatchEvaluation,
    QuestionSet,
    ResumeProfile,
)
from backend.services.analysis import AnalysisService
from backend.services.documents import DocumentChunk


def _job_profile() -> JobProfile:
    return JobProfile(
        job_title="Backend Engineer",
        summary="Build APIs",
        responsibilities=["Build reliable APIs"],
        criteria=[
            Criterion(
                criterion_id="criterion_01",
                name="Python APIs",
                description="Build Python API services",
                importance="must",
                weight=60,
                evidence_query="Python; FastAPI; API services",
            ),
            Criterion(
                criterion_id="criterion_02",
                name="Vector search",
                description="Use vector retrieval systems",
                importance="important",
                weight=40,
                evidence_query="Milvus; vector retrieval; RAG",
            ),
        ],
    )


def _evidence() -> dict[str, list[dict]]:
    api = EvidenceChunk(
        chunk_id="api-1",
        filename="resume.pdf",
        page_number=1,
        section="Projects",
        text="Built FastAPI services for resume analysis.",
        score=0.91,
    )
    vector = EvidenceChunk(
        chunk_id="vec-1",
        filename="resume.pdf",
        page_number=2,
        section="Projects",
        text="Implemented Milvus vector retrieval and RAG filtering.",
        score=0.88,
    )
    return {
        "criterion_01": [api.model_dump(mode="json")],
        "criterion_02": [vector.model_dump(mode="json")],
    }


def test_match_schema_accepts_evidence_chunk_ids_not_full_evidence():
    evaluation = MatchEvaluation(
        evaluations=[
            {
                "criterion_id": "criterion_01",
                "name": "Python APIs",
                "weight": 60,
                "score": 4,
                "status": "match",
                "reason": "Direct API implementation evidence.",
                "evidence_chunk_ids": ["api-1"],
                "missing_evidence": ["scale"],
                "risk": "",
            },
            {
                "criterion_id": "criterion_02",
                "name": "Vector search",
                "weight": 40,
                "score": 0,
                "status": "no_evidence",
                "reason": "No supplied evidence supports this criterion.",
                "evidence_chunk_ids": [],
                "missing_evidence": ["Milvus experience"],
                "risk": "",
            },
        ]
    )

    assert evaluation.evaluations[0].evidence_chunk_ids == ["api-1"]
    assert "evidence" not in MatchEvaluation.model_json_schema()["$defs"]["CriterionEvaluation"]["properties"]


def test_score_status_and_evidence_state_are_strictly_validated():
    with pytest.raises(ValueError, match="score/status mismatch"):
        MatchEvaluation(
            evaluations=[
                {
                    "criterion_id": "criterion_01",
                    "name": "Python APIs",
                    "weight": 60,
                    "score": 5,
                    "status": "partial_match",
                    "reason": "bad mapping",
                    "evidence_chunk_ids": ["api-1"],
                }
            ]
        )
    with pytest.raises(ValueError, match="score=0 requires empty evidence"):
        MatchEvaluation(
            evaluations=[
                {
                    "criterion_id": "criterion_01",
                    "name": "Python APIs",
                    "weight": 60,
                    "score": 0,
                    "status": "no_evidence",
                    "reason": "bad evidence",
                    "evidence_chunk_ids": ["api-1"],
                }
            ]
        )


def test_hydrate_match_evaluation_drops_cross_criterion_chunk_and_downgrades_empty_match():
    from backend.services import llm_validation

    assert hasattr(llm_validation, "hydrate_match_evaluation")
    hydrate_match_evaluation = llm_validation.hydrate_match_evaluation

    raw = MatchEvaluation(
        evaluations=[
            {
                "criterion_id": "criterion_01",
                "name": "Python APIs",
                "weight": 60,
                "score": 4,
                "status": "match",
                "reason": "Direct API implementation evidence.",
                "evidence_chunk_ids": ["api-1"],
            },
            {
                "criterion_id": "criterion_02",
                "name": "Vector search",
                "weight": 40,
                "score": 3,
                "status": "partial_match",
                "reason": "Direct vector retrieval evidence.",
                "evidence_chunk_ids": ["vec-1"],
            },
        ]
    )

    hydrated = hydrate_match_evaluation(_job_profile(), raw, _evidence())

    assert hydrated[0].evidence[0].text == "Built FastAPI services for resume analysis."
    assert hydrated[1].evidence[0].section == "Projects"

    raw.evaluations[1].evidence_chunk_ids = ["api-1"]
    hydrated = hydrate_match_evaluation(_job_profile(), raw, _evidence())

    assert hydrated[1].score == 0
    assert hydrated[1].status == "no_evidence"
    assert hydrated[1].evidence_chunk_ids == []
    assert hydrated[1].evidence == []


def test_hydrate_match_evaluation_rejects_missing_or_reordered_criteria():
    from backend.services import llm_validation

    assert hasattr(llm_validation, "hydrate_match_evaluation")
    hydrate_match_evaluation = llm_validation.hydrate_match_evaluation

    raw = MatchEvaluation(
        evaluations=[
            {
                "criterion_id": "criterion_02",
                "name": "Vector search",
                "weight": 40,
                "score": 3,
                "status": "partial_match",
                "reason": "Direct vector retrieval evidence.",
                "evidence_chunk_ids": ["vec-1"],
            },
            {
                "criterion_id": "criterion_01",
                "name": "Python APIs",
                "weight": 60,
                "score": 4,
                "status": "match",
                "reason": "Direct API implementation evidence.",
                "evidence_chunk_ids": ["api-1"],
            },
        ]
    )

    with pytest.raises(ValueError, match="criterion set/order mismatch"):
        hydrate_match_evaluation(_job_profile(), raw, _evidence())


def test_resume_source_refs_must_match_input_chunks_verbatim():
    from backend.services import llm_validation

    assert hasattr(llm_validation, "validate_resume_source_refs")
    validate_resume_source_refs = llm_validation.validate_resume_source_refs

    profile = ResumeProfile(
        candidate_name="Ada Lovelace",
        source_refs=[
            {
                "chunk_id": "resume-1",
                "page_number": 1,
                "section": "Summary",
                "text": "Ada Lovelace",
            }
        ],
    )
    chunks = [
        DocumentChunk(
            id="resume-1",
            run_id=0,
            candidate_id=1,
            document_type="resume",
            filename="resume.pdf",
            page_number=1,
            section="Summary",
            chunk_index=0,
            text="Ada Lovelace\nPython engineer",
            metadata={},
        )
    ]

    validate_resume_source_refs(profile, chunks)
    profile.source_refs[0].text = "Ada Byron"
    with pytest.raises(ValueError, match="non-verbatim source text"):
        validate_resume_source_refs(profile, chunks)


def test_resume_source_refs_preserve_llm_section_when_valid():
    from backend.services import llm_validation

    validate_resume_source_refs = llm_validation.validate_resume_source_refs

    profile = ResumeProfile(
        candidate_name="Ada Lovelace",
        source_refs=[
            {
                "chunk_id": "resume-1",
                "page_number": 1,
                "section": "Candidate Summary",
                "text": "Ada Lovelace",
            }
        ],
    )
    chunks = [
        DocumentChunk(
            id="resume-1",
            run_id=0,
            candidate_id=1,
            document_type="resume",
            filename="resume.pdf",
            page_number=1,
            section="Summary",
            chunk_index=0,
            text="Ada Lovelace\nPython engineer",
            metadata={},
        )
    ]

    validate_resume_source_refs(profile, chunks)

    assert profile.source_refs[0].section == "Candidate Summary"


def test_resume_source_refs_reject_non_contiguous_or_repaired_source_quote():
    from backend.services import llm_validation

    validate_resume_source_refs = llm_validation.validate_resume_source_refs

    profile = ResumeProfile(
        candidate_name="Ada Lovelace",
        source_refs=[
            {
                "chunk_id": "resume-1",
                "page_number": 2,
                "section": "Awards",
                "text": "校级创业大赛二等奖",
            }
        ],
    )
    chunks = [
        DocumentChunk(
            id="resume-1",
            run_id=0,
            candidate_id=1,
            document_type="resume",
            filename="resume.pdf",
            page_number=2,
            section="Awards",
            chunk_index=0,
            text="项目最终获得校级创业大赛二等塡n奖。",
            metadata={},
        )
    ]

    with pytest.raises(ValueError, match="non-verbatim source text"):
        validate_resume_source_refs(profile, chunks)


def test_text_quality_gate_blocks_garbled_ocr_before_llm():
    from backend.services import documents

    assert hasattr(documents, "assert_acceptable_text_quality")
    assert_acceptable_text_quality = documents.assert_acceptable_text_quality

    with pytest.raises(ValueError, match="TEXT_QUALITY_TOO_LOW"):
        assert_acceptable_text_quality("锟斤拷" * 50 + "@@@@@@@" * 10, filename="resume.pdf")


def test_text_quality_gate_accepts_readable_chinese_jd_without_whitespace():
    from backend.services import documents

    assert_acceptable_text_quality = documents.assert_acceptable_text_quality
    jd_text = (
        "岗位职责负责后端服务开发接口设计数据库建模性能优化线上问题排查"
        "任职要求熟悉PythonFastAPIPostgreSQL具备良好沟通能力和工程质量意识"
        "能够独立推进需求落地并与产品前端测试协作完成交付"
        "参与系统架构演进代码评审自动化测试监控告警容量规划和技术文档沉淀"
        "关注安全合规稳定性可维护性并持续优化研发流程提升团队交付效率"
    )

    assert_acceptable_text_quality(jd_text, filename="jd-text.txt")


def test_multi_position_jd_is_detected_before_single_profile_parse():
    from backend.services import documents

    assert hasattr(documents, "detect_multiple_positions")
    detect_multiple_positions = documents.detect_multiple_positions

    jd_text = """
    职位一：新媒体运营（AI方向）
    岗位职责：负责内容运营。

    职位二：AI业务探索
    岗位职责：负责业务调研。
    """

    assert detect_multiple_positions(jd_text)


def test_question_split_uses_blueprint_two_batches_and_ambiguity_followups():
    from backend.schemas import workflow as workflow_schemas

    assert hasattr(workflow_schemas, "QuestionBlueprint")
    assert hasattr(workflow_schemas, "QuestionBlueprintItem")
    assert hasattr(workflow_schemas, "QuestionBatch")
    QuestionBlueprint = workflow_schemas.QuestionBlueprint
    QuestionBlueprintItem = workflow_schemas.QuestionBlueprintItem
    QuestionBatch = workflow_schemas.QuestionBatch

    job_profile = _job_profile()
    report = SimpleNamespace(
        job_profile=job_profile,
        resume_profile=ResumeProfile(candidate_name="Ada"),
        evaluations=[],
        total_score=0,
        recommendation="reject",
        model_dump=lambda **_kwargs: {},
        model_copy=lambda update: update,
    )
    blueprint = QuestionBlueprint(
        formal_questions=[
            QuestionBlueprintItem(
                question_id=f"q{i:02d}",
                question_type=question_type,
                primary_criterion_id="criterion_01" if i < 6 else "criterion_02",
                evidence_chunk_ids=["api-1"] if question_type != "gap_validation" else [],
                objective=f"objective {i}",
                difficulty="medium",
            )
            for i, question_type in enumerate(
                [
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
                ],
                start=1,
            )
        ],
        ambiguity_sources=[],
    )
    batch_1 = QuestionBatch(formal_questions=[])
    batch_2 = QuestionBatch(formal_questions=[])
    followups = AmbiguityFollowupSet.model_construct(ambiguity_followups=[])
    calls = []

    class Harness:
        def run_schema(self, *, task, schema, **_kwargs):
            calls.append((task, schema.__name__))
            if task == "plan_question_blueprint":
                return blueprint
            if task == "generate_question_batch" and len(calls) == 2:
                return batch_1
            if task == "generate_question_batch":
                return batch_2
            if task == "generate_ambiguity_followups":
                return followups
            raise AssertionError(task)

    service = object.__new__(AnalysisService)
    service.harness = Harness()
    service.repository = SimpleNamespace(
        get_candidate_report=lambda **_kwargs: report,
        save_questions=lambda **kwargs: kwargs["question_set"],
    )
    service._build_question_set_from_split = lambda **_kwargs: followups

    service.generate_questions(user_id=1, run_id=2, candidate_id=3)

    assert calls == [
        ("plan_question_blueprint", "QuestionBlueprint"),
        ("generate_question_batch", "QuestionBatch"),
        ("generate_question_batch", "QuestionBatch"),
        ("generate_ambiguity_followups", "AmbiguityFollowupSet"),
    ]


def test_prompt_templates_render_without_unresolved_placeholders():
    variables_by_prompt = {
        "parse_jd": {"jd_text": "Backend Engineer"},
        "parse_resume": {"filename": "resume.pdf", "chunks_json": []},
        "evaluate_match": {"criteria_json": [], "resume_profile_json": {}, "evidence_json": {}, "ambiguities_json": []},
        "plan_question_blueprint": {
            "report_json": {},
            "question_count": 10,
            "question_type_distribution": {
                "resume_experience": 3,
                "jd_core_capability": 2,
                "scenario_design": 2,
                "gap_validation": 2,
                "behavior_review": 1,
            },
        },
        "generate_question_batch": {
            "report_json": {},
            "blueprint_json": {"formal_questions": []},
            "existing_questions_json": [],
        },
        "generate_ambiguity_followups": {
            "report_json": {},
            "blueprint_json": {},
            "formal_questions_json": [],
        },
        "generate_followup": {
            "jd_context": {},
            "resume_context": {},
            "question_context": {},
            "history": [],
            "question": "What did you build?",
            "answer": "I built APIs.",
        },
    }

    for prompt_name, variables in variables_by_prompt.items():
        rendered = AgentHarness.render_prompt(AgentHarness.load_prompt(prompt_name), variables)
        assert "{{" not in rendered
        assert "}}" not in rendered
