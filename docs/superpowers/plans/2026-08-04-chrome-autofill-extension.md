# Chrome Autofill Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Chrome MV3 extension that fills recruiting application forms from ResuMate profiles after user review, with backend-powered matching and local cache fallback.

**Architecture:** ResuMate backend exposes simplified autofill profiles and match suggestions. The Chrome extension scans the current page, asks the backend to match page elements to profile fields when available, falls back to local rules when offline, and fills only user-selected fields through a content script.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLAlchemy, pytest, Chrome Manifest V3, plain JavaScript, HTML, CSS, `chrome.storage`, `chrome.sidePanel`, `chrome.tabs`, `chrome.scripting`.

---

## Scope And File Map

Backend files:

- Create `backend/schemas/autofill.py`: Pydantic request/response models for profiles, page elements, matches, and events.
- Create `backend/services/autofill.py`: profile mapping, sensitive-field filtering, deterministic matching, and event sanitization.
- Create `backend/routes/autofill.py`: authenticated API endpoints.
- Modify `backend/routes/api.py`: include the autofill router.
- Modify `backend/schemas/__init__.py`: export autofill schema classes only if another module imports from the package root during implementation.
- Create `backend/tests/test_autofill_profile.py`: profile mapping tests.
- Create `backend/tests/test_autofill_matching.py`: deterministic matcher and sensitive filtering tests.
- Create `backend/tests/test_autofill_routes.py`: API route tests using dependency overrides.

Extension files:

- Create `extension/manifest.json`: MV3 metadata and permissions.
- Create `extension/service-worker.js`: side panel behavior and message routing.
- Create `extension/lib/constants.js`: storage keys, confidence labels, default backend URL, blocked input patterns.
- Create `extension/lib/storage.js`: `chrome.storage.local` wrapper.
- Create `extension/lib/api-client.js`: calls ResuMate autofill APIs.
- Create `extension/lib/field-matcher.js`: offline deterministic matcher.
- Create `extension/content/fill-engine.js`: scan and fill page form elements.
- Create `extension/content/scraper.js`: company and position scraping.
- Create `extension/sidepanel/sidepanel.html`: side panel shell.
- Create `extension/sidepanel/sidepanel.css`: quiet product UI styles.
- Create `extension/sidepanel/sidepanel.js`: profile loading, scanning, matching, review, and fill actions.
- Create `extension/fixtures/application-form.html`: local manual test page.
- Create `extension/README.md`: load and test instructions.

## Task 1: Backend Autofill Schemas

**Files:**
- Create: `backend/schemas/autofill.py`
- Test: `backend/tests/test_autofill_profile.py`

- [ ] **Step 1: Write failing schema tests**

Add `backend/tests/test_autofill_profile.py`:

```python
from backend.schemas.autofill import (
    ApplicationField,
    ApplicationProfile,
    AutofillMatchResponse,
    MatchSuggestion,
    PageElement,
)


def test_application_profile_serializes_with_camel_case_ids():
    profile = ApplicationProfile(
        id="resume:1",
        name="Ada Resume",
        source_resume_id="resume:1",
        updated_at="2026-08-04T00:00:00Z",
        sections=[
            {
                "id": "basic",
                "label": "Basic",
                "fields": [
                    {
                        "key": "candidate_name",
                        "label": "Name",
                        "value": "Ada Lovelace",
                        "aliases": ["full name"],
                        "category": "basic",
                        "confidence": "high",
                        "source": "resume",
                    }
                ],
            }
        ],
    )

    payload = profile.model_dump(mode="json", by_alias=True)

    assert payload["sourceResumeId"] == "resume:1"
    assert payload["sections"][0]["fields"][0]["key"] == "candidate_name"


def test_match_response_accepts_page_element_index():
    response = AutofillMatchResponse(
        matches=[
            MatchSuggestion(
                field_key="contact.email",
                element_index=2,
                confidence="high",
                reason="label contains email",
                field=ApplicationField(
                    key="contact.email",
                    label="Email",
                    value="ada@example.com",
                    aliases=["email address"],
                    category="basic",
                    confidence="high",
                    source="resume",
                ),
                element=PageElement(
                    index=2,
                    tag="input",
                    type="email",
                    id="email",
                    name="email",
                    placeholder="Email",
                    label_text="Email",
                ),
            )
        ],
        blocked=[],
        warnings=[],
    )

    assert response.matches[0].field_key == "contact.email"
    assert response.matches[0].element.index == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_autofill_profile.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'backend.schemas.autofill'`.

- [ ] **Step 3: Implement schema models**

Create `backend/schemas/autofill.py`:

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


Confidence = Literal["high", "medium", "low"]
AutofillEventType = Literal["scan", "match", "fill"]
AutofillEventStatus = Literal["success", "partial", "failed"]


class AutofillModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class ApplicationField(AutofillModel):
    key: str
    label: str
    value: str = ""
    aliases: list[str] = Field(default_factory=list)
    category: str = "general"
    confidence: Confidence = "medium"
    source: str = "resume"


class ApplicationSection(AutofillModel):
    id: str
    label: str
    fields: list[ApplicationField] = Field(default_factory=list)


class ApplicationProfile(AutofillModel):
    id: str
    name: str
    source_resume_id: str = Field(alias="sourceResumeId")
    updated_at: str = Field(alias="updatedAt")
    sections: list[ApplicationSection] = Field(default_factory=list)


class ApplicationProfileSummary(AutofillModel):
    id: str
    name: str
    source_resume_id: str = Field(alias="sourceResumeId")
    updated_at: str = Field(alias="updatedAt")
    field_count: int = Field(alias="fieldCount", ge=0)


class PageElement(AutofillModel):
    index: int = Field(ge=0)
    tag: str
    type: str = ""
    id: str = ""
    name: str = ""
    placeholder: str = ""
    label_text: str = Field(default="", alias="labelText")
    aria_label: str = Field(default="", alias="ariaLabel")
    nearby_text: str = Field(default="", alias="nearbyText")
    value: str = ""


class PageContext(AutofillModel):
    url: str = ""
    title: str = ""
    company: str = ""
    position: str = ""
    confidence: dict[str, str] = Field(default_factory=dict)


class AutofillMatchRequest(AutofillModel):
    profile: ApplicationProfile | None = None
    profile_id: str = Field(default="", alias="profileId")
    page: PageContext = Field(default_factory=PageContext)
    elements: list[PageElement] = Field(default_factory=list)


class MatchSuggestion(AutofillModel):
    field_key: str = Field(alias="fieldKey")
    element_index: int = Field(alias="elementIndex", ge=0)
    confidence: Confidence
    reason: str
    field: ApplicationField
    element: PageElement


class BlockedElement(AutofillModel):
    element_index: int = Field(alias="elementIndex", ge=0)
    reason: str
    element: PageElement


class AutofillMatchResponse(AutofillModel):
    matches: list[MatchSuggestion] = Field(default_factory=list)
    blocked: list[BlockedElement] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AutofillEventRequest(AutofillModel):
    event_type: AutofillEventType = Field(alias="eventType")
    status: AutofillEventStatus
    page: PageContext = Field(default_factory=PageContext)
    profile_id: str = Field(default="", alias="profileId")
    field_keys: list[str] = Field(default_factory=list, alias="fieldKeys")
    element_summaries: list[dict[str, Any]] = Field(default_factory=list, alias="elementSummaries")
    errors: list[str] = Field(default_factory=list)


class AutofillEventResponse(AutofillModel):
    ok: bool = True
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_autofill_profile.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

Run:

```powershell
git -c safe.directory=C:/Users/Zhu/Desktop/code/ResuMate-Agent add backend/schemas/autofill.py backend/tests/test_autofill_profile.py
git -c safe.directory=C:/Users/Zhu/Desktop/code/ResuMate-Agent commit -m "feat: add autofill schema models"
```

## Task 2: Application Profile Builder

**Files:**
- Modify: `backend/tests/test_autofill_profile.py`
- Create: `backend/services/autofill.py`

- [ ] **Step 1: Add failing profile builder test**

Append to `backend/tests/test_autofill_profile.py`:

```python
from datetime import datetime, timezone

from backend.db.models import Resume
from backend.services.autofill import build_application_profile, flatten_application_fields


def test_build_application_profile_maps_resume_profile_fields():
    resume = Resume(
        id=7,
        user_id=1,
        filename="ada.pdf",
        raw_text="",
        structured_data={
            "candidate_name": "Ada Lovelace",
            "contact": {"email": "ada@example.com", "phone": "1234567890", "location": "Shanghai"},
            "education": [
                {"school": "Example University", "degree": "MS", "major": "Computer Science", "years": "2022-2024"}
            ],
            "work_experience": [
                {
                    "company": "Analytical Engines Ltd",
                    "title": "Backend Engineer",
                    "duration": "2024-2026",
                    "description": "Built FastAPI services.",
                    "bullets": [{"raw_text": "Reduced latency by 30%."}],
                }
            ],
            "projects": [
                {
                    "name": "Resume Agent",
                    "role": "Developer",
                    "description": "Built document parsing workflow.",
                    "bullets": [{"raw_text": "Added OCR fallback."}],
                }
            ],
            "skills": [{"name": "Python"}, {"name": "FastAPI"}],
            "languages": ["English", "Chinese"],
            "certifications": ["AWS"],
            "self_summary": "Backend engineer focused on AI tools.",
        },
        created_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
    )

    profile = build_application_profile(resume)
    fields = {field.key: field.value for field in flatten_application_fields(profile)}

    assert profile.id == "resume:7"
    assert profile.name == "Ada Lovelace"
    assert fields["candidate_name"] == "Ada Lovelace"
    assert fields["contact.email"] == "ada@example.com"
    assert fields["education.0.school"] == "Example University"
    assert fields["work_experience.0.description"] == "Built FastAPI services.\nReduced latency by 30%."
    assert fields["projects.0.description"] == "Built document parsing workflow.\nAdded OCR fallback."
    assert fields["skills"] == "Python, FastAPI"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_autofill_profile.py::test_build_application_profile_maps_resume_profile_fields -q
```

Expected: fail with `ModuleNotFoundError: No module named 'backend.services.autofill'`.

- [ ] **Step 3: Implement profile builder**

Create `backend/services/autofill.py` with this initial content:

```python
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
    data = resume.structured_data or {}
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
    for index, item in enumerate(data.get("work_experience") or []):
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
```

- [ ] **Step 4: Run profile tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_autofill_profile.py -q
```

Expected: all tests in the file pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git -c safe.directory=C:/Users/Zhu/Desktop/code/ResuMate-Agent add backend/services/autofill.py backend/tests/test_autofill_profile.py
git -c safe.directory=C:/Users/Zhu/Desktop/code/ResuMate-Agent commit -m "feat: derive autofill profiles from resumes"
```

## Task 3: Deterministic Matcher And Sensitive Filtering

**Files:**
- Create: `backend/tests/test_autofill_matching.py`
- Modify: `backend/services/autofill.py`

- [ ] **Step 1: Write failing matcher tests**

Create `backend/tests/test_autofill_matching.py`:

```python
from backend.schemas.autofill import ApplicationField, ApplicationProfile, ApplicationSection, PageElement
from backend.services.autofill import match_application_fields


def _profile() -> ApplicationProfile:
    return ApplicationProfile(
        id="resume:1",
        name="Ada",
        source_resume_id="resume:1",
        updated_at="2026-08-04T00:00:00Z",
        sections=[
            ApplicationSection(
                id="basic",
                label="Basic",
                fields=[
                    ApplicationField(key="candidate_name", label="Name", value="Ada", aliases=["姓名", "full name"], category="basic", confidence="high", source="resume"),
                    ApplicationField(key="contact.email", label="Email", value="ada@example.com", aliases=["邮箱", "email address"], category="basic", confidence="high", source="resume"),
                    ApplicationField(key="contact.phone", label="Phone", value="1234567890", aliases=["手机", "mobile"], category="basic", confidence="high", source="resume"),
                ],
            )
        ],
    )


def test_match_application_fields_matches_chinese_labels():
    response = match_application_fields(
        _profile(),
        [
            PageElement(index=0, tag="input", type="text", label_text="姓名"),
            PageElement(index=1, tag="input", type="email", placeholder="请输入邮箱"),
            PageElement(index=2, tag="input", type="tel", name="mobile"),
        ],
    )

    assert [(item.field_key, item.element_index, item.confidence) for item in response.matches] == [
        ("candidate_name", 0, "high"),
        ("contact.email", 1, "high"),
        ("contact.phone", 2, "high"),
    ]
    assert response.blocked == []


def test_match_application_fields_blocks_sensitive_elements():
    response = match_application_fields(
        _profile(),
        [
            PageElement(index=0, tag="input", type="password", label_text="Password"),
            PageElement(index=1, tag="input", type="text", placeholder="验证码"),
            PageElement(index=2, tag="input", type="text", label_text="Email"),
        ],
    )

    assert [item.element_index for item in response.blocked] == [0, 1]
    assert [(item.field_key, item.element_index) for item in response.matches] == [("contact.email", 2)]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_autofill_matching.py -q
```

Expected: fail with `ImportError` for `match_application_fields`.

- [ ] **Step 3: Implement matcher functions**

Append this code to `backend/services/autofill.py`:

```python
import re

from backend.schemas.autofill import AutofillMatchResponse, BlockedElement, MatchSuggestion, PageElement


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
    "contact.email": ["email", "e-mail", "mail", "邮箱"],
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
        confidence = "high" if score >= 4 else "medium"
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
```

- [ ] **Step 4: Run matcher tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_autofill_matching.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Run profile and matcher tests together**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_autofill_profile.py backend\tests\test_autofill_matching.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git -c safe.directory=C:/Users/Zhu/Desktop/code/ResuMate-Agent add backend/services/autofill.py backend/tests/test_autofill_matching.py
git -c safe.directory=C:/Users/Zhu/Desktop/code/ResuMate-Agent commit -m "feat: add deterministic autofill matcher"
```

## Task 4: Backend Autofill Routes

**Files:**
- Create: `backend/routes/autofill.py`
- Modify: `backend/routes/api.py`
- Create: `backend/tests/test_autofill_routes.py`
- Modify: `backend/tests/test_main_entrypoint.py`

- [ ] **Step 1: Write route tests**

Create `backend/tests/test_autofill_routes.py`:

```python
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from backend.app import app
from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.db.models import Resume, User


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class FakeDb:
    def __init__(self, rows):
        self.rows = rows

    def query(self, model):
        assert model is Resume
        return FakeQuery(self.rows)


def _resume() -> Resume:
    return Resume(
        id=3,
        user_id=42,
        filename="ada.pdf",
        raw_text="",
        structured_data={"candidate_name": "Ada", "contact": {"email": "ada@example.com"}},
        created_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
    )


def _client(rows):
    app.dependency_overrides[get_current_user] = lambda: User(id=42, username="ada", role="user", password_hash="hash")
    app.dependency_overrides[get_db] = lambda: FakeDb(rows)
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_list_autofill_profiles_returns_resume_summaries():
    response = _client([_resume()]).get("/api/autofill/profiles")

    assert response.status_code == 200
    assert response.json()[0]["id"] == "resume:3"
    assert response.json()[0]["name"] == "Ada"
    assert response.json()[0]["fieldCount"] > 0


def test_get_autofill_profile_returns_full_profile():
    response = _client([_resume()]).get("/api/autofill/profiles/resume:3")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sourceResumeId"] == "resume:3"
    assert payload["sections"][0]["fields"][0]["value"] == "Ada"


def test_match_autofill_profile_by_payload():
    profile = _client([_resume()]).get("/api/autofill/profiles/resume:3").json()

    response = _client([_resume()]).post(
        "/api/autofill/match",
        json={
            "profile": profile,
            "page": {"url": "https://jobs.bytedance.com", "title": "Apply"},
            "elements": [{"index": 0, "tag": "input", "type": "email", "labelText": "邮箱"}],
        },
    )

    assert response.status_code == 200
    assert response.json()["matches"][0]["fieldKey"] == "contact.email"


def test_events_endpoint_redacts_values_from_response():
    response = _client([_resume()]).post(
        "/api/autofill/events",
        json={
            "eventType": "fill",
            "status": "success",
            "profileId": "resume:3",
            "fieldKeys": ["contact.email"],
            "elementSummaries": [{"index": 0, "labelText": "Email", "value": "ada@example.com"}],
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
```

Modify `backend/tests/test_main_entrypoint.py` by adding:

```python
def test_container_entrypoint_includes_autofill_routes():
    paths = {route.path for route in container_app.routes}
    assert "/api/autofill/profiles" in paths
    assert "/api/autofill/match" in paths
    assert "/api/autofill/events" in paths
```

- [ ] **Step 2: Run route tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_autofill_routes.py backend\tests\test_main_entrypoint.py::test_container_entrypoint_includes_autofill_routes -q
```

Expected: fail with 404 responses and missing route assertion.

- [ ] **Step 3: Implement routes**

Create `backend/routes/autofill.py`:

```python
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.db.models import Resume, User
from backend.schemas.autofill import (
    ApplicationProfile,
    ApplicationProfileSummary,
    AutofillEventRequest,
    AutofillEventResponse,
    AutofillMatchRequest,
    AutofillMatchResponse,
)
from backend.services.autofill import build_application_profile, flatten_application_fields, match_application_fields

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/autofill", tags=["autofill"])


def _resume_id(profile_id: str) -> int:
    prefix, _, raw_id = profile_id.partition(":")
    if prefix != "resume" or not raw_id.isdigit():
        raise HTTPException(status_code=404, detail="profile not found")
    return int(raw_id)


def _find_resume(db: Session, user_id: int, profile_id: str) -> Resume:
    row = db.query(Resume).filter(Resume.id == _resume_id(profile_id), Resume.user_id == user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="profile not found")
    return row


@router.get("/profiles", response_model=list[ApplicationProfileSummary])
def list_profiles(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Resume).filter(Resume.user_id == current_user.id).order_by(Resume.updated_at.desc()).all()
    summaries: list[ApplicationProfileSummary] = []
    for row in rows:
        profile = build_application_profile(row)
        summaries.append(
            ApplicationProfileSummary(
                id=profile.id,
                name=profile.name,
                source_resume_id=profile.source_resume_id,
                updated_at=profile.updated_at,
                field_count=len([field for field in flatten_application_fields(profile) if field.value]),
            )
        )
    return summaries


@router.get("/profiles/{profile_id}", response_model=ApplicationProfile)
def get_profile(profile_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return build_application_profile(_find_resume(db, current_user.id, profile_id))


@router.post("/match", response_model=AutofillMatchResponse)
def match_fields(request: AutofillMatchRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = request.profile
    if profile is None:
        if not request.profile_id:
            raise HTTPException(status_code=422, detail="profile or profileId is required")
        profile = build_application_profile(_find_resume(db, current_user.id, request.profile_id))
    return match_application_fields(profile, request.elements)


@router.post("/events", response_model=AutofillEventResponse)
def record_event(request: AutofillEventRequest, current_user: User = Depends(get_current_user)):
    safe_elements = []
    for element in request.element_summaries:
        safe = {key: value for key, value in element.items() if key != "value"}
        safe_elements.append(safe)
    logger.info(
        "Autofill event | user_id=%s type=%s status=%s profile_id=%s fields=%s elements=%s errors=%s",
        current_user.id,
        request.event_type,
        request.status,
        request.profile_id,
        request.field_keys,
        safe_elements,
        request.errors,
    )
    return AutofillEventResponse(ok=True)
```

Modify `backend/routes/api.py`:

```python
from backend.routes.autofill import router as autofill_router
```

Add the include near other subrouters:

```python
router.include_router(autofill_router)
```

- [ ] **Step 4: Run route tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_autofill_routes.py backend\tests\test_main_entrypoint.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Run backend autofill suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_autofill_profile.py backend\tests\test_autofill_matching.py backend\tests\test_autofill_routes.py -q
```

Expected: all autofill tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git -c safe.directory=C:/Users/Zhu/Desktop/code/ResuMate-Agent add backend/routes/autofill.py backend/routes/api.py backend/tests/test_autofill_routes.py backend/tests/test_main_entrypoint.py
git -c safe.directory=C:/Users/Zhu/Desktop/code/ResuMate-Agent commit -m "feat: expose autofill backend api"
```

## Task 5: Chrome Extension Shell And Static UI

**Files:**
- Create: `extension/manifest.json`
- Create: `extension/service-worker.js`
- Create: `extension/lib/constants.js`
- Create: `extension/sidepanel/sidepanel.html`
- Create: `extension/sidepanel/sidepanel.css`
- Create: `extension/sidepanel/sidepanel.js`
- Create: `extension/README.md`

- [ ] **Step 1: Create extension manifest**

Create `extension/manifest.json`:

```json
{
  "manifest_version": 3,
  "name": "ResuMate Autofill",
  "version": "0.1.0",
  "description": "Fill recruiting forms from ResuMate profiles after user review.",
  "permissions": ["sidePanel", "storage", "activeTab", "scripting"],
  "host_permissions": ["http://127.0.0.1/*", "http://localhost/*", "<all_urls>"],
  "action": {
    "default_title": "ResuMate Autofill"
  },
  "side_panel": {
    "default_path": "sidepanel/sidepanel.html"
  },
  "background": {
    "service_worker": "service-worker.js",
    "type": "module"
  },
  "content_scripts": [
    {
      "matches": ["<all_urls>"],
      "js": ["content/fill-engine.js"],
      "run_at": "document_end"
    }
  ]
}
```

- [ ] **Step 2: Create service worker**

Create `extension/service-worker.js`:

```javascript
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
```

- [ ] **Step 3: Create constants**

Create `extension/lib/constants.js`:

```javascript
export const DEFAULT_API_BASE = 'http://127.0.0.1:8000';

export const STORAGE_KEYS = {
  apiBase: 'resumate_api_base',
  authToken: 'resumate_auth_token',
  activeProfileId: 'resumate_active_profile_id',
  profiles: 'resumate_cached_profiles',
  lastMatches: 'resumate_last_matches'
};

export const CONFIDENCE_ORDER = {
  high: 1,
  medium: 2,
  low: 3
};
```

- [ ] **Step 4: Create side panel HTML**

Create `extension/sidepanel/sidepanel.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>ResuMate Autofill</title>
    <link rel="stylesheet" href="sidepanel.css" />
  </head>
  <body>
    <main class="shell">
      <header class="topbar">
        <div>
          <h1>ResuMate</h1>
          <p id="statusText">Disconnected</p>
        </div>
        <button id="refreshProfilesBtn" type="button">Refresh</button>
      </header>

      <section class="panel">
        <label for="apiBaseInput">Backend</label>
        <div class="row">
          <input id="apiBaseInput" type="url" />
          <button id="saveSettingsBtn" type="button">Save</button>
        </div>
        <label for="tokenInput">Token</label>
        <input id="tokenInput" type="password" placeholder="Paste ResuMate JWT" />
      </section>

      <section class="panel">
        <label for="profileSelect">Profile</label>
        <select id="profileSelect"></select>
        <div id="profileFields" class="field-list"></div>
      </section>

      <section class="actions">
        <button id="scanBtn" type="button">Scan Page</button>
        <button id="fillBtn" type="button" disabled>Fill Selected</button>
      </section>

      <section id="pageInfo" class="page-info"></section>
      <section id="matches" class="matches"></section>
    </main>
    <script type="module" src="sidepanel.js"></script>
  </body>
</html>
```

- [ ] **Step 5: Create side panel CSS**

Create `extension/sidepanel/sidepanel.css`:

```css
* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font: 13px/1.4 Arial, sans-serif;
  color: #1f2937;
  background: #f7f8fa;
}

.shell {
  display: grid;
  gap: 12px;
  padding: 12px;
}

.topbar,
.panel,
.actions,
.page-info,
.matches {
  background: #ffffff;
  border: 1px solid #d6dae1;
  border-radius: 8px;
  padding: 12px;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

h1 {
  margin: 0;
  font-size: 18px;
}

p {
  margin: 4px 0 0;
  color: #667085;
}

label {
  display: block;
  margin: 8px 0 4px;
  font-weight: 700;
}

input,
select,
button {
  width: 100%;
  min-height: 34px;
  border: 1px solid #c5cad3;
  border-radius: 6px;
  padding: 6px 8px;
  font: inherit;
}

button {
  cursor: pointer;
  background: #1f2937;
  color: #ffffff;
  border-color: #1f2937;
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.row {
  display: grid;
  grid-template-columns: 1fr 72px;
  gap: 8px;
}

.actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.field-list,
.matches {
  display: grid;
  gap: 8px;
}

.field,
.match {
  border: 1px solid #e1e5eb;
  border-radius: 6px;
  padding: 8px;
  background: #fbfcfd;
}

.match {
  display: grid;
  grid-template-columns: 18px 1fr;
  gap: 8px;
}

.muted {
  color: #667085;
}
```

- [ ] **Step 6: Create minimal sidepanel JS**

Create `extension/sidepanel/sidepanel.js`:

```javascript
import { DEFAULT_API_BASE } from '../lib/constants.js';

const state = {
  apiBase: DEFAULT_API_BASE,
  token: '',
  profiles: [],
  activeProfile: null,
  matches: []
};

const $ = (id) => document.getElementById(id);

function setStatus(text) {
  $('statusText').textContent = text;
}

function render() {
  $('apiBaseInput').value = state.apiBase;
  $('tokenInput').value = state.token;
  $('profileSelect').innerHTML = state.profiles
    .map((profile) => `<option value="${profile.id}">${profile.name}</option>`)
    .join('');
  $('profileFields').innerHTML = state.activeProfile
    ? state.activeProfile.sections.flatMap((section) => section.fields).filter((field) => field.value).slice(0, 8)
        .map((field) => `<div class="field"><strong>${field.label}</strong><div class="muted">${field.value}</div></div>`)
        .join('')
    : '<div class="muted">No profile loaded</div>';
}

function bind() {
  $('saveSettingsBtn').addEventListener('click', () => {
    state.apiBase = $('apiBaseInput').value || DEFAULT_API_BASE;
    state.token = $('tokenInput').value || '';
    setStatus('Settings saved');
    render();
  });
  $('refreshProfilesBtn').addEventListener('click', () => setStatus('Profile loading is added in the next task'));
  $('scanBtn').addEventListener('click', () => setStatus('Scanning is added in the fill-engine task'));
}

bind();
render();
```

- [ ] **Step 7: Add extension README**

Create `extension/README.md`:

```markdown
# ResuMate Autofill Extension

## Load Locally

1. Open Chrome or Edge.
2. Go to `chrome://extensions`.
3. Enable Developer mode.
4. Choose "Load unpacked".
5. Select the `extension/` directory.
6. Open a recruiting application page and click the ResuMate Autofill toolbar icon.

## First Version Boundary

- The extension fills selected fields only after user review.
- It does not submit applications.
- It does not bypass login, captcha, two-factor checks, or site restrictions.
- File upload fields are shown as manual actions.
```

- [ ] **Step 8: Verify JSON syntax**

Run:

```powershell
node -e "JSON.parse(require('fs').readFileSync('extension/manifest.json','utf8')); console.log('manifest ok')"
```

Expected: `manifest ok`.

- [ ] **Step 9: Commit**

Run:

```powershell
git -c safe.directory=C:/Users/Zhu/Desktop/code/ResuMate-Agent add extension/manifest.json extension/service-worker.js extension/lib/constants.js extension/sidepanel/sidepanel.html extension/sidepanel/sidepanel.css extension/sidepanel/sidepanel.js extension/README.md
git -c safe.directory=C:/Users/Zhu/Desktop/code/ResuMate-Agent commit -m "feat: add chrome extension shell"
```

## Task 6: Extension Storage And API Client

**Files:**
- Create: `extension/lib/storage.js`
- Create: `extension/lib/api-client.js`
- Modify: `extension/sidepanel/sidepanel.js`

- [ ] **Step 1: Add storage wrapper**

Create `extension/lib/storage.js`:

```javascript
import { DEFAULT_API_BASE, STORAGE_KEYS } from './constants.js';

export async function getSettings() {
  const data = await chrome.storage.local.get([STORAGE_KEYS.apiBase, STORAGE_KEYS.authToken]);
  return {
    apiBase: data[STORAGE_KEYS.apiBase] || DEFAULT_API_BASE,
    token: data[STORAGE_KEYS.authToken] || ''
  };
}

export async function saveSettings(settings) {
  await chrome.storage.local.set({
    [STORAGE_KEYS.apiBase]: settings.apiBase || DEFAULT_API_BASE,
    [STORAGE_KEYS.authToken]: settings.token || ''
  });
}

export async function getCachedProfiles() {
  const data = await chrome.storage.local.get(STORAGE_KEYS.profiles);
  return Array.isArray(data[STORAGE_KEYS.profiles]) ? data[STORAGE_KEYS.profiles] : [];
}

export async function cacheProfiles(profiles) {
  await chrome.storage.local.set({ [STORAGE_KEYS.profiles]: profiles || [] });
}

export async function getActiveProfileId() {
  const data = await chrome.storage.local.get(STORAGE_KEYS.activeProfileId);
  return data[STORAGE_KEYS.activeProfileId] || '';
}

export async function setActiveProfileId(profileId) {
  await chrome.storage.local.set({ [STORAGE_KEYS.activeProfileId]: profileId || '' });
}
```

- [ ] **Step 2: Add API client**

Create `extension/lib/api-client.js`:

```javascript
function headers(token) {
  const value = { 'Content-Type': 'application/json' };
  if (token) value.Authorization = `Bearer ${token}`;
  return value;
}

async function parseJsonResponse(response) {
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const message = data && data.detail ? data.detail : `HTTP ${response.status}`;
    throw new Error(Array.isArray(message) ? JSON.stringify(message) : String(message));
  }
  return data;
}

export async function listProfiles(settings) {
  const response = await fetch(`${settings.apiBase}/api/autofill/profiles`, {
    headers: headers(settings.token)
  });
  return parseJsonResponse(response);
}

export async function getProfile(settings, profileId) {
  const response = await fetch(`${settings.apiBase}/api/autofill/profiles/${encodeURIComponent(profileId)}`, {
    headers: headers(settings.token)
  });
  return parseJsonResponse(response);
}

export async function matchFields(settings, payload) {
  const response = await fetch(`${settings.apiBase}/api/autofill/match`, {
    method: 'POST',
    headers: headers(settings.token),
    body: JSON.stringify(payload)
  });
  return parseJsonResponse(response);
}

export async function recordEvent(settings, payload) {
  const response = await fetch(`${settings.apiBase}/api/autofill/events`, {
    method: 'POST',
    headers: headers(settings.token),
    body: JSON.stringify(payload)
  });
  return parseJsonResponse(response);
}
```

- [ ] **Step 3: Wire profile loading in sidepanel**

Replace `extension/sidepanel/sidepanel.js` with:

```javascript
import { DEFAULT_API_BASE } from '../lib/constants.js';
import { getProfile, listProfiles } from '../lib/api-client.js';
import { cacheProfiles, getActiveProfileId, getCachedProfiles, getSettings, saveSettings, setActiveProfileId } from '../lib/storage.js';

const state = {
  apiBase: DEFAULT_API_BASE,
  token: '',
  profileSummaries: [],
  activeProfile: null,
  offline: false,
  matches: []
};

const $ = (id) => document.getElementById(id);

function settings() {
  return { apiBase: state.apiBase, token: state.token };
}

function setStatus(text) {
  $('statusText').textContent = text;
}

function allFields(profile) {
  return profile ? profile.sections.flatMap((section) => section.fields).filter((field) => field.value) : [];
}

function renderProfiles() {
  $('profileSelect').innerHTML = state.profileSummaries
    .map((profile) => `<option value="${profile.id}">${profile.name}</option>`)
    .join('');
  if (state.activeProfile) $('profileSelect').value = state.activeProfile.id;
}

function renderFields() {
  const fields = allFields(state.activeProfile).slice(0, 12);
  $('profileFields').innerHTML = fields.length
    ? fields.map((field) => `<div class="field"><strong>${field.label}</strong><div class="muted">${field.value}</div></div>`).join('')
    : '<div class="muted">No profile loaded</div>';
}

function renderSettings() {
  $('apiBaseInput').value = state.apiBase;
  $('tokenInput').value = state.token;
}

function render() {
  renderSettings();
  renderProfiles();
  renderFields();
}

async function loadProfile(profileId) {
  const profile = await getProfile(settings(), profileId);
  state.activeProfile = profile;
  await setActiveProfileId(profile.id);
  return profile;
}

async function refreshProfiles() {
  try {
    state.offline = false;
    state.profileSummaries = await listProfiles(settings());
    const activeId = await getActiveProfileId();
    const selected = state.profileSummaries.find((profile) => profile.id === activeId) || state.profileSummaries[0];
    state.activeProfile = selected ? await loadProfile(selected.id) : null;
    await cacheProfiles(state.activeProfile ? [state.activeProfile] : []);
    setStatus(state.activeProfile ? 'Connected' : 'No profiles');
  } catch (error) {
    state.offline = true;
    const cached = await getCachedProfiles();
    state.activeProfile = cached[0] || null;
    state.profileSummaries = cached.map((profile) => ({ id: profile.id, name: `${profile.name} (cached)`, sourceResumeId: profile.sourceResumeId, updatedAt: profile.updatedAt, fieldCount: allFields(profile).length }));
    setStatus(state.activeProfile ? `Offline: ${error.message}` : `Disconnected: ${error.message}`);
  }
  render();
}

function bind() {
  $('saveSettingsBtn').addEventListener('click', async () => {
    state.apiBase = $('apiBaseInput').value || DEFAULT_API_BASE;
    state.token = $('tokenInput').value || '';
    await saveSettings(settings());
    await refreshProfiles();
  });
  $('refreshProfilesBtn').addEventListener('click', refreshProfiles);
  $('profileSelect').addEventListener('change', async (event) => {
    try {
      await loadProfile(event.target.value);
      render();
    } catch (error) {
      setStatus(`Profile load failed: ${error.message}`);
    }
  });
  $('scanBtn').addEventListener('click', () => setStatus('Scanning is added in the fill-engine task'));
}

async function init() {
  const saved = await getSettings();
  state.apiBase = saved.apiBase;
  state.token = saved.token;
  bind();
  render();
  await refreshProfiles();
}

init();
```

- [ ] **Step 4: Verify JavaScript modules parse**

Run:

```powershell
node --check extension\lib\storage.js
node --check extension\lib\api-client.js
node --check extension\sidepanel\sidepanel.js
```

Expected: no output and exit code 0 for each command.

- [ ] **Step 5: Commit**

Run:

```powershell
git -c safe.directory=C:/Users/Zhu/Desktop/code/ResuMate-Agent add extension/lib/storage.js extension/lib/api-client.js extension/sidepanel/sidepanel.js
git -c safe.directory=C:/Users/Zhu/Desktop/code/ResuMate-Agent commit -m "feat: connect extension to autofill api"
```

## Task 7: Content Fill Engine And Offline Matcher

**Files:**
- Create: `extension/content/fill-engine.js`
- Create: `extension/lib/field-matcher.js`
- Modify: `extension/sidepanel/sidepanel.js`

- [ ] **Step 1: Create content fill engine**

Create `extension/content/fill-engine.js`:

```javascript
(function () {
  'use strict';

  let lastFocusedElement = null;
  let scannedElements = [];

  document.addEventListener('focusin', (event) => {
    if (isFillable(event.target)) lastFocusedElement = event.target;
  }, true);

  function isFillable(element) {
    if (!element || !element.tagName) return false;
    const tag = element.tagName.toLowerCase();
    if (tag === 'input') {
      const type = (element.type || 'text').toLowerCase();
      return !['hidden', 'submit', 'button', 'reset', 'file', 'password'].includes(type);
    }
    return tag === 'textarea' || tag === 'select' || element.isContentEditable || element.getAttribute('contenteditable') === 'true';
  }

  function textOf(element) {
    return element && element.textContent ? element.textContent.trim().replace(/\s+/g, ' ').slice(0, 120) : '';
  }

  function labelFor(element) {
    if (element.id) {
      const label = document.querySelector(`label[for="${CSS.escape(element.id)}"]`);
      if (label) return textOf(label);
    }
    const wrapper = element.closest('label');
    if (wrapper) return textOf(wrapper);
    return '';
  }

  function nearbyText(element) {
    const container = element.closest('label, .form-item, .form-row, .field, .ant-form-item, .semi-form-field, .arco-form-item, div');
    return textOf(container).slice(0, 160);
  }

  function scanForm() {
    scannedElements = [];
    const elements = [];
    const selector = 'input, textarea, select, [contenteditable="true"]';
    document.querySelectorAll(selector).forEach((element) => {
      if (!isFillable(element)) return;
      const rect = element.getBoundingClientRect();
      if (rect.width < 20 || rect.height < 10) return;
      scannedElements.push(element);
      elements.push({
        index: scannedElements.length - 1,
        tag: element.tagName.toLowerCase(),
        type: element.type || '',
        id: element.id || '',
        name: element.name || '',
        placeholder: element.placeholder || '',
        labelText: labelFor(element),
        ariaLabel: element.getAttribute('aria-label') || '',
        nearbyText: nearbyText(element),
        value: element.value || ''
      });
    });
    return { elements };
  }

  function fillInput(element, value) {
    element.focus();
    const proto = element.tagName === 'INPUT' ? HTMLInputElement.prototype : HTMLTextAreaElement.prototype;
    const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
    if (descriptor && descriptor.set) descriptor.set.call(element, value);
    else element.value = value;
    if (element._valueTracker) element._valueTracker.setValue(element.value);
    element.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
    element.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
    return { success: true, filled: value };
  }

  function fillSelect(element, value) {
    element.focus();
    const search = String(value || '').toLowerCase().trim();
    let bestIndex = -1;
    for (let index = 0; index < element.options.length; index += 1) {
      const option = element.options[index];
      if (!option || option.disabled) continue;
      const text = (option.text || option.label || '').toLowerCase().trim();
      const optionValue = (option.value || '').toLowerCase().trim();
      if (text === search || optionValue === search || text.includes(search) || search.includes(text)) {
        bestIndex = index;
        break;
      }
    }
    if (bestIndex < 0) return { success: false, error: `No option for ${value}` };
    element.selectedIndex = bestIndex;
    element.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
    return { success: true, filled: element.options[bestIndex].text };
  }

  function fillContentEditable(element, value) {
    element.focus();
    element.textContent = value;
    element.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
    element.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
    return { success: true, filled: value };
  }

  function fillElement(element, value) {
    if (!element || !document.contains(element) || !isFillable(element)) {
      return { success: false, error: 'Element is no longer fillable' };
    }
    const tag = element.tagName.toLowerCase();
    if (tag === 'select') return fillSelect(element, value);
    if (tag === 'input' || tag === 'textarea') return fillInput(element, value);
    if (element.isContentEditable || element.getAttribute('contenteditable') === 'true') return fillContentEditable(element, value);
    return { success: false, error: `Unsupported element ${tag}` };
  }

  chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
    if (request.type === 'SCAN_FORM') {
      sendResponse(scanForm());
      return true;
    }
    if (request.type === 'FILL_SELECTED') {
      const results = (request.items || []).map((item) => {
        const element = scannedElements[item.elementIndex];
        return fillElement(element, item.value);
      });
      sendResponse({ results });
      return true;
    }
    if (request.type === 'FILL_FOCUSED') {
      sendResponse(fillElement(lastFocusedElement, request.value));
      return true;
    }
    return false;
  });
})();
```

- [ ] **Step 2: Create offline matcher**

Create `extension/lib/field-matcher.js`:

```javascript
const SENSITIVE = ['password', 'captcha', 'verification', 'otp', 'id card', 'bank card', '密码', '验证码', '身份证', '银行卡'];

const KEYWORDS = {
  candidate_name: ['name', 'full name', '姓名'],
  'contact.email': ['email', 'mail', '邮箱'],
  'contact.phone': ['phone', 'mobile', 'tel', '手机', '电话'],
  'contact.location': ['city', 'location', '城市'],
  skills: ['skills', '技能'],
  languages: ['languages', '语言'],
  certifications: ['certifications', 'certificate', '证书'],
  self_summary: ['summary', 'self introduction', '自我介绍']
};

function norm(value) {
  return String(value || '').toLowerCase().replace(/\s+/g, ' ').trim();
}

function elementText(element) {
  return norm([element.type, element.id, element.name, element.placeholder, element.labelText, element.ariaLabel, element.nearbyText].filter(Boolean).join(' '));
}

function fieldKeywords(field) {
  const words = [field.key, field.label, ...(field.aliases || []), ...(KEYWORDS[field.key] || [])];
  if (field.key.includes('.school')) words.push('school', 'university', '学校');
  if (field.key.includes('.company')) words.push('company', 'employer', '公司');
  if (field.key.includes('.title')) words.push('title', 'role', 'position', '岗位');
  if (field.key.includes('.description')) words.push('description', '描述', '介绍');
  return words.map(norm).filter(Boolean);
}

function isSensitive(element) {
  const text = elementText(element);
  return norm(element.type) === 'password' || SENSITIVE.some((item) => text.includes(item));
}

export function flattenFields(profile) {
  return profile ? profile.sections.flatMap((section) => section.fields).filter((field) => field.value) : [];
}

export function matchLocally(profile, elements) {
  const fields = flattenFields(profile);
  const blocked = [];
  const candidates = [];
  for (const element of elements) {
    if (isSensitive(element)) {
      blocked.push({ elementIndex: element.index, reason: 'sensitive field', element });
      continue;
    }
    const text = elementText(element);
    for (const field of fields) {
      const keyword = fieldKeywords(field).find((item) => item && text.includes(item));
      if (keyword) candidates.push({ score: keyword.length, field, element, reason: `label contains "${keyword}"` });
    }
  }
  const usedFields = new Set();
  const usedElements = new Set();
  const matches = [];
  for (const candidate of candidates.sort((a, b) => b.score - a.score)) {
    if (usedFields.has(candidate.field.key) || usedElements.has(candidate.element.index)) continue;
    matches.push({
      fieldKey: candidate.field.key,
      elementIndex: candidate.element.index,
      confidence: candidate.score >= 4 ? 'high' : 'medium',
      reason: candidate.reason,
      field: candidate.field,
      element: candidate.element
    });
    usedFields.add(candidate.field.key);
    usedElements.add(candidate.element.index);
  }
  return { matches: matches.sort((a, b) => a.elementIndex - b.elementIndex), blocked, warnings: [] };
}
```

- [ ] **Step 3: Wire scan and fill in sidepanel**

Replace the API client import in `extension/sidepanel/sidepanel.js`:

```javascript
import { getProfile, listProfiles, matchFields, recordEvent } from '../lib/api-client.js';
import { matchLocally } from '../lib/field-matcher.js';
```

Add these functions above `bind()`:

```javascript
async function activeTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tabs[0] || !tabs[0].id) throw new Error('No active tab');
  return tabs[0];
}

function renderMatches() {
  $('fillBtn').disabled = state.matches.length === 0;
  $('matches').innerHTML = state.matches.length
    ? state.matches.map((match, index) => `
      <label class="match">
        <input type="checkbox" data-match-index="${index}" ${match.confidence === 'high' ? 'checked' : ''} />
        <span>
          <strong>${match.field.label}</strong> -> ${match.element.labelText || match.element.placeholder || match.element.name || match.element.id || `Field ${match.elementIndex}`}
          <div class="muted">${match.confidence}: ${match.reason}</div>
        </span>
      </label>
    `).join('')
    : '<div class="muted">No matches yet</div>';
}

async function scanPage() {
  if (!state.activeProfile) {
    setStatus('Load a profile before scanning');
    return;
  }
  const tab = await activeTab();
  const scan = await chrome.tabs.sendMessage(tab.id, { type: 'SCAN_FORM' });
  const payload = {
    profile: state.activeProfile,
    page: { url: tab.url || '', title: tab.title || '' },
    elements: scan.elements || []
  };
  const response = state.offline ? matchLocally(state.activeProfile, payload.elements) : await matchFields(settings(), payload);
  state.matches = response.matches || [];
  $('pageInfo').textContent = `${payload.elements.length} fields scanned on ${payload.page.title}`;
  await recordEvent(settings(), {
    eventType: 'scan',
    status: state.matches.length ? 'success' : 'partial',
    profileId: state.activeProfile.id,
    fieldKeys: state.matches.map((match) => match.fieldKey),
    elementSummaries: payload.elements.map((element) => ({ index: element.index, labelText: element.labelText, name: element.name, type: element.type }))
  }).catch(() => {});
  renderMatches();
  setStatus(`Matched ${state.matches.length} fields`);
}

async function fillSelected() {
  const tab = await activeTab();
  const selected = [...document.querySelectorAll('[data-match-index]:checked')]
    .map((input) => state.matches[Number(input.dataset.matchIndex)])
    .filter(Boolean);
  const items = selected.map((match) => ({ elementIndex: match.elementIndex, value: match.field.value }));
  const response = await chrome.tabs.sendMessage(tab.id, { type: 'FILL_SELECTED', items });
  const ok = (response.results || []).filter((item) => item.success).length;
  const fail = (response.results || []).length - ok;
  await recordEvent(settings(), {
    eventType: 'fill',
    status: fail ? 'partial' : 'success',
    profileId: state.activeProfile.id,
    fieldKeys: selected.map((match) => match.fieldKey),
    elementSummaries: selected.map((match) => ({ index: match.elementIndex, labelText: match.element.labelText, name: match.element.name, type: match.element.type })),
    errors: (response.results || []).filter((item) => !item.success).map((item) => item.error || 'fill failed')
  }).catch(() => {});
  setStatus(`Filled ${ok} fields${fail ? `, ${fail} failed` : ''}`);
}
```

Replace the old scan button binding:

```javascript
$('scanBtn').addEventListener('click', scanPage);
$('fillBtn').addEventListener('click', fillSelected);
```

- [ ] **Step 4: Verify JavaScript parses**

Run:

```powershell
node --check extension\content\fill-engine.js
node --check extension\lib\field-matcher.js
node --check extension\sidepanel\sidepanel.js
```

Expected: no output and exit code 0 for each command.

- [ ] **Step 5: Commit**

Run:

```powershell
git -c safe.directory=C:/Users/Zhu/Desktop/code/ResuMate-Agent add extension/content/fill-engine.js extension/lib/field-matcher.js extension/sidepanel/sidepanel.js
git -c safe.directory=C:/Users/Zhu/Desktop/code/ResuMate-Agent commit -m "feat: scan and fill recruiting forms"
```

## Task 8: Page Scraper And Match Context

**Files:**
- Create: `extension/content/scraper.js`
- Modify: `extension/sidepanel/sidepanel.js`

- [ ] **Step 1: Create scraper**

Create `extension/content/scraper.js`:

```javascript
(() => {
  const hostname = location.hostname.toLowerCase();

  function text(selectors) {
    for (const selector of selectors.split(',')) {
      let element = null;
      try {
        element = document.querySelector(selector.trim());
      } catch (_error) {
        element = null;
      }
      const value = element && element.textContent ? element.textContent.trim().replace(/\s+/g, ' ') : '';
      if (value) return value.slice(0, 80);
    }
    return '';
  }

  function meta(name) {
    const element = document.querySelector(`meta[property="${name}"], meta[name="${name}"]`);
    return element ? (element.getAttribute('content') || '').trim() : '';
  }

  function genericPosition() {
    return text('h1, [class*="job-title"], [class*="jobTitle"], [class*="job-name"], [class*="positionName"], [class*="position-title"]');
  }

  function titleSegments(value) {
    return String(value || document.title).split(/\s*[|｜\-–—_·»【】]\s*/).map((item) => item.trim()).filter(Boolean);
  }

  function titlePosition(value) {
    const segments = titleSegments(value).filter((item) => !/招聘|校招|社招|Careers?|Jobs?|Hiring/i.test(item));
    return (segments.sort((a, b) => b.length - a.length)[0] || '').slice(0, 80);
  }

  function titleCompany(value) {
    for (const segment of titleSegments(value)) {
      if (/招聘|校招|社招|Careers?|Jobs?|Hiring/i.test(segment)) {
        const cleaned = segment.replace(/招聘|校招|社招|Careers?|Jobs?|Hiring/gi, '').replace(/官网|首页/g, '').trim();
        if (cleaned) return cleaned.slice(0, 40);
      }
    }
    return '';
  }

  const rules = [
    { match: (host) => host === 'jobs.bytedance.com', company: 'ByteDance', position: () => text('h1, [class*="postTitle"]') || genericPosition() },
    { match: (host) => host === 'careers.tencent.com' || host === 'join.qq.com', company: 'Tencent', position: () => text('.job-detail-title, h1') || genericPosition() },
    { match: (host) => host === 'talent.alibaba.com', company: 'Alibaba', position: genericPosition },
    { match: (host) => host === 'zhaopin.meituan.com', company: 'Meituan', position: genericPosition },
    { match: (host) => host === 'talent.baidu.com', company: 'Baidu', position: genericPosition },
    { match: (host) => host === 'careers.jd.com' || host === 'zhaopin.jd.com', company: 'JD', position: genericPosition },
    { match: (host) => host === 'hr.163.com' || host === 'campus.163.com', company: 'NetEase', position: genericPosition },
    { match: (host) => host === 'careers.pinduoduo.com', company: 'Pinduoduo', position: genericPosition },
    { match: (host) => host.endsWith('.mokahr.com'), company: () => meta('og:site_name') || titleCompany(), position: genericPosition },
    { match: (host) => host.endsWith('.beisen.com') || host.includes('hotjob'), company: () => meta('og:site_name') || titleCompany(), position: genericPosition },
    { match: (host) => host.endsWith('.myworkdayjobs.com'), company: (host) => host.split('.')[0], position: () => text('h1[data-automation-id="jobPostingHeader"], h1') },
    { match: (host) => host.endsWith('.greenhouse.io'), company: () => meta('og:site_name') || titleCompany(), position: () => text('h1.app-title, h1') },
    { match: (host) => host.endsWith('.lever.co'), company: () => meta('og:site_name') || titleCompany() || location.pathname.split('/').filter(Boolean)[0] || '', position: () => text('.posting-headline h2, h2, h1') }
  ];

  let company = '';
  let position = '';
  const confidence = { company: 'none', position: 'none' };
  const rule = rules.find((item) => item.match(hostname));
  if (rule) {
    company = typeof rule.company === 'function' ? rule.company(hostname) : rule.company;
    position = typeof rule.position === 'function' ? rule.position(hostname) : rule.position;
    if (company) confidence.company = 'site-rule';
    if (position) confidence.position = 'site-rule';
  }
  if (!company) {
    company = meta('og:site_name') || titleCompany() || hostname.split('.').filter((part) => !['www', 'careers', 'jobs', 'com', 'cn', 'net'].includes(part)).pop() || hostname;
    confidence.company = company ? 'fallback' : 'none';
  }
  if (!position) {
    position = titlePosition(meta('og:title')) || titlePosition() || genericPosition();
    confidence.position = position ? 'fallback' : 'none';
  }

  return { company, position, url: location.href, title: document.title, confidence };
})();
```

- [ ] **Step 2: Inject scraper during scan**

Replace `scanPage()` in `extension/sidepanel/sidepanel.js` so page context is scraped before matching:

```javascript
async function scanPage() {
  if (!state.activeProfile) {
    setStatus('Load a profile before scanning');
    return;
  }
  const tab = await activeTab();
  const scan = await chrome.tabs.sendMessage(tab.id, { type: 'SCAN_FORM' });
  const scrapeResults = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ['content/scraper.js']
  });
  const scraped = scrapeResults && scrapeResults[0] ? scrapeResults[0].result : {};
  const payload = {
    profile: state.activeProfile,
    page: {
      url: scraped.url || tab.url || '',
      title: scraped.title || tab.title || '',
      company: scraped.company || '',
      position: scraped.position || '',
      confidence: scraped.confidence || {}
    },
    elements: scan.elements || []
  };
  const response = state.offline ? matchLocally(state.activeProfile, payload.elements) : await matchFields(settings(), payload);
  state.matches = response.matches || [];
  $('pageInfo').textContent = `${payload.elements.length} fields scanned for ${payload.page.company || 'unknown company'} ${payload.page.position || ''}`;
  await recordEvent(settings(), {
    eventType: 'scan',
    status: state.matches.length ? 'success' : 'partial',
    profileId: state.activeProfile.id,
    fieldKeys: state.matches.map((match) => match.fieldKey),
    elementSummaries: payload.elements.map((element) => ({ index: element.index, labelText: element.labelText, name: element.name, type: element.type }))
  }).catch(() => {});
  renderMatches();
  setStatus(`Matched ${state.matches.length} fields`);
}
```

- [ ] **Step 3: Verify JavaScript parses**

Run:

```powershell
node --check extension\content\scraper.js
node --check extension\sidepanel\sidepanel.js
```

Expected: no output and exit code 0 for each command.

- [ ] **Step 4: Commit**

Run:

```powershell
git -c safe.directory=C:/Users/Zhu/Desktop/code/ResuMate-Agent add extension/content/scraper.js extension/sidepanel/sidepanel.js
git -c safe.directory=C:/Users/Zhu/Desktop/code/ResuMate-Agent commit -m "feat: add recruiting page scraper"
```

## Task 9: Manual Test Fixture And Final Verification

**Files:**
- Create: `extension/fixtures/application-form.html`
- Modify: `extension/README.md`

- [ ] **Step 1: Create local application form fixture**

Create `extension/fixtures/application-form.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Backend Engineer - Example Careers</title>
    <style>
      body { font: 14px Arial, sans-serif; margin: 32px; max-width: 720px; }
      label { display: grid; gap: 4px; margin: 12px 0; }
      input, textarea, select { min-height: 34px; padding: 6px 8px; }
      textarea { min-height: 96px; }
    </style>
  </head>
  <body>
    <h1>Backend Engineer</h1>
    <form>
      <label>姓名 <input name="candidate_name" /></label>
      <label>邮箱 <input type="email" name="email" /></label>
      <label>手机 <input type="tel" name="mobile" /></label>
      <label>学校 <input name="school" /></label>
      <label>专业 <input name="major" /></label>
      <label>技能 <textarea name="skills"></textarea></label>
      <label>城市
        <select name="city">
          <option value="">Select</option>
          <option>Shanghai</option>
          <option>Beijing</option>
          <option>Shenzhen</option>
        </select>
      </label>
      <label>验证码 <input name="captcha" /></label>
      <button type="button">Submit button stays manual</button>
    </form>
  </body>
</html>
```

- [ ] **Step 2: Update extension README with verification**

Append to `extension/README.md`:

```markdown
## Manual Verification

1. Start ResuMate backend at `http://127.0.0.1:8000`.
2. Log in through the main app and copy the JWT from local storage, or call `/auth/login` and copy `access_token`.
3. Load the unpacked extension.
4. Open `extension/fixtures/application-form.html` in the browser.
5. Open the extension side panel.
6. Set backend URL and token.
7. Refresh profiles.
8. Scan page.
9. Confirm high-confidence fields are checked.
10. Click Fill Selected.
11. Verify normal fields are filled and the captcha field remains unchanged.
12. Verify the submit button was not clicked.
```

- [ ] **Step 3: Run final backend tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_autofill_profile.py backend\tests\test_autofill_matching.py backend\tests\test_autofill_routes.py backend\tests\test_main_entrypoint.py -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Run frontend build smoke test**

Run:

```powershell
npm.cmd run build
```

Working directory: `frontend`

Expected: Vue typecheck and Vite build pass.

- [ ] **Step 5: Run extension syntax checks**

Run:

```powershell
node --check extension\service-worker.js
node --check extension\lib\constants.js
node --check extension\lib\storage.js
node --check extension\lib\api-client.js
node --check extension\lib\field-matcher.js
node --check extension\content\fill-engine.js
node --check extension\content\scraper.js
node --check extension\sidepanel\sidepanel.js
node -e "JSON.parse(require('fs').readFileSync('extension/manifest.json','utf8')); console.log('manifest ok')"
```

Expected: syntax checks exit 0 and manifest prints `manifest ok`.

- [ ] **Step 6: Commit**

Run:

```powershell
git -c safe.directory=C:/Users/Zhu/Desktop/code/ResuMate-Agent add extension/fixtures/application-form.html extension/README.md
git -c safe.directory=C:/Users/Zhu/Desktop/code/ResuMate-Agent commit -m "test: add autofill extension fixture"
```

## Final Review Checklist

- [ ] `GET /api/autofill/profiles` returns only current-user resumes.
- [ ] `GET /api/autofill/profiles/{profile_id}` rejects invalid or missing resume profiles.
- [ ] `POST /api/autofill/match` blocks sensitive fields.
- [ ] `POST /api/autofill/events` logs no full field values.
- [ ] Extension can load cached profile data when the backend is unavailable.
- [ ] Extension scans visible fillable controls and ignores hidden, file, password, and submit controls.
- [ ] Extension fills only selected matches.
- [ ] Extension never clicks submit-like buttons.
- [ ] `extension/fixtures/application-form.html` verifies Chinese labels and sensitive-field blocking.

## Handoff Notes

- Keep the first version in plain JavaScript. Add a build system only when the extension needs package dependencies or bundled tests.
- If LLM fallback is added during execution, make it a separate commit after deterministic matching is passing.
- If the existing auth flow makes manual JWT entry awkward, add a small token helper endpoint or UI as a separate design update.
