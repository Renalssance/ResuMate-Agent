from __future__ import annotations

import json
from collections import Counter

from sqlalchemy.orm import Session

from backend.agents.harness import AgentHarness
from backend.db.models import JobDescription, Resume
from backend.graph.candidate_workflow import CandidateAnalysisGraph
from backend.rag.milvus import MilvusRagStore
from backend.repositories.runs import SqlAlchemyRunRepository
from backend.schemas.workflow import (
    AmbiguityFollowupSet,
    AnalyzeResponse,
    CandidateReport,
    InterviewQuestion,
    QuestionBatch,
    QuestionBlueprint,
    QuestionBlueprintItem,
    QuestionSet,
)
from backend.services.llm_validation import question_primary_evidence_limit, validate_question_set
from backend.services.progress import progress_hub


def parse_document_id(value: str, expected_type: str) -> int:
    prefix, separator, raw_id = value.partition(":")
    if separator != ":" or prefix != expected_type or not raw_id.isdigit():
        raise ValueError(f"invalid {expected_type} document id")
    return int(raw_id)


class AnalysisService:
    def __init__(
        self,
        *,
        db: Session,
        harness: AgentHarness | None = None,
        rag_store: MilvusRagStore | None = None,
    ) -> None:
        self.db = db
        self.harness = harness or AgentHarness()
        self.rag_store = rag_store or MilvusRagStore()
        self.repository = SqlAlchemyRunRepository(db)
        self.graph = CandidateAnalysisGraph(
            harness=self.harness,
            rag_store=self.rag_store,
            repository=self.repository,
        )

    def analyze_document_ids(
        self,
        *,
        user_id: int,
        jd_document_id: str,
        resume_document_ids: list[str],
        task_id: str = "",
    ) -> AnalyzeResponse:
        task_id = task_id or progress_hub.create_task("task_match")
        try:
            jd_id = parse_document_id(jd_document_id, "jd")
            resume_ids = [parse_document_id(value, "resume") for value in resume_document_ids]
        except ValueError as exc:
            progress_hub.publish(task_id, stage="failed", status="failed", progress=100, message=str(exc))
            raise
        jd = self.db.query(JobDescription).filter(JobDescription.id == jd_id, JobDescription.user_id == user_id).first()
        resumes = self.db.query(Resume).filter(Resume.id.in_(resume_ids), Resume.user_id == user_id).all()
        by_id = {resume.id: resume for resume in resumes}
        if not jd or len(by_id) != len(set(resume_ids)):
            progress_hub.publish(
                task_id,
                stage="failed",
                status="failed",
                progress=100,
                message="Selected documents do not exist or are not owned by the current user",
            )
            raise ValueError("selected documents do not exist or are not owned by the current user")
        progress_hub.publish(
            task_id,
            stage="load_jd",
            status="running",
            progress=5,
            message="Creating PostgreSQL analysis run",
            data={"jd_document_id": jd_document_id, "resume_count": len(resume_ids)},
        )
        job = self.repository.create_run(user_id=user_id, jd=jd, resumes=[by_id[item] for item in resume_ids])
        for candidate in job.candidates:
            resume = candidate.resume
            try:
                report = self.graph.run(
                    {
                        "user_id": user_id,
                        "run_id": job.id,
                        "candidate_id": candidate.id,
                        "jd_document_id": jd.id,
                        "resume_document_id": resume.id,
                        "filename": resume.filename,
                        "job": job,
                        "candidate": candidate,
                        "task_id": task_id,
                    }
                )
            except Exception as exc:
                self.repository.mark_candidate_failed(candidate, str(exc))
                progress_hub.publish(
                    task_id,
                    stage="failed",
                    status="failed",
                    progress=100,
                    message=f"{resume.filename}: {exc}",
                    data={"run_id": job.id, "candidate_id": candidate.id},
                )
                raise
        summary = self.repository.get_run(user_id=user_id, run_id=job.id)
        if not summary:
            progress_hub.publish(task_id, stage="failed", status="failed", progress=100, message="Analysis did not persist a run")
            raise RuntimeError("analysis did not persist a run")
        response = AnalyzeResponse(**summary.model_dump(), task_id=task_id)
        progress_hub.publish(
            task_id,
            stage="completed",
            status="success",
            progress=100,
            message="Match analysis completed",
            data=response.model_dump(mode="json", by_alias=True),
        )
        return response

    def generate_questions(self, *, user_id: int, run_id: int, candidate_id: int, task_id: str = "") -> CandidateReport:
        task_id = task_id or progress_hub.create_task("task_questions")
        progress_hub.publish(
            task_id,
            stage="load_context",
            status="running",
            progress=15,
            message="Loading persisted match report from PostgreSQL",
            data={"run_id": run_id, "candidate_id": candidate_id},
        )
        report = self.repository.get_candidate_report(
            user_id=user_id,
            run_id=run_id,
            candidate_id=candidate_id,
        )
        if not report:
            progress_hub.publish(task_id, stage="failed", status="failed", progress=100, message="Candidate report not found")
            raise ValueError("candidate report not found")
        progress_hub.publish(
            task_id,
            stage="retrieve_evidence",
            status="running",
            progress=30,
            message="Using cited match evidence for question context",
            data={"run_id": run_id, "candidate_id": candidate_id},
        )
        report_context = {
            "job_profile": report.job_profile.model_dump(mode="json"),
            "resume_profile": report.resume_profile.model_dump(mode="json"),
            "evaluations": [item.model_dump(mode="json") for item in report.evaluations],
            "total_score": report.total_score,
            "recommendation": report.recommendation,
        }
        progress_hub.publish(
            task_id,
            stage="analyze_gaps",
            status="running",
            progress=45,
            message="Preparing gaps and assessment focus for question generation",
            data={"run_id": run_id, "candidate_id": candidate_id},
        )
        progress_hub.publish(
            task_id,
            stage="generate_questions",
            status="running",
            progress=65,
            message="Generating interview questions with LLM",
            data={"run_id": run_id, "candidate_id": candidate_id},
        )
        try:
            # Split question generation into blueprint -> two batches -> follow-ups.
            # Smaller schema-constrained calls are more stable than asking the LLM
            # to produce the full interview pack in one long JSON response.
            blueprint = self.harness.run_schema(
                task="plan_question_blueprint",
                prompt_name="plan_question_blueprint",
                schema=QuestionBlueprint,
                task_id=task_id,
                progress_stage="generate_questions",
                progress=65,
                variables={"report_json": json.dumps(report_context, ensure_ascii=False)},
            )
            batch_1 = self.harness.run_schema(
                task="generate_question_batch",
                prompt_name="generate_question_batch",
                schema=QuestionBatch,
                task_id=task_id,
                progress_stage="generate_questions",
                progress=68,
                variables={
                    "report_json": json.dumps(report_context, ensure_ascii=False),
                    "blueprint_json": json.dumps(
                        {"formal_questions": [item.model_dump(mode="json") for item in blueprint.formal_questions[:5]]},
                        ensure_ascii=False,
                    ),
                    "existing_questions_json": "[]",
                },
            )
            batch_2 = self.harness.run_schema(
                task="generate_question_batch",
                prompt_name="generate_question_batch",
                schema=QuestionBatch,
                task_id=task_id,
                progress_stage="generate_questions",
                progress=72,
                variables={
                    "report_json": json.dumps(report_context, ensure_ascii=False),
                    "blueprint_json": json.dumps(
                        {"formal_questions": [item.model_dump(mode="json") for item in blueprint.formal_questions[5:]]},
                        ensure_ascii=False,
                    ),
                    "existing_questions_json": json.dumps(
                        [item.question for item in batch_1.formal_questions],
                        ensure_ascii=False,
                    ),
                },
            )
            followups = self.harness.run_schema(
                task="generate_ambiguity_followups",
                prompt_name="generate_ambiguity_followups",
                schema=AmbiguityFollowupSet,
                task_id=task_id,
                progress_stage="generate_questions",
                progress=76,
                variables={
                    "report_json": json.dumps(report_context, ensure_ascii=False),
                    "blueprint_json": json.dumps(blueprint.model_dump(mode="json"), ensure_ascii=False),
                    "formal_questions_json": json.dumps(
                        [item.model_dump(mode="json") for item in [*batch_1.formal_questions, *batch_2.formal_questions]],
                        ensure_ascii=False,
                    ),
                },
            )
            question_set = self._build_question_set_from_split(
                report=report,
                blueprint=blueprint,
                batches=[batch_1, batch_2],
                followups=followups,
            )
        except Exception as exc:
            progress_hub.publish(
                task_id,
                stage="failed",
                status="failed",
                progress=100,
                message=f"Question generation failed: {exc}",
                data={"run_id": run_id, "candidate_id": candidate_id},
            )
            raise
        progress_hub.publish(
            task_id,
            stage="rubric",
            status="running",
            progress=82,
            message="Validating question rubric and follow-up prompts",
            data={"run_id": run_id, "candidate_id": candidate_id},
        )
        try:
            updated = self.repository.save_questions(
                user_id=user_id,
                run_id=run_id,
                candidate_id=candidate_id,
                question_set=question_set,
            )
        except Exception as exc:
            progress_hub.publish(
                task_id,
                stage="failed",
                status="failed",
                progress=100,
                message=f"Question save failed: {exc}",
                data={"run_id": run_id, "candidate_id": candidate_id},
            )
            raise
        progress_hub.publish(
            task_id,
            stage="save",
            status="running",
            progress=94,
            message="Saving generated questions to PostgreSQL",
            data={"run_id": run_id, "candidate_id": candidate_id},
        )
        progress_hub.publish(
            task_id,
            stage="completed",
            status="success",
            progress=100,
            message="Question generation completed",
            data=updated.model_dump(mode="json"),
        )
        return updated

    def _build_question_set_from_split(
        self,
        *,
        report: CandidateReport,
        blueprint: QuestionBlueprint,
        batches: list[QuestionBatch],
        followups: AmbiguityFollowupSet,
    ) -> QuestionSet:
        formal_questions = [question for batch in batches for question in batch.formal_questions]
        allowed_evidence_ids = {chunk_id for item in report.evaluations for chunk_id in item.evidence_chunk_ids}
        gap_ids = {
            item.criterion_id
            for item in report.evaluations
            if item.score <= 2 or item.status in {"no_evidence", "conflict"} or item.missing_evidence
        }
        primary_evidence_limit = question_primary_evidence_limit(
            question_set=QuestionSet.model_construct(formal_questions=formal_questions, ambiguity_followups=[]),
            allowed_evidence_chunk_ids=allowed_evidence_ids,
        )
        # LLM output is a draft at this boundary. Normalize criterion aliases
        # and evidence IDs into the persisted report contract before applying
        # strict validation or saving.
        formal_questions = self._normalize_generated_questions(
            report=report,
            blueprint_items=blueprint.formal_questions,
            questions=formal_questions,
            gap_criterion_ids=gap_ids,
            primary_evidence_limit=primary_evidence_limit,
        )
        followup_questions = self._normalize_generated_questions(
            report=report,
            blueprint_items=[],
            questions=followups.ambiguity_followups,
            gap_criterion_ids=gap_ids,
            primary_evidence_limit=primary_evidence_limit,
        )
        question_set = QuestionSet(
            formal_questions=formal_questions,
            ambiguity_followups=followup_questions,
        )
        validate_question_set(
            question_set,
            job_profile=report.job_profile,
            allowed_evidence_chunk_ids=allowed_evidence_ids,
            gap_criterion_ids=gap_ids,
        )
        expected_ids = [item.question_id for item in blueprint.formal_questions]
        actual_count = len(formal_questions)
        if actual_count != len(expected_ids):
            raise ValueError(f"question batch count mismatch: expected {len(expected_ids)}, got {actual_count}")
        return question_set

    @staticmethod
    def _normalize_generated_questions(
        *,
        report: CandidateReport,
        blueprint_items: list[QuestionBlueprintItem],
        questions: list[InterviewQuestion],
        gap_criterion_ids: set[str],
        primary_evidence_limit: int = 2,
    ) -> list[InterviewQuestion]:
        criteria_by_id = {item.criterion_id: item for item in report.job_profile.criteria}
        criterion_id_by_alias = {
            AnalysisService._reference_key(item.criterion_id): item.criterion_id
            for item in report.job_profile.criteria
        }
        criterion_id_by_alias.update(
            {
                AnalysisService._reference_key(item.name): item.criterion_id
                for item in report.job_profile.criteria
            }
        )
        evidence_by_criterion = {
            item.criterion_id: item.evidence_chunk_ids
            for item in report.evaluations
        }
        report_evidence_ids = [
            chunk_id
            for item in report.evaluations
            for chunk_id in item.evidence_chunk_ids
        ]
        report_evidence_id_set = set(report_evidence_ids)
        primary_use_count: Counter[str] = Counter()
        normalized: list[InterviewQuestion] = []
        fallback_criterion_id = next(iter(criteria_by_id), "")
        fallback_gap_criterion_id = next(iter(gap_criterion_ids), "")
        for index, question in enumerate(questions):
            blueprint_item = blueprint_items[index] if index < len(blueprint_items) else None
            candidate_ids: list[str] = []

            def add_unique(values: list[str]) -> None:
                for value in values:
                    if value and value not in candidate_ids:
                        candidate_ids.append(value)

            if blueprint_item:
                add_unique(blueprint_item.evidence_chunk_ids)
            add_unique(question.evidence_chunk_ids)

            if blueprint_item:
                raw_criterion_ids = [
                    blueprint_item.primary_criterion_id,
                    *blueprint_item.secondary_criterion_ids,
                    *question.related_criteria,
                ]
            else:
                raw_criterion_ids = question.related_criteria

            criterion_ids = [
                criterion_id
                for criterion_id in (
                    criterion_id_by_alias.get(AnalysisService._reference_key(value), "")
                    for value in raw_criterion_ids
                )
                if criterion_id
            ]
            if question.question_type == "gap_validation" and gap_criterion_ids:
                criterion_ids = [criterion_id for criterion_id in criterion_ids if criterion_id in gap_criterion_ids]
                if not criterion_ids and blueprint_item and blueprint_item.primary_criterion_id in gap_criterion_ids:
                    criterion_ids = [blueprint_item.primary_criterion_id]
                if not criterion_ids and fallback_gap_criterion_id:
                    criterion_ids = [fallback_gap_criterion_id]
            if not criterion_ids and blueprint_item:
                criterion_ids = [blueprint_item.primary_criterion_id]
            if not criterion_ids and fallback_criterion_id:
                criterion_ids = [fallback_criterion_id]
            criterion_ids = list(dict.fromkeys(criterion_ids))

            if question.question_type == "gap_validation" and not candidate_ids:
                normalized.append(question.model_copy(update={"related_criteria": criterion_ids, "evidence_chunk_ids": []}))
                continue

            for criterion_id in criterion_ids:
                add_unique(evidence_by_criterion.get(criterion_id, []))
            candidate_ids = [chunk_id for chunk_id in candidate_ids if chunk_id in report_evidence_id_set]
            if question.question_type != "gap_validation" and not candidate_ids:
                add_unique(report_evidence_ids)

            primary = next((chunk_id for chunk_id in candidate_ids if primary_use_count[chunk_id] < primary_evidence_limit), "")
            if not primary and question.question_type != "gap_validation":
                add_unique(report_evidence_ids)
                primary = next((chunk_id for chunk_id in candidate_ids if primary_use_count[chunk_id] < primary_evidence_limit), "")
            if primary:
                secondary = next((chunk_id for chunk_id in candidate_ids if chunk_id != primary), "")
                selected_ids = [primary, *([secondary] if secondary else [])]
                question = question.model_copy(update={"related_criteria": criterion_ids, "evidence_chunk_ids": selected_ids})
                primary_use_count.update(selected_ids[:1])
            elif question.question_type == "gap_validation":
                question = question.model_copy(update={"related_criteria": criterion_ids, "evidence_chunk_ids": []})
            elif candidate_ids:
                selected_ids = candidate_ids[:2]
                question = question.model_copy(update={"related_criteria": criterion_ids, "evidence_chunk_ids": selected_ids})
                primary_use_count.update(selected_ids[:1])
            else:
                question = question.model_copy(update={"related_criteria": criterion_ids, "evidence_chunk_ids": []})
            normalized.append(question)
        return normalized

    @staticmethod
    def _reference_key(value: str) -> str:
        return " ".join((value or "").split()).casefold()
