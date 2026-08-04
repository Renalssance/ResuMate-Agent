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
