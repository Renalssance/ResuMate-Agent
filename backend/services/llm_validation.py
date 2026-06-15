from __future__ import annotations

import re
from collections import Counter
from math import ceil
from typing import Iterable

from backend.schemas.workflow import (
    EvidenceChunk,
    HydratedCriterionEvaluation,
    JobProfile,
    MatchEvaluation,
    QuestionSet,
    ResumeProfile,
    SourceRef,
)
from backend.services.documents import DocumentChunk


def _canonicalize_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _iter_source_refs(profile: ResumeProfile) -> Iterable[SourceRef]:
    yield from profile.source_refs
    for item in [*profile.education, *profile.work_experience, *profile.projects]:
        yield from item.source_refs
    for item in profile.work_experience:
        for bullet in item.bullets:
            yield from bullet.source_refs
    for item in profile.projects:
        for bullet in item.bullets:
            yield from bullet.source_refs
    for item in [*profile.skills, *profile.achievements]:
        yield from item.source_refs


def validate_resume_source_refs(profile: ResumeProfile, chunks: list[DocumentChunk]) -> None:
    chunk_map = {chunk.id: chunk for chunk in chunks}
    for ref in _iter_source_refs(profile):
        source = chunk_map.get(ref.chunk_id)
        if source is None:
            raise ValueError(f"unknown chunk_id: {ref.chunk_id}")
        if ref.page_number != source.page_number:
            raise ValueError(f"page mismatch: {ref.chunk_id}")
        if _canonicalize_ws(ref.text) not in _canonicalize_ws(source.text):
            raise ValueError(f"non-verbatim source text: {ref.chunk_id}")


def hydrate_match_evaluation(
    job_profile: JobProfile,
    evaluation: MatchEvaluation,
    evidence_by_criterion: dict[str, list[dict]],
) -> list[HydratedCriterionEvaluation]:
    expected_ids = [criterion.criterion_id for criterion in job_profile.criteria]
    actual_ids = [item.criterion_id for item in evaluation.evaluations]
    if actual_ids != expected_ids:
        raise ValueError("criterion set/order mismatch")

    hydrated: list[HydratedCriterionEvaluation] = []
    criteria_by_id = {criterion.criterion_id: criterion for criterion in job_profile.criteria}
    for item in evaluation.evaluations:
        criterion = criteria_by_id[item.criterion_id]
        if item.name != criterion.name or item.weight != criterion.weight:
            raise ValueError(f"criterion identity mismatch: {item.criterion_id}")
        allowed_chunks = {
            chunk["chunk_id"]: EvidenceChunk.model_validate(chunk)
            for chunk in evidence_by_criterion.get(item.criterion_id, [])
        }
        selected_ids = [chunk_id for chunk_id in item.evidence_chunk_ids if chunk_id in allowed_chunks]
        payload = item.model_dump(mode="json")
        payload["evidence_chunk_ids"] = selected_ids
        if item.score > 0 and not selected_ids:
            payload["score"] = 0
            payload["status"] = "no_evidence"
        hydrated.append(
            HydratedCriterionEvaluation(
                **payload,
                evidence=[allowed_chunks[chunk_id] for chunk_id in selected_ids],
            )
        )
    return hydrated


def validate_question_set(
    question_set: QuestionSet,
    *,
    job_profile: JobProfile,
    allowed_evidence_chunk_ids: set[str],
    gap_criterion_ids: set[str],
) -> None:
    criterion_ids = {criterion.criterion_id for criterion in job_profile.criteria}
    seen_questions: set[str] = set()
    evidence_use_count: Counter[str] = Counter()
    primary_evidence_limit = question_primary_evidence_limit(
        question_set=question_set,
        allowed_evidence_chunk_ids=allowed_evidence_chunk_ids,
    )
    for question in question_set.formal_questions:
        normalized = _canonicalize_ws(question.question).casefold()
        if normalized in seen_questions:
            raise ValueError("duplicate interview question")
        seen_questions.add(normalized)
        if not set(question.related_criteria) <= criterion_ids:
            raise ValueError("question references unknown criterion")
        if not set(question.evidence_chunk_ids) <= allowed_evidence_chunk_ids:
            raise ValueError("question evidence outside candidate report")
        if allowed_evidence_chunk_ids and question.question_type != "gap_validation" and not question.evidence_chunk_ids:
            raise ValueError("non-gap question requires evidence")
        if gap_criterion_ids and question.question_type == "gap_validation" and not set(question.related_criteria) <= gap_criterion_ids:
            raise ValueError("gap question must target low-score or missing-evidence criteria")
        evidence_use_count.update(question.evidence_chunk_ids[:1])
    overused = [chunk_id for chunk_id, count in evidence_use_count.items() if count > primary_evidence_limit]
    if overused:
        raise ValueError(f"evidence chunk overused: {overused[0]}")


def question_primary_evidence_limit(
    *,
    question_set: QuestionSet,
    allowed_evidence_chunk_ids: set[str],
) -> int:
    evidence_required_count = sum(
        1
        for question in question_set.formal_questions
        if question.question_type != "gap_validation"
    )
    if not allowed_evidence_chunk_ids:
        return 2
    return max(2, ceil(evidence_required_count / len(allowed_evidence_chunk_ids)))
