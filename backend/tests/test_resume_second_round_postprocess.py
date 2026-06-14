from __future__ import annotations

from backend.rag.milvus import build_resume_semantic_summary
from backend.schemas.workflow import ResumeProfile
from backend.services.documents import PageText, chunk_pages
from backend.services.resume_postprocess import postprocess_resume_profile


def test_resume_postprocess_extracts_contact_with_source_refs_and_quality_warnings():
    chunks = chunk_pages(
        pages=[
            PageText(
                page_number=1,
                text="\n".join(
                    [
                        "Ada Lovelace",
                        "Phone: 138-0000-0000",
                        "Email: ada@example.com",
                        "Address: Beijing Haidian",
                    ]
                ),
            )
        ],
        run_id=1,
        candidate_id=2,
        document_type="resume",
        filename="resume.pdf",
    )
    profile = ResumeProfile(candidate_name="Ada Lovelace", contact={})

    processed = postprocess_resume_profile(profile, chunks)

    assert processed.contact["phone"] == "138-0000-0000"
    assert processed.contact["email"] == "ada@example.com"
    assert processed.contact["address"] == "Beijing Haidian"
    contact_refs = processed.structured_ambiguities[-1]["contact_source_refs"]
    assert {item["field"] for item in contact_refs} == {"phone", "email", "address"}
    assert all(item["source_refs"][0]["page_number"] == 1 for item in contact_refs)
    assert processed.quality["contact_extracted"] is True
    assert processed.quality["status"] == "success"


def test_resume_postprocess_fills_descriptions_and_normalizes_skill_evidence():
    chunks = chunk_pages(
        pages=[
            PageText(
                page_number=1,
                text="\n".join(
                    [
                        "Experience",
                        "Acme Backend Engineer 2024.01-2024.06",
                        "- Built Docker deployment for APIs.",
                        "Skills",
                        "Proficient Java SpringBoot",
                        "Education",
                        "Machine Learning course",
                    ]
                ),
            )
        ],
        run_id=1,
        candidate_id=2,
        document_type="resume",
        filename="resume.pdf",
    )
    profile = ResumeProfile.model_validate(
        {
            "candidate_name": "Ada",
            "work_experience": [
                {
                    "company": "Acme",
                    "title": "Backend Engineer",
                    "bullets": [{"raw_text": "Built Docker deployment for APIs."}],
                }
            ],
            "projects": [{"name": "Launch", "description": "", "bullets": [{"raw_text": "Improved conversion by 50%."}]}],
            "skills": [
                {"name": "Docker", "evidence_level": "mentioned"},
                {"name": "Java", "evidence_level": "mentioned"},
                {"name": "SpringBoot", "evidence_level": "mentioned"},
                {"name": "Machine Learning", "evidence_level": "mentioned"},
            ],
        }
    )

    processed = postprocess_resume_profile(profile, chunks)

    assert processed.work_experience[0].description == "Built Docker deployment for APIs."
    assert processed.projects[0].description == "Improved conversion by 50%."
    levels = {skill.name: skill.evidence_level for skill in processed.skills}
    assert levels["Docker"] == "demonstrated"
    assert levels["Java"] == "self_claimed"
    assert levels["SpringBoot"] == "self_claimed"
    assert levels["Machine Learning"] == "course_only"


def test_resume_summary_deduplicates_aliases_and_chunk_versions_are_non_empty(monkeypatch):
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("EMBEDDING_VERSION", raising=False)
    chunks = chunk_pages(
        pages=[PageText(page_number=1, text="Projects\nBuilt with Kubernetes and K8s.\nSkills\nSpring Boot SpringBoot")],
        run_id=1,
        candidate_id=2,
        document_type="resume",
        filename="resume.pdf",
    )
    content = {
        "candidate_name": "Ada",
        "skills": [
            {"name": "Kubernetes", "evidence_level": "demonstrated"},
            {"name": "K8s", "evidence_level": "demonstrated"},
            {"name": "Spring Boot", "evidence_level": "self_claimed"},
            {"name": "SpringBoot", "evidence_level": "self_claimed"},
        ],
        "work_experience": [{"description": "Used Kubernetes for deployment.", "technologies": ["K8s"]}],
    }

    summary = build_resume_semantic_summary(content)

    assert summary.count("Kubernetes") == 1
    assert summary.count("SpringBoot") == 1
    assert chunks[0].metadata["embedding_text"]
    assert chunks[0].metadata["ocr_version"] == "unknown"
    assert chunks[0].metadata["embedding_model"] == "unknown"
    assert chunks[0].metadata["embedding_version"] == "unknown"
