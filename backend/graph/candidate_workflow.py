from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from backend.agents.harness import AgentHarness
from backend.rag.milvus import MilvusRagStore
from backend.repositories.runs import SqlAlchemyRunRepository
from backend.schemas.workflow import (
    CandidateReport,
    CriterionEvaluation,
    JobProfile,
    MatchEvaluation,
    Recommendation,
    ResumeProfile,
)
from backend.services.documents import DocumentChunk
from backend.services.llm_validation import hydrate_match_evaluation
from backend.services.progress import progress_hub


class CandidateState(TypedDict, total=False):
    user_id: int
    run_id: int
    candidate_id: int
    jd_document_id: int
    resume_document_id: int
    job: Any
    candidate: Any
    filename: str
    jd_chunks: list[DocumentChunk]
    resume_chunks: list[DocumentChunk]
    job_profile: JobProfile
    resume_profile: ResumeProfile
    evidence_by_criterion: dict[str, list[dict[str, Any]]]
    evaluation: MatchEvaluation
    total_score: float
    recommendation: Recommendation
    report: CandidateReport
    task_id: str


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
    def __init__(self, *, harness: AgentHarness, rag_store: MilvusRagStore, repository: SqlAlchemyRunRepository) -> None:
        self.harness = harness
        self.rag_store = rag_store
        self.repository = repository
        self.graph = self._build_graph()

    def run(self, state: CandidateState) -> CandidateReport:
        result = self.graph.invoke(state)
        return result["report"]

    def _build_graph(self):
        builder = StateGraph(CandidateState)
        builder.add_node("load_structured_profiles", self.load_structured_profiles)
        builder.add_node("retrieve_evidence", self.retrieve_evidence)
        builder.add_node("evaluate_match", self.evaluate_match)
        builder.add_node("calculate_score", self.calculate_score)
        builder.add_node("persist_report", self.persist_report)
        builder.set_entry_point("load_structured_profiles")
        # The LLM evaluates criterion-level evidence only; deterministic Python
        # code applies weighting and recommendation thresholds in later nodes.
        builder.add_edge("load_structured_profiles", "retrieve_evidence")
        builder.add_edge("retrieve_evidence", "evaluate_match")
        builder.add_edge("evaluate_match", "calculate_score")
        builder.add_edge("calculate_score", "persist_report")
        builder.add_edge("persist_report", END)
        return builder.compile()

    def load_structured_profiles(self, state: CandidateState) -> CandidateState:
        progress_hub.publish(
            state.get("task_id"),
            stage="load_jd",
            status="running",
            progress=10,
            message="Loading structured JD profile",
            data={"run_id": state.get("run_id"), "candidate_id": state.get("candidate_id")},
        )
        job_profile = self.rag_store.load_document_profile(
            user_id=state["user_id"],
            document_type="jd",
            document_id=state["jd_document_id"],
        )
        progress_hub.publish(
            state.get("task_id"),
            stage="load_resume",
            status="running",
            progress=20,
            message="Loading structured resume profile",
            data={"run_id": state.get("run_id"), "candidate_id": state.get("candidate_id")},
        )
        resume_profile = self.rag_store.load_document_profile(
            user_id=state["user_id"],
            document_type="resume",
            document_id=state["resume_document_id"],
        )
        if not job_profile or not resume_profile:
            raise ValueError("向量库中缺少结构化 JD 或简历，请先重新解析对应文档")
        state["job_profile"] = JobProfile.model_validate(job_profile)
        state["resume_profile"] = ResumeProfile.model_validate(resume_profile)
        return state

    def retrieve_evidence(self, state: CandidateState) -> CandidateState:
        progress_hub.publish(
            state.get("task_id"),
            stage="milvus_search",
            status="running",
            progress=35,
            message="Searching resume evidence in Milvus",
            data={"run_id": state.get("run_id"), "candidate_id": state.get("candidate_id")},
        )
        evidence_by_criterion: dict[str, list[dict[str, Any]]] = {}
        for criterion in state["job_profile"].criteria:
            evidence = self.rag_store.search_resume_evidence(
                user_id=state["user_id"],
                document_id=state["resume_document_id"],
                query=criterion.evidence_query,
                top_k=4,
            )
            evidence_by_criterion[criterion.criterion_id] = [item.model_dump(mode="json") for item in evidence]
        state["evidence_by_criterion"] = evidence_by_criterion
        return state

    def evaluate_match(self, state: CandidateState) -> CandidateState:
        progress_hub.publish(
            state.get("task_id"),
            stage="llm_match",
            status="running",
            progress=58,
            message="Evaluating JD-resume match with LLM",
            data={"run_id": state.get("run_id"), "candidate_id": state.get("candidate_id")},
        )
        criteria_payload = [item.model_dump(mode="json") for item in state["job_profile"].criteria]
        state["evaluation"] = self.harness.run_schema(
            task="evaluate_match",
            prompt_name="evaluate_match",
            schema=MatchEvaluation,
            variables={
                "criteria_json": criteria_payload,
                "resume_profile_json": state["resume_profile"].model_dump(mode="json"),
                "evidence_json": state["evidence_by_criterion"],
                "ambiguities_json": state["resume_profile"].structured_ambiguities,
            },
        )
        state["evaluation"] = MatchEvaluation(
            evaluations=hydrate_match_evaluation(
                state["job_profile"],
                state["evaluation"],
                state["evidence_by_criterion"],
            )
        )
        return state

    def calculate_score(self, state: CandidateState) -> CandidateState:
        progress_hub.publish(
            state.get("task_id"),
            stage="score",
            status="running",
            progress=72,
            message="Calculating weighted match score",
            data={"run_id": state.get("run_id"), "candidate_id": state.get("candidate_id")},
        )
        state["total_score"] = calculate_total_score(state["evaluation"].evaluations)
        state["recommendation"] = recommendation_for_score(state["total_score"])
        return state

    def persist_report(self, state: CandidateState) -> CandidateState:
        progress_hub.publish(
            state.get("task_id"),
            stage="vectorize",
            status="running",
            progress=84,
            message="Vectorizing candidate report artifact",
            data={"run_id": state.get("run_id"), "candidate_id": state.get("candidate_id")},
        )
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
            formal_questions=[],
            ambiguity_followups=[],
        )
        state["report"] = report
        self.repository.save_report(job=state["job"], candidate=state["candidate"], report=report)
        progress_hub.publish(
            state.get("task_id"),
            stage="milvus_save",
            status="running",
            progress=92,
            message="Saving match artifact to Milvus and report to PostgreSQL",
            data={"run_id": state.get("run_id"), "candidate_id": state.get("candidate_id")},
        )
        self.rag_store.persist_artifact(
            user_id=state["user_id"],
            run_id=state["run_id"],
            candidate_id=state["candidate_id"],
            artifact_type="candidate_report",
            summary=report.summary,
            content=report.model_dump(mode="json"),
        )
        return state

    @staticmethod
    def _build_summary(state: CandidateState) -> str:
        return (
            f"{state['resume_profile'].candidate_name} matched {state['job_profile'].job_title} "
            f"with score {state['total_score']} and recommendation {state['recommendation']}."
        )
