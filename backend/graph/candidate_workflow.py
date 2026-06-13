from __future__ import annotations

import json
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from backend.agents.harness import AgentHarness
from backend.rag.milvus import MilvusRagStore
from backend.repositories.runs import run_repository
from backend.schemas.workflow import (
    CandidateReport,
    CriterionEvaluation,
    JobProfile,
    MatchEvaluation,
    QuestionSet,
    Recommendation,
    ResumeProfile,
)
from backend.services.documents import DocumentChunk


class CandidateState(TypedDict, total=False):
    run_id: str
    candidate_id: str
    filename: str
    jd_chunks: list[DocumentChunk]
    resume_chunks: list[DocumentChunk]
    job_profile: JobProfile
    resume_profile: ResumeProfile
    evidence_by_criterion: dict[str, list[dict[str, Any]]]
    evaluation: MatchEvaluation
    total_score: float
    recommendation: Recommendation
    question_set: QuestionSet
    report: CandidateReport


def calculate_total_score(evaluations: list[CriterionEvaluation]) -> float:
    total = sum(item.weight * item.score / 5 for item in evaluations)
    return round(max(0, min(100, total)), 2)


def recommendation_for_score(score: float) -> Recommendation:
    if score >= 80:
        return "strong_recommend"
    if score >= 65:
        return "recommend"
    if score >= 50:
        return "hold"
    return "reject"


class CandidateAnalysisGraph:
    def __init__(self, *, harness: AgentHarness, rag_store: MilvusRagStore) -> None:
        self.harness = harness
        self.rag_store = rag_store
        self.graph = self._build_graph()

    def run(self, state: CandidateState) -> CandidateReport:
        result = self.graph.invoke(state)
        return result["report"]

    def _build_graph(self):
        builder = StateGraph(CandidateState)
        builder.add_node("load_documents", self.load_documents)
        builder.add_node("index_documents", self.index_documents)
        builder.add_node("parse_jd", self.parse_jd)
        builder.add_node("parse_resume", self.parse_resume)
        builder.add_node("retrieve_evidence", self.retrieve_evidence)
        builder.add_node("evaluate_match", self.evaluate_match)
        builder.add_node("calculate_score", self.calculate_score)
        builder.add_node("generate_questions", self.generate_questions)
        builder.add_node("persist_report", self.persist_report)
        builder.set_entry_point("load_documents")
        builder.add_edge("load_documents", "index_documents")
        builder.add_edge("index_documents", "parse_jd")
        builder.add_edge("parse_jd", "parse_resume")
        builder.add_edge("parse_resume", "retrieve_evidence")
        builder.add_edge("retrieve_evidence", "evaluate_match")
        builder.add_edge("evaluate_match", "calculate_score")
        builder.add_edge("calculate_score", "generate_questions")
        builder.add_edge("generate_questions", "persist_report")
        builder.add_edge("persist_report", END)
        return builder.compile()

    def load_documents(self, state: CandidateState) -> CandidateState:
        if not state.get("jd_chunks") or not state.get("resume_chunks"):
            raise ValueError("jd_chunks and resume_chunks are required")
        return state

    def index_documents(self, state: CandidateState) -> CandidateState:
        self.rag_store.index_chunks(state["jd_chunks"])
        self.rag_store.index_chunks(state["resume_chunks"])
        return state

    def parse_jd(self, state: CandidateState) -> CandidateState:
        if state.get("job_profile"):
            return state
        jd_text = "\n\n".join(chunk.text for chunk in state["jd_chunks"])
        state["job_profile"] = self.harness.run_schema(
            task="parse_jd",
            prompt_name="parse_jd",
            schema=JobProfile,
            variables={"jd_text": jd_text[:24000]},
        )
        self.rag_store.persist_artifact(
            run_id=state["run_id"],
            candidate_id="",
            artifact_type="job_profile",
            summary=state["job_profile"].summary,
            content=state["job_profile"].model_dump(mode="json"),
        )
        return state

    def parse_resume(self, state: CandidateState) -> CandidateState:
        chunks_payload = [
            {
                "chunk_id": chunk.id,
                "page_number": chunk.page_number,
                "section": chunk.section,
                "text": chunk.text,
            }
            for chunk in state["resume_chunks"]
        ]
        state["resume_profile"] = self.harness.run_schema(
            task="parse_resume",
            prompt_name="parse_resume",
            schema=ResumeProfile,
            variables={"filename": state["filename"], "chunks_json": chunks_payload[:80]},
        )
        self.rag_store.persist_artifact(
            run_id=state["run_id"],
            candidate_id=state["candidate_id"],
            artifact_type="resume_profile",
            summary=state["resume_profile"].candidate_name,
            content=state["resume_profile"].model_dump(mode="json"),
        )
        return state

    def retrieve_evidence(self, state: CandidateState) -> CandidateState:
        evidence_by_criterion: dict[str, list[dict[str, Any]]] = {}
        for criterion in state["job_profile"].criteria:
            evidence = self.rag_store.search_resume_evidence(
                run_id=state["run_id"],
                candidate_id=state["candidate_id"],
                query=criterion.evidence_query,
                top_k=4,
            )
            evidence_by_criterion[criterion.criterion_id] = [item.model_dump(mode="json") for item in evidence]
        state["evidence_by_criterion"] = evidence_by_criterion
        return state

    def evaluate_match(self, state: CandidateState) -> CandidateState:
        criteria_payload = [item.model_dump(mode="json") for item in state["job_profile"].criteria]
        state["evaluation"] = self.harness.run_schema(
            task="evaluate_match",
            prompt_name="evaluate_match",
            schema=MatchEvaluation,
            variables={
                "criteria_json": criteria_payload,
                "evidence_json": state["evidence_by_criterion"],
            },
        )
        state["evaluation"] = MatchEvaluation(
            evaluations=self._align_evaluations(state["job_profile"], state["evaluation"])
        )
        return state

    def calculate_score(self, state: CandidateState) -> CandidateState:
        state["total_score"] = calculate_total_score(state["evaluation"].evaluations)
        state["recommendation"] = recommendation_for_score(state["total_score"])
        return state

    def generate_questions(self, state: CandidateState) -> CandidateState:
        report_context = {
            "job_profile": state["job_profile"].model_dump(mode="json"),
            "resume_profile": state["resume_profile"].model_dump(mode="json"),
            "evaluations": [item.model_dump(mode="json") for item in state["evaluation"].evaluations],
            "total_score": state["total_score"],
            "recommendation": state["recommendation"],
        }
        state["question_set"] = self.harness.run_schema(
            task="generate_questions",
            prompt_name="generate_questions",
            schema=QuestionSet,
            variables={"report_json": json.dumps(report_context, ensure_ascii=False)},
        )
        return state

    def persist_report(self, state: CandidateState) -> CandidateState:
        evaluations = state["evaluation"].evaluations
        strengths = [
            item.name
            for item in sorted(evaluations, key=lambda entry: (entry.score, entry.weight), reverse=True)
            if item.score >= 4
        ][:3]
        if not strengths:
            strengths = [item.name for item in sorted(evaluations, key=lambda entry: entry.score, reverse=True)[:3]]

        report = CandidateReport(
            run_id=state["run_id"],
            candidate_id=state["candidate_id"],
            candidate_name=state["resume_profile"].candidate_name,
            filename=state["filename"],
            job_profile=state["job_profile"],
            resume_profile=state["resume_profile"],
            evaluations=evaluations,
            total_score=state["total_score"],
            recommendation=state["recommendation"],
            top_strengths=strengths,
            summary=self._build_summary(state),
            formal_questions=state["question_set"].formal_questions,
            ambiguity_followups=state["question_set"].ambiguity_followups,
        )
        state["report"] = report
        run_repository.save_report(state["run_id"], report)
        self.rag_store.persist_artifact(
            run_id=state["run_id"],
            candidate_id=state["candidate_id"],
            artifact_type="candidate_report",
            summary=report.summary,
            content=report.model_dump(mode="json"),
        )
        return state

    @staticmethod
    def _align_evaluations(job_profile: JobProfile, evaluation: MatchEvaluation) -> list[CriterionEvaluation]:
        by_id = {item.criterion_id: item for item in evaluation.evaluations}
        aligned: list[CriterionEvaluation] = []
        for criterion in job_profile.criteria:
            item = by_id.get(criterion.criterion_id)
            if item is None:
                item = CriterionEvaluation(
                    criterion_id=criterion.criterion_id,
                    name=criterion.name,
                    weight=criterion.weight,
                    score=0,
                    status="no_evidence",
                    reason="No evaluation was returned for this criterion.",
                    evidence=[],
                    missing_evidence=["evaluation_missing"],
                    risk="The model did not evaluate this criterion.",
                )
            aligned.append(
                item.model_copy(
                    update={
                        "criterion_id": criterion.criterion_id,
                        "name": criterion.name,
                        "weight": criterion.weight,
                    }
                )
            )
        return aligned

    @staticmethod
    def _build_summary(state: CandidateState) -> str:
        return (
            f"{state['resume_profile'].candidate_name} matched {state['job_profile'].job_title} "
            f"with score {state['total_score']} and recommendation {state['recommendation']}."
        )
