from __future__ import annotations

from collections.abc import Iterable
from datetime import timezone

from backend.db.models import Resume
from backend.schemas.autofill import ApplicationField, ApplicationProfile, ApplicationSection


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
