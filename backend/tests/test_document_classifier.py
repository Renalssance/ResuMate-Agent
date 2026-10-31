import pytest
from pydantic import ValidationError

from backend.schemas.document_import import DocumentClassification
from backend.services import document_classifier
from backend.services.document_classifier import classify_document_content


def test_resume_structure_is_classified_without_filename():
    text = """教育经历
清华大学 计算机硕士
工作经历
模型评测工程师
项目经历
构建 VLM 评测平台"""
    assert classify_document_content(text) == DocumentClassification(
        document_type="resume", confidence="high", reason="检测到教育、工作和项目经历结构"
    )


def test_job_structure_is_classified_without_filename():
    text = """岗位职责
负责大模型评测平台建设
任职要求
熟悉 Python 和 Pytest
加分项
具备 Agent 工程经验"""
    assert classify_document_content(text) == DocumentClassification(
        document_type="jd", confidence="high", reason="检测到岗位职责、任职要求和加分项结构"
    )


def test_mixed_or_unstructured_content_defers_to_model():
    assert classify_document_content("我们希望找到合适的人，一起建设模型评测系统。") is None
    assert classify_document_content("工作经历\n任职要求\n熟悉 Python") is None


@pytest.mark.parametrize("invalid", [
    {"document_type": "other"},
    {"confidence": "certain"},
    {"reason": ""},
    {"reason": "理" * 161},
    {"filename": "resume.pdf"},
])
def test_classification_rejects_invalid_results(invalid):
    data = {"document_type": "ambiguous", "confidence": "low", "reason": "正文不足"}
    with pytest.raises(ValidationError):
        DocumentClassification(**(data | invalid))


@pytest.mark.parametrize("document_type, confidence", [("jd", "medium"), ("ambiguous", "low")])
def test_fallback_sends_only_content_to_model(monkeypatch, document_type, confidence):
    captured = {}
    guard = lambda: None
    progress_callback = lambda **kwargs: None

    class Harness:
        def __init__(self, **kwargs):
            captured["init"] = kwargs

        def run_schema(self, **kwargs):
            captured.update(kwargs)
            return DocumentClassification(
                document_type=document_type, confidence=confidence, reason="信息不足"
            )

    monkeypatch.setattr(document_classifier, "AgentHarness", Harness)
    result = document_classifier.classify_document(
        "岗位相关说明", user_id=7, guard=guard, progress_callback=progress_callback
    )
    assert result == DocumentClassification(
        document_type=document_type, confidence=confidence, reason="信息不足"
    )
    assert captured["init"] == {
        "user_id": 7, "guard": guard, "progress_callback": progress_callback
    }
    assert captured["variables"] == {"document_text": "岗位相关说明"}
    assert "filename" not in captured["variables"]
    assert captured["task"] == "document.classify"
    assert captured["prompt_name"] == "classify_document"
    assert captured["schema"] is DocumentClassification
    assert captured["progress_stage"] == "classify"
    assert captured["progress"] == 35


def test_fallback_limits_model_content_to_24000_characters(monkeypatch):
    captured = {}

    class Harness:
        def __init__(self, **kwargs):
            pass

        def run_schema(self, **kwargs):
            captured.update(kwargs)
            return DocumentClassification(document_type="ambiguous", confidence="low", reason="信息不足")

    monkeypatch.setattr(document_classifier, "AgentHarness", Harness)
    document_classifier.classify_document("正" * 24000 + "文", user_id=7)
    assert captured["variables"] == {"document_text": "正" * 24000}


def test_high_confidence_structural_result_skips_model(monkeypatch):
    def fail_model_setup(**kwargs):
        raise AssertionError("model must not run")

    monkeypatch.setattr(document_classifier, "AgentHarness", fail_model_setup)
    result = document_classifier.classify_document(
        "教育经历\n学校\n工作经历\n公司\n项目经历\n平台", user_id=7
    )
    assert result.document_type == "resume"
    assert result.confidence == "high"


@pytest.mark.parametrize("text, document_type", [
    (" EDUCATION:\n学校\nWork Experience：\n公司", "resume"),
    ("Responsibilities:\n建设平台\nQualifications：\nPython", "jd"),
    ("工作经历\n工作经历\n工作经历", None),
    ("教育经历丰富\n工作经历丰富", None),
    ("教育经历\n工作经历\n任职要求", None),
])
def test_structural_rules_require_distinct_complete_unmixed_headings(text, document_type):
    result = classify_document_content(text)
    assert (result.document_type if result else None) == document_type
