from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.graph.candidate_workflow import CandidateAnalysisGraph
from backend.rag.milvus import DOCUMENT_COLLECTION, PROFILE_COLLECTION, MilvusRagStore, build_resume_semantic_summary
from backend.schemas.workflow import ResumeProfile
from backend.services.documents import PageText, chunk_pages, normalize_ocr_text
from backend.services.llm_validation import validate_resume_source_refs
from backend.services.resume_postprocess import postprocess_resume_profile

from backend.tests.test_rag_filters import FakeEmbedding, _ready_client


def test_section_detection_uses_whitelist_not_short_body_lines():
    chunks = chunk_pages(
        pages=[
            PageText(
                page_number=1,
                text="\n".join(
                    [
                        "教育经历",
                        "浙江大学 计算机科学 2020-2024",
                        "上的准确率提升12%。",
                        "力提升3倍。",
                        "实习经历",
                        "某互联网大厂 后端开发实习生 2024.06-2024.09",
                    ]
                ),
            )
        ],
        run_id=1,
        candidate_id=2,
        document_type="resume",
        filename="resume.pdf",
        chunk_size=120,
    )

    sections = {chunk.section for chunk in chunks}
    assert "上的准确率提升12%。" not in sections
    assert "力提升3倍。" not in sections
    assert {"教育经历", "实习经历"} <= sections


def test_chunking_splits_top_level_sections_and_keeps_work_context_across_pages():
    pages = [
        PageText(
            page_number=1,
            text="\n".join(
                [
                    "教育经历",
                    "浙江大学 软件工程 本科 2020-2024",
                    "实习经历",
                    "某互联网大厂",
                    "后端开发实习生",
                    "2024.06-2024.09",
                    "- 使用 Docker 和 K8s 建设部署流程。",
                ]
            ),
        ),
        PageText(
            page_number=2,
            text="\n".join(
                [
                    "- 引入 Redis 和消息队列，吞吐提升3倍。",
                    "项目经历",
                    "智能问答平台",
                    "- 基于多模态大模型完成检索增强。",
                    "专业技能",
                    "Java Go SpringBoot Django MySQL PostgreSQL CI/CD",
                ]
            ),
        ),
    ]

    chunks = chunk_pages(
        pages=pages,
        run_id=1,
        candidate_id=2,
        document_type="resume",
        filename="resume.pdf",
        chunk_size=90,
    )

    assert not any("教育经历" in chunk.text and "实习经历" in chunk.text for chunk in chunks)
    assert not any("项目经历" in chunk.text and "专业技能" in chunk.text for chunk in chunks)
    assert any("多模态大模型" in chunk.text for chunk in chunks)
    assert not any(chunk.text.startswith("态大模型") for chunk in chunks)
    redis_chunk = next(chunk for chunk in chunks if "Redis" in chunk.text)
    assert redis_chunk.page_number == 2
    assert "章节：实习经历" in redis_chunk.text
    assert "公司：某互联网大厂" in redis_chunk.text
    assert "职位：后端开发实习生" in redis_chunk.text
    assert "时间：2024.06-2024.09" in redis_chunk.text
    assert redis_chunk.metadata["page_start"] == 2
    assert redis_chunk.metadata["page_end"] == 2
    assert redis_chunk.metadata["normalized"] is True


def test_chunking_keeps_pipe_delimited_work_entries_without_bullets():
    chunks = chunk_pages(
        pages=[
            PageText(
                page_number=1,
                text="\n".join(
                    [
                        "实习经历",
                        "某互联网大厂|后端开发实习生|2024.06-2024.09",
                        "负责高并发秒杀系统的接口优化，通过引I入Redis缓存与消息队列削峰，使系统QPS承载能力提升3倍。",
                    ]
                ),
            ),
            PageText(
                page_number=2,
                text="\n".join(
                    [
                        "参与微服务架构重构，使用Docker容器化部署核心模块，配合K8s实现自动化扩缩容，资源利用率提升25%。",
                        "项目经验",
                        "XX品牌AIGC营销实战",
                    ]
                ),
            ),
        ],
        run_id=1,
        candidate_id=2,
        document_type="resume",
        filename="resume.pdf",
        chunk_size=180,
    )

    redis_chunk = next(chunk for chunk in chunks if "Redis" in chunk.text)
    docker_chunk = next(chunk for chunk in chunks if "Docker" in chunk.text)

    assert redis_chunk.section == "实习经历"
    assert docker_chunk.section == "实习经历"
    assert "公司：某互联网大厂" in redis_chunk.text
    assert "职位：后端开发实习生" in docker_chunk.text
    assert "时间：2024.06-2024.09" in docker_chunk.text


def test_source_ref_validation_rejects_bad_chunk_page_and_non_contiguous_text_but_allows_whitespace():
    chunks = chunk_pages(
        pages=[PageText(page_number=1, text="项目经历\n智能问答平台\n使用 LoRA 与 RAG 微调 Llama-3。")],
        run_id=1,
        candidate_id=2,
        document_type="resume",
        filename="resume.pdf",
    )
    chunk = next(item for item in chunks if "LoRA" in item.text)

    profile = ResumeProfile(
        candidate_name="小文",
        source_refs=[
            {
                "chunk_id": chunk.id,
                "page_number": 1,
                "section": "项目经历",
                "text": "使用 LoRA 与 RAG\n微调 Llama-3。",
            }
        ],
    )
    validate_resume_source_refs(profile, chunks)
    assert profile.source_refs[0].text == "使用 LoRA 与 RAG\n微调 Llama-3。"

    profile.source_refs[0].chunk_id = "missing"
    with pytest.raises(ValueError, match="unknown chunk_id"):
        validate_resume_source_refs(profile, chunks)

    profile.source_refs[0].chunk_id = chunk.id
    profile.source_refs[0].page_number = 2
    with pytest.raises(ValueError, match="page mismatch"):
        validate_resume_source_refs(profile, chunks)

    profile.source_refs[0].page_number = 1
    profile.source_refs[0].text = "使用 LoRA Llama-3"
    with pytest.raises(ValueError, match="non-verbatim source text"):
        validate_resume_source_refs(profile, chunks)


def test_resume_postprocess_removes_non_verbatim_source_refs_before_strict_validation():
    chunks = chunk_pages(
        pages=[PageText(page_number=1, text="Projects\nBuilt a retrieval augmented resume parser with page tracing.")],
        run_id=0,
        candidate_id=16,
        document_type="resume",
        filename="resume.pdf",
    )
    chunk = chunks[0]
    profile = ResumeProfile(
        candidate_name="Candidate",
        source_refs=[
            {
                "chunk_id": chunk.id,
                "page_number": 1,
                "section": "Projects",
                "text": "Built a corrected RAG resume parser",
            }
        ],
    )

    processed = postprocess_resume_profile(profile, chunks)

    validate_resume_source_refs(processed, chunks)
    assert processed.source_refs == []
    assert any(item.get("type") == "dropped_non_verbatim_source_ref" for item in processed.structured_ambiguities)


def test_ocr_normalization_preserves_raw_text_and_records_suspicious_tokens():
    raw = "资\n源利用率\n设\n计成本\n投\n稿至顶会\n引I入Redis\nAl平台"

    normalized = normalize_ocr_text(raw)

    assert normalized.raw_text == raw
    assert "资源利用率" in normalized.normalized_text
    assert "设计成本" in normalized.normalized_text
    assert "投稿至顶会" in normalized.normalized_text
    assert "引I入Redis" in normalized.normalized_text
    assert any("引I入" in item["text"] for item in normalized.ambiguities)
    assert any("Al" in item["text"] for item in normalized.ambiguities)


def test_resume_profile_schema_accepts_legacy_and_structured_fields():
    legacy = ResumeProfile.model_validate(
        {
            "candidate_name": "小文",
            "skills": ["Python"],
            "achievements": ["一等奖"],
        }
    )
    assert legacy.skills[0].name == "Python"
    assert legacy.achievements[0].name == "一等奖"
    assert legacy.self_summary == ""
    assert legacy.quality == {}

    structured = ResumeProfile.model_validate(
        {
            "candidate_name": "小文",
            "work_experience": [
                {
                    "company": "某互联网大厂",
                    "title": "后端开发实习生",
                    "start_date": "2024.06",
                    "end_date": "2024.09",
                    "bullets": [{"raw_text": "使用 Docker 和 K8s 建设部署流程。"}],
                    "technologies": ["Docker", "K8s"],
                    "metrics": [{"name": "吞吐", "value": "3倍"}],
                }
            ],
            "skills": [{"name": "LoRA", "evidence_level": "demonstrated"}],
            "achievements": [{"name": "一等奖", "level": "校级", "category": "竞赛"}],
        }
    )
    assert structured.work_experience[0].bullets[0].raw_text == "使用 Docker 和 K8s 建设部署流程。"
    assert structured.skills[0].evidence_level == "demonstrated"


def test_resume_profile_embedding_uses_semantic_resume_content_not_only_name():
    content = {
        "candidate_name": "小文",
        "education": [{"school": "浙江大学", "major": "软件工程", "courses": ["机器学习"]}],
        "work_experience": [
            {"company": "某互联网大厂", "title": "后端开发实习生", "technologies": ["Docker", "K8s"]}
        ],
        "projects": [{"name": "智能问答平台", "technologies": ["LoRA", "RAG"]}],
        "skills": [{"name": "SpringBoot", "evidence_level": "self_claimed"}],
        "achievements": [{"name": "一等奖"}],
    }
    summary = build_resume_semantic_summary(content)

    assert summary != "小文"
    assert "浙江大学" in summary
    assert "后端开发实习生" in summary
    assert "Docker" in summary
    assert "LoRA" in summary

    embedding = FakeEmbedding()
    client = _ready_client()
    store = MilvusRagStore(client=client, embedding_client=embedding)
    store.persist_document_profile(
        user_id=7,
        document_type="resume",
        document_id=21,
        summary="小文",
        content=content,
    )
    assert embedding.calls[0] == summary


def test_chunk_embedding_uses_normalized_text_and_preserves_metadata():
    embedding = FakeEmbedding()
    client = _ready_client()
    store = MilvusRagStore(client=client, embedding_client=embedding)
    chunks = chunk_pages(
        pages=[PageText(page_number=1, text="项目经历\n智能问答平台\n资\n源利用率提升12%。")],
        run_id=1,
        candidate_id=2,
        document_type="resume",
        filename="resume.pdf",
    )

    store.index_chunks(user_id=7, document_id=21, chunks=chunks)

    row = client.upsert_calls[0]["data"][0]
    assert embedding.calls[0] == chunks[0].metadata["embedding_text"]
    assert row["metadata"]["raw_text"]
    assert row["metadata"]["section"] == row["section"]
    assert "entity_id" in row["metadata"]
    assert "page_start" in row["metadata"]


def test_candidate_match_prompt_receives_resume_profile_and_ambiguities():
    calls = {}

    class Harness:
        def run_schema(self, **kwargs):
            calls.update(kwargs)
            return kwargs["schema"](
                evaluations=[
                    {
                        "criterion_id": "c1",
                        "name": "Python",
                        "weight": 100,
                        "score": 0,
                        "status": "no_evidence",
                        "reason": "No evidence.",
                        "evidence_chunk_ids": [],
                    }
                ]
            )

    graph = object.__new__(CandidateAnalysisGraph)
    graph.harness = Harness()
    state = {
        "task_id": "",
        "run_id": 1,
        "candidate_id": 2,
        "job_profile": SimpleNamespace(
            criteria=[
                SimpleNamespace(
                    criterion_id="c1",
                    name="Python",
                    weight=100,
                    model_dump=lambda **_kwargs: {"criterion_id": "c1", "name": "Python", "weight": 100},
                )
            ]
        ),
        "resume_profile": ResumeProfile(
            candidate_name="小文",
            structured_ambiguities=[{"type": "ocr", "text": "引I入"}],
        ),
        "evidence_by_criterion": {"c1": []},
    }

    CandidateAnalysisGraph.evaluate_match(graph, state)

    variables = calls["variables"]
    assert "resume_profile_json" in variables
    assert variables["resume_profile_json"]["candidate_name"] == "小文"
    assert variables["ambiguities_json"] == [{"type": "ocr", "text": "引I入"}]
