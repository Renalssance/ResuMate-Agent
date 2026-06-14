from __future__ import annotations

import re
from collections import Counter
from typing import Any

from backend.schemas.workflow import ResumeProfile, SourceRef
from backend.services.documents import DocumentChunk


CONTACT_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"(?P<value>[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})", re.IGNORECASE),
    "phone": re.compile(
        r"(?P<value>(?:\+?\d{1,3}[- ]?)?(?:1[3-9]\d[- ]?\d{4}[- ]?\d{4}|\d{3,4}[- ]?\d{7,8}))"
    ),
    "wechat": re.compile(r"(?:Wechat|WeChat|微信)[:：\s]*(?P<value>[A-Za-z][A-Za-z0-9_-]{5,19})", re.IGNORECASE),
    "github": re.compile(r"(?P<value>https?://github\.com/[A-Za-z0-9_.-]+|github[:：\s]+[A-Za-z0-9_.-]+)", re.IGNORECASE),
    "linkedin": re.compile(r"(?P<value>https?://(?:www\.)?linkedin\.com/in/[A-Za-z0-9_.%-]+)", re.IGNORECASE),
    "homepage": re.compile(r"(?P<value>https?://(?!github\.com|(?:www\.)?linkedin\.com)\S+)", re.IGNORECASE),
    "address": re.compile(r"(?:Address|地址|City|城市)[:：\s]*(?P<value>[^\n;；]+)", re.IGNORECASE),
}

LEVEL_PRIORITY = {"mentioned": 0, "course_only": 1, "self_claimed": 2, "demonstrated": 3}
CLAIM_WORDS = ("proficient", "familiar", "skilled", "expert", "master", "精通", "熟悉", "熟练", "了解", "掌握")
COURSE_WORDS = ("course", "courses", "coursework", "课程")
WORK_SECTION_HINTS = ("experience", "project", "work", "research", "实习", "工作", "项目", "科研")
SKILL_SECTION_HINTS = ("skill", "professional", "技能")


def postprocess_resume_profile(profile: ResumeProfile, chunks: list[DocumentChunk]) -> ResumeProfile:
    """Apply deterministic resume parsing fixes after LLM extraction."""

    processed = profile.model_copy(deep=True)
    _sanitize_source_refs(processed, chunks)
    contact_refs = _merge_contact(processed, chunks)
    _fill_descriptions(processed)
    _normalize_skill_evidence(processed, chunks)
    _dedupe_structured_ambiguities(processed, chunks)
    processed.quality = _build_quality(processed, chunks)
    if contact_refs:
        processed.structured_ambiguities.append(
            {"type": "contact_extraction", "contact_source_refs": contact_refs}
        )
    return processed


def _sanitize_source_refs(profile: ResumeProfile, chunks: list[DocumentChunk]) -> None:
    chunk_map = {chunk.id: chunk for chunk in chunks}
    dropped: list[dict[str, Any]] = []

    def clean(refs: list[SourceRef]) -> list[SourceRef]:
        valid: list[SourceRef] = []
        for ref in refs:
            chunk = chunk_map.get(ref.chunk_id)
            if (
                chunk is not None
                and ref.page_number == chunk.page_number
                and _canonical_ws(ref.text) in _canonical_ws(chunk.text)
            ):
                valid.append(ref)
                continue
            dropped.append(
                {
                    "type": "dropped_non_verbatim_source_ref",
                    "chunk_id": ref.chunk_id,
                    "page_number": ref.page_number,
                    "section": ref.section,
                    "text": ref.text,
                }
            )
        return valid

    profile.source_refs = clean(profile.source_refs)
    for item in [*profile.education, *profile.work_experience, *profile.projects]:
        item.source_refs = clean(item.source_refs)
    for item in profile.work_experience:
        for bullet in item.bullets:
            bullet.source_refs = clean(bullet.source_refs)
    for item in profile.projects:
        for bullet in item.bullets:
            bullet.source_refs = clean(bullet.source_refs)
    for item in [*profile.skills, *profile.achievements]:
        item.source_refs = clean(item.source_refs)
    profile.structured_ambiguities.extend(dropped)


def _canonical_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _merge_contact(profile: ResumeProfile, chunks: list[DocumentChunk]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    extracted: dict[str, tuple[str, SourceRef]] = {}
    for chunk in chunks:
        for field, pattern in CONTACT_PATTERNS.items():
            if field in extracted:
                continue
            match = pattern.search(chunk.text)
            if not match:
                continue
            value = match.group("value").strip().rstrip(".,;；")
            quote = match.group(0).strip()
            extracted[field] = (
                value,
                SourceRef(page_number=chunk.page_number, section=chunk.section, text=quote, chunk_id=chunk.id),
            )

    for field, (value, ref) in extracted.items():
        existing = str(profile.contact.get(field) or "").strip()
        if existing and existing != value:
            profile.structured_ambiguities.append(
                {
                    "type": "contact_conflict",
                    "field": field,
                    "llm_value": existing,
                    "rule_value": value,
                    "source_refs": [ref.model_dump(mode="json")],
                }
            )
            continue
        if not existing:
            profile.contact[field] = value
        refs.append({"field": field, "source_refs": [ref.model_dump(mode="json")]})
    return refs


def _fill_descriptions(profile: ResumeProfile) -> None:
    for item in [*profile.work_experience, *profile.projects]:
        bullet_texts = [bullet.raw_text.strip() for bullet in item.bullets if bullet.raw_text.strip()]
        if bullet_texts:
            item.description = "\n".join(bullet_texts)


def _normalize_skill_evidence(profile: ResumeProfile, chunks: list[DocumentChunk]) -> None:
    for skill in profile.skills:
        name = skill.name.strip()
        if not name:
            continue
        level, claim = _classify_skill(name, chunks)
        if LEVEL_PRIORITY[level] >= LEVEL_PRIORITY.get(skill.evidence_level, 0):
            skill.evidence_level = level
        if claim and not skill.proficiency_claim:
            skill.proficiency_claim = claim


def _classify_skill(skill_name: str, chunks: list[DocumentChunk]) -> tuple[str, str]:
    normalized_skill = _canonical_skill(skill_name)
    best = "mentioned"
    claim = ""
    for chunk in chunks:
        if normalized_skill not in _canonical_text(chunk.text):
            continue
        section = (chunk.section or "").casefold()
        text = chunk.text.casefold()
        if any(word in section for word in WORK_SECTION_HINTS):
            best = _higher_level(best, "demonstrated")
        if any(word in section for word in SKILL_SECTION_HINTS) or any(word in text for word in CLAIM_WORDS):
            best = _higher_level(best, "self_claimed")
            claim = claim or _first_claim_word(chunk.text)
        if any(word in section for word in ("education", "教育")) or any(word in text for word in COURSE_WORDS):
            best = _higher_level(best, "course_only")
    return best, claim


def _higher_level(left: str, right: str) -> str:
    return right if LEVEL_PRIORITY[right] > LEVEL_PRIORITY.get(left, 0) else left


def _first_claim_word(text: str) -> str:
    lowered = text.casefold()
    for word in CLAIM_WORDS:
        if word.casefold() in lowered:
            return word
    return ""


def _canonical_skill(value: str) -> str:
    return _canonical_text(_skill_alias(value))


def _canonical_text(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", (value or "").casefold())


def _skill_alias(value: str) -> str:
    compact = re.sub(r"[\s_-]+", "", value or "").casefold()
    aliases = {
        "k8s": "kubernetes",
        "kubernetes": "kubernetes",
        "springboot": "springboot",
        "spring": "spring",
        "postgres": "postgresql",
        "postgresql": "postgresql",
    }
    return aliases.get(compact, value)


def _dedupe_structured_ambiguities(profile: ResumeProfile, chunks: list[DocumentChunk]) -> None:
    seen: set[tuple[Any, ...]] = set()
    deduped = []
    for item in [*profile.structured_ambiguities, *_document_ambiguities(chunks)]:
        key = (
            item.get("page_number"),
            item.get("type"),
            item.get("text") or item.get("raw_text"),
            item.get("start"),
            item.get("end"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    profile.structured_ambiguities = deduped


def _document_ambiguities(chunks: list[DocumentChunk]) -> list[dict[str, Any]]:
    results = []
    seen: set[tuple[Any, ...]] = set()
    for chunk in chunks:
        for item in chunk.metadata.get("ocr_ambiguities") or []:
            entry = dict(item)
            entry.setdefault("page_number", chunk.page_number)
            entry.setdefault("ambiguity_id", f"ocr:p{chunk.page_number}:{entry.get('start', 0)}:{entry.get('end', 0)}")
            key = (
                entry.get("page_number"),
                entry.get("type"),
                entry.get("text") or entry.get("raw_text"),
                entry.get("start"),
                entry.get("end"),
            )
            if key not in seen:
                seen.add(key)
                results.append(entry)
    return results


def _build_quality(profile: ResumeProfile, chunks: list[DocumentChunk]) -> dict[str, Any]:
    source_ref_count = sum(1 for _ in _iter_source_refs(profile))
    referenced = {ref.chunk_id for ref in _iter_source_refs(profile)}
    missing = []
    if not profile.candidate_name:
        missing.append("candidate_name")
    if _raw_has_contact(chunks) and not profile.contact:
        missing.append("contact")
    warning_count = len(_document_ambiguities(chunks))
    cross_page_warning = any(chunk.metadata.get("page_start") != chunk.metadata.get("page_end") for chunk in chunks)
    status = "success"
    if missing or cross_page_warning or warning_count:
        status = "success_with_warnings"
    return {
        "parse_completeness": 1.0 if not missing else 0.75,
        "source_ref_coverage": round(len(referenced) / max(len(chunks), 1), 4),
        "ocr_warning_count": warning_count,
        "unresolved_ambiguity_count": len(profile.structured_ambiguities),
        "contact_extracted": bool(profile.contact),
        "cross_page_reference_warning": cross_page_warning,
        "missing_required_fields": missing,
        "status": status,
        "source_ref_count": source_ref_count,
        "chunk_count": len(chunks),
        "evidence_level_distribution": dict(Counter(skill.evidence_level for skill in profile.skills)),
    }


def _iter_source_refs(profile: ResumeProfile):
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


def _raw_has_contact(chunks: list[DocumentChunk]) -> bool:
    text = "\n".join(chunk.text for chunk in chunks)
    return bool(CONTACT_PATTERNS["email"].search(text) or CONTACT_PATTERNS["phone"].search(text))
