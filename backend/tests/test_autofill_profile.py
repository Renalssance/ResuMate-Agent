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
