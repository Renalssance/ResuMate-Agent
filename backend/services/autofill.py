from __future__ import annotations

from collections.abc import Iterable
from datetime import timezone
import re

from backend.db.models import Resume
from backend.schemas.autofill import (
    ApplicationField,
    ApplicationProfile,
    ApplicationSection,
    AutofillMatchResponse,
    BlockedElement,
    MatchSuggestion,
    PageElement,
)


def _utc_isoformat(value) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _join_lines(*values: str) -> str:
    return "\n".join(value.strip() for value in values if value and value.strip())


def _bullet_text(items: Iterable[dict]) -> str:
    lines = []
    for item in items or []:
        if isinstance(item, dict):
            raw = _text(item.get("raw_text") or item.get("description"))
            if raw:
                lines.append(raw)
    return "\n".join(lines)


def _field(key: str, label: str, value: str, aliases: list[str], category: str) -> ApplicationField:
    return ApplicationField(
        key=key,
        label=label,
        value=value,
        aliases=aliases,
        category=category,
        confidence="high" if value else "low",
        source="resume",
    )


def flatten_application_fields(profile: ApplicationProfile) -> list[ApplicationField]:
    return [field for section in profile.sections for field in section.fields]


def build_application_profile(resume: Resume) -> ApplicationProfile:
    data = resume.structured_data if isinstance(resume.structured_data, dict) else {}
    contact = data.get("contact") if isinstance(data.get("contact"), dict) else {}
    name = _text(data.get("candidate_name") or data.get("name") or resume.filename)
    sections: list[ApplicationSection] = [
        ApplicationSection(
            id="basic",
            label="Basic",
            fields=[
                _field("candidate_name", "Name", name, ["name", "full name", "姓名"], "basic"),
                _field("contact.email", "Email", _text(contact.get("email")), ["email", "邮箱"], "basic"),
                _field("contact.phone", "Phone", _text(contact.get("phone")), ["phone", "mobile", "手机"], "basic"),
                _field("contact.location", "City", _text(contact.get("location") or contact.get("city")), ["city", "location", "城市"], "basic"),
            ],
        )
    ]

    education_fields: list[ApplicationField] = []
    for index, item in enumerate(data.get("education") or []):
        if not isinstance(item, dict):
            continue
        number = index + 1
        prefix = f"education.{index}"
        education_fields.extend(
            [
                _field(f"{prefix}.school", f"School {number}", _text(item.get("school")), ["school", "university", "学校"], "education"),
                _field(f"{prefix}.degree", f"Degree {number}", _text(item.get("degree")), ["degree", "学位"], "education"),
                _field(f"{prefix}.major", f"Major {number}", _text(item.get("major")), ["major", "专业"], "education"),
                _field(f"{prefix}.years", f"Education Dates {number}", _text(item.get("years") or _join_lines(_text(item.get("start_date")), _text(item.get("end_date")))), ["education date", "graduation", "时间"], "education"),
            ]
        )
    sections.append(ApplicationSection(id="education", label="Education", fields=education_fields))

    work_fields: list[ApplicationField] = []
    work_items = data.get("work_experience") or data.get("experience") or []
    for index, item in enumerate(work_items):
        if not isinstance(item, dict):
            continue
        number = index + 1
        prefix = f"work_experience.{index}"
        description = _join_lines(_text(item.get("description")), _bullet_text(item.get("bullets") or []))
        work_fields.extend(
            [
                _field(f"{prefix}.company", f"Company {number}", _text(item.get("company")), ["company", "employer", "公司"], "work"),
                _field(f"{prefix}.title", f"Title {number}", _text(item.get("title")), ["title", "role", "position", "岗位"], "work"),
                _field(f"{prefix}.duration", f"Work Dates {number}", _text(item.get("duration")), ["work date", "employment period", "时间"], "work"),
                _field(f"{prefix}.description", f"Work Description {number}", description, ["work description", "experience", "职责"], "work"),
            ]
        )
    sections.append(ApplicationSection(id="work", label="Work Experience", fields=work_fields))

    project_fields: list[ApplicationField] = []
    for index, item in enumerate(data.get("projects") or []):
        if not isinstance(item, dict):
            continue
        number = index + 1
        prefix = f"projects.{index}"
        description = _join_lines(_text(item.get("description")), _bullet_text(item.get("bullets") or []))
        project_fields.extend(
            [
                _field(f"{prefix}.name", f"Project {number}", _text(item.get("name")), ["project", "项目"], "project"),
                _field(f"{prefix}.role", f"Project Role {number}", _text(item.get("role")), ["project role", "角色"], "project"),
                _field(f"{prefix}.description", f"Project Description {number}", description, ["project description", "项目描述"], "project"),
            ]
        )
    sections.append(ApplicationSection(id="projects", label="Projects", fields=project_fields))

    skills = ", ".join(_text(item.get("name") if isinstance(item, dict) else item) for item in data.get("skills") or [] if _text(item.get("name") if isinstance(item, dict) else item))
    sections.append(
        ApplicationSection(
            id="skills",
            label="Skills And Other",
            fields=[
                _field("skills", "Skills", skills, ["skills", "technical skills", "技能"], "skills"),
                _field("languages", "Languages", ", ".join(_text(item) for item in data.get("languages") or [] if _text(item)), ["languages", "语言"], "skills"),
                _field("certifications", "Certifications", ", ".join(_text(item) for item in data.get("certifications") or [] if _text(item)), ["certifications", "certificates", "证书"], "skills"),
                _field("self_summary", "Self Introduction", _text(data.get("self_summary")), ["self introduction", "summary", "自我介绍"], "summary"),
            ],
        )
    )

    return ApplicationProfile(
        id=f"resume:{resume.id}",
        name=name,
        source_resume_id=f"resume:{resume.id}",
        updated_at=_utc_isoformat(resume.updated_at),
        sections=sections,
    )


SENSITIVE_PATTERNS = [
    "password",
    "captcha",
    "verification",
    "verify code",
    "sms code",
    "one-time",
    "otp",
    "id card",
    "identity card",
    "national id",
    "bank card",
    "credit card",
    "密码",
    "验证码",
    "校验码",
    "身份证",
    "银行卡",
]


FIELD_KEYWORDS = {
    "candidate_name": ["name", "full name", "姓名", "名字"],
    "contact.email": ["email", "e-mail", "邮箱"],
    "contact.phone": ["phone", "mobile", "tel", "telephone", "手机", "电话"],
    "contact.location": ["city", "location", "current city", "城市", "所在地"],
    "skills": ["skills", "technical skills", "技能", "专业技能"],
    "languages": ["languages", "language", "语言"],
    "certifications": ["certifications", "certificate", "证书"],
    "self_summary": ["summary", "self introduction", "about me", "自我介绍", "个人介绍"],
}


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").lower()).strip()


def _element_text(element: PageElement) -> str:
    parts = [
        element.type,
        element.id,
        element.name,
        element.placeholder,
        element.label_text,
        element.aria_label,
        element.nearby_text,
    ]
    return _norm(" ".join(part for part in parts if part))


def is_sensitive_element(element: PageElement) -> bool:
    text = _element_text(element)
    if _norm(element.type) in {"password"}:
        return True
    return any(pattern in text for pattern in SENSITIVE_PATTERNS)


def _keywords_for_field(field: ApplicationField) -> list[str]:
    keywords = [field.key, field.label, *field.aliases]
    keywords.extend(FIELD_KEYWORDS.get(field.key, []))
    if field.key.startswith("education.") and field.key.endswith(".school"):
        keywords.extend(["school", "university", "学校"])
    if field.key.startswith("education.") and field.key.endswith(".major"):
        keywords.extend(["major", "专业"])
    if field.key.startswith("education.") and field.key.endswith(".degree"):
        keywords.extend(["degree", "学位"])
    if field.key.startswith("work_experience.") and field.key.endswith(".company"):
        keywords.extend(["company", "employer", "公司"])
    if field.key.startswith("work_experience.") and field.key.endswith(".title"):
        keywords.extend(["title", "role", "position", "岗位"])
    if field.key.endswith(".description"):
        keywords.extend(["description", "details", "介绍", "描述", "职责"])
    return [_norm(keyword) for keyword in keywords if _norm(keyword)]


def _score_field_for_element(field: ApplicationField, element: PageElement) -> tuple[int, str]:
    text = _element_text(element)
    if not text or not field.value:
        return 0, ""
    best = 0
    reason = ""
    for keyword in _keywords_for_field(field):
        if keyword == text:
            return 100, f'exact match on "{keyword}"'
        if keyword in text:
            if len(keyword) > best:
                best = len(keyword)
                reason = f'label contains "{keyword}"'
    return best, reason


def match_application_fields(profile: ApplicationProfile, elements: list[PageElement]) -> AutofillMatchResponse:
    fields = [field for field in flatten_application_fields(profile) if field.value]
    blocked: list[BlockedElement] = []
    candidates: list[tuple[int, int, ApplicationField, PageElement, str]] = []

    for element in elements:
        if is_sensitive_element(element):
            blocked.append(BlockedElement(element_index=element.index, reason="sensitive field", element=element))
            continue
        for field in fields:
            score, reason = _score_field_for_element(field, element)
            if score > 0:
                candidates.append((score, element.index, field, element, reason))

    matches: list[MatchSuggestion] = []
    used_fields: set[str] = set()
    used_elements: set[int] = set()
    for score, element_index, field, element, reason in sorted(candidates, key=lambda item: item[0], reverse=True):
        if field.key in used_fields or element_index in used_elements:
            continue
        confidence = "high" if score >= 2 else "medium"
        matches.append(
            MatchSuggestion(
                field_key=field.key,
                element_index=element_index,
                confidence=confidence,
                reason=reason,
                field=field,
                element=element,
            )
        )
        used_fields.add(field.key)
        used_elements.add(element_index)

    return AutofillMatchResponse(matches=sorted(matches, key=lambda item: item.element_index), blocked=blocked, warnings=[])
