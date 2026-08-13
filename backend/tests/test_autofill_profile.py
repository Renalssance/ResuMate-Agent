from backend.schemas.autofill import (
    ApplicationField,
    ApplicationProfile,
    AutofillMatchResponse,
    MatchSuggestion,
    PageElement,
)
from datetime import datetime, timezone

from backend.db.models import Resume
from backend.services.autofill import build_application_profile, flatten_application_fields


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


def test_build_application_profile_maps_resume_profile_fields():
    resume = Resume(
        id=7,
        user_id=1,
        filename="ada.pdf",
        raw_text="",
        structured_data={
            "candidate_name": "Ada Lovelace",
            "contact": {"email": "ada@example.com", "phone": "1234567890", "location": "Shanghai"},
            "application": {
                "referral_code": "BT-123",
                "gender": "Female",
                "birth_date": "1999.01.01",
                "ethnicity": "Han",
                "nationality": "China",
                "id_document_type": "Chinese Resident ID",
                "expected_salary": "20k-30k",
                "current_address": "Shanghai Pudong",
                "portfolio_url": "https://ada.dev",
                "linkedin_url": "https://linkedin.com/in/ada",
            },
            "education": [
                {
                    "school": "Example University",
                    "degree": "MS",
                    "major": "Computer Science",
                    "years": "2022-2024",
                    "college": "School of Computing",
                    "lab": "AI Lab",
                    "research_direction": "Agent systems",
                    "advisor": "Dr. Turing",
                }
            ],
            "work_experience": [
                {
                    "company": "Analytical Engines Ltd",
                    "title": "Backend Engineer",
                    "duration": "2024-2026",
                    "start_date": "2024.01",
                    "end_date": "2026.02",
                    "description": "Built FastAPI services.",
                    "bullets": [{"raw_text": "Reduced latency by 30%."}],
                }
            ],
            "projects": [
                {
                    "name": "Resume Agent",
                    "role": "Developer",
                    "duration": "2025.01 - 2025.06",
                    "start_date": "2025.01",
                    "end_date": "2025.06",
                    "url": "https://github.com/ada/resume-agent",
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
    assert fields["application.referral_code"] == "BT-123"
    assert fields["application.gender"] == "Female"
    assert fields["application.birth_date"] == "1999.01.01"
    assert fields["application.ethnicity"] == "Han"
    assert fields["application.nationality"] == "China"
    assert fields["application.id_document_type"] == "Chinese Resident ID"
    assert fields["application.expected_salary"] == "20k-30k"
    assert fields["application.current_address"] == "Shanghai Pudong"
    assert fields["application.portfolio_url"] == "https://ada.dev"
    assert fields["application.linkedin_url"] == "https://linkedin.com/in/ada"
    assert fields["education.0.school"] == "Example University"
    assert fields["education.0.college"] == "School of Computing"
    assert fields["education.0.lab"] == "AI Lab"
    assert fields["education.0.research_direction"] == "Agent systems"
    assert fields["education.0.advisor"] == "Dr. Turing"
    assert fields["work_experience.0.start_date"] == "2024.01"
    assert fields["work_experience.0.end_date"] == "2026.02"
    assert fields["work_experience.0.description"] == "Built FastAPI services.\nReduced latency by 30%."
    assert fields["projects.0.url"] == "https://github.com/ada/resume-agent"
    assert fields["projects.0.duration"] == "2025.01 - 2025.06"
    assert fields["projects.0.start_date"] == "2025.01"
    assert fields["projects.0.end_date"] == "2025.06"
    assert fields["projects.0.description"] == "Built document parsing workflow.\nAdded OCR fallback."
    assert fields["skills"] == "Python, FastAPI"


def test_build_application_profile_ignores_malformed_structured_data():
    resume = Resume(
        id=8,
        user_id=1,
        filename="malformed.pdf",
        raw_text="",
        structured_data=["bad"],
        created_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
    )

    profile = build_application_profile(resume)
    fields = {field.key: field.value for field in flatten_application_fields(profile)}

    assert profile.id == "resume:8"
    assert profile.name == "malformed.pdf"
    assert fields["candidate_name"] == "malformed.pdf"


def test_build_application_profile_accepts_legacy_experience_key():
    resume = Resume(
        id=9,
        user_id=1,
        filename="grace.pdf",
        raw_text="",
        structured_data={
            "candidate_name": "Grace Hopper",
            "experience": [
                {
                    "company": "Navy",
                    "title": "Computer Scientist",
                    "duration": "1944-1986",
                    "description": "Built compiler systems.",
                }
            ],
        },
        created_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
    )

    profile = build_application_profile(resume)
    fields = {field.key: field.value for field in flatten_application_fields(profile)}

    assert fields["work_experience.0.company"] == "Navy"
    assert fields["work_experience.0.title"] == "Computer Scientist"
    assert fields["work_experience.0.duration"] == "1944-1986"
    assert fields["work_experience.0.description"] == "Built compiler systems."
