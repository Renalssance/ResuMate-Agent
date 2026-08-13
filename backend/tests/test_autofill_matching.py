from datetime import datetime, timezone

from backend.db.models import Resume
from backend.schemas.autofill import ApplicationField, ApplicationProfile, ApplicationSection, PageElement
from backend.services.autofill import build_application_profile, match_application_fields


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


def _project_profile() -> ApplicationProfile:
    return ApplicationProfile(
        id="resume:2",
        name="Zhu",
        source_resume_id="resume:2",
        updated_at="2026-08-06T00:00:00Z",
        sections=[
            ApplicationSection(
                id="projects",
                label="Projects",
                fields=[
                    ApplicationField(key="projects.0.name", label="Project 1", value="多Agent 智能旅行规划助手", aliases=["project", "项目"], category="project", confidence="high", source="resume"),
                    ApplicationField(key="projects.0.role", label="Project Role 1", value="后端开发", aliases=["project role", "角色"], category="project", confidence="high", source="resume"),
                    ApplicationField(key="projects.0.duration", label="Project Dates 1", value="2025.01 - 2025.06", aliases=["project date", "起止时间"], category="project", confidence="high", source="resume"),
                    ApplicationField(key="projects.0.description", label="Project Description 1", value="负责 Agent 编排、RAG 检索和行程生成。", aliases=["project description", "项目描述"], category="project", confidence="high", source="resume"),
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


def test_match_application_fields_does_not_match_mailing_address_as_email():
    response_with_email = match_application_fields(
        _profile(),
        [
            PageElement(index=0, tag="input", type="text", label_text="Mailing Address"),
            PageElement(index=1, tag="input", type="email", label_text="Email"),
        ],
    )
    response_without_email = match_application_fields(
        _profile(),
        [PageElement(index=0, tag="input", type="text", label_text="Mailing Address")],
    )

    assert [(item.field_key, item.element_index) for item in response_with_email.matches] == [("contact.email", 1)]
    assert response_without_email.matches == []


def test_match_application_fields_matches_bytedance_project_experience_labels_from_built_profile():
    profile = build_application_profile(
        Resume(
            id=2,
            user_id=1,
            filename="zhu.pdf",
            raw_text="",
            structured_data={
                "candidate_name": "Zhu",
                "projects": [
                    {
                        "name": "多Agent 智能旅行规划助手",
                        "role": "后端开发",
                        "duration": "2025.01 - 2025.06",
                        "description": "负责 Agent 编排、RAG 检索和行程生成。",
                    }
                ],
            },
            created_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
            updated_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
        )
    )

    response = match_application_fields(
        profile,
        [
            PageElement(index=0, tag="input", type="text", label_text="项目名称"),
            PageElement(index=1, tag="input", type="text", label_text="项目角色"),
            PageElement(index=2, tag="input", type="text", label_text="起止时间"),
            PageElement(index=3, tag="input", type="text", label_text="项目链接"),
            PageElement(index=4, tag="textarea", type="", label_text="描述"),
        ],
    )

    assert [(item.field_key, item.element_index) for item in response.matches] == [
        ("projects.0.name", 0),
        ("projects.0.role", 1),
        ("projects.0.duration", 2),
        ("projects.0.description", 4),
    ]


def test_match_application_fields_does_not_fill_project_link_without_url_field():
    response = match_application_fields(
        _project_profile(),
        [PageElement(index=0, tag="input", type="text", label_text="项目链接")],
    )

    assert response.matches == []
