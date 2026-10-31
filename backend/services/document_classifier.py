import re

from backend.agents.harness import AgentHarness
from backend.schemas.document_import import DocumentClassification

RESUME_SECTIONS = {
    "教育": re.compile(r"^(教育经历|教育背景|education)$", re.I),
    "工作": re.compile(r"^(工作经历|实习经历|职业经历|work experience|experience)$", re.I),
    "项目": re.compile(r"^(项目经历|项目经验|projects?)$", re.I),
    "技能": re.compile(r"^(专业技能|技能清单|技术能力|skills?)$", re.I),
    "成果": re.compile(r"^(论文发表|研究成果|荣誉奖项|publications?|awards?)$", re.I),
}
JD_SECTIONS = {
    "岗位职责": re.compile(r"^(岗位职责|职位职责|工作职责|responsibilities)$", re.I),
    "任职要求": re.compile(r"^(任职要求|职位要求|岗位要求|requirements|qualifications)$", re.I),
    "加分项": re.compile(r"^(加分项|优先条件|preferred qualifications)$", re.I),
    "薪酬福利": re.compile(r"^(薪酬福利|员工福利|benefits?)$", re.I),
    "工作地点": re.compile(r"^(工作地点|办公地点|workplace|location)$", re.I),
}


def _matched_sections(text: str, patterns: dict[str, re.Pattern[str]]) -> list[str]:
    lines = [re.sub(r"[：:]$", "", line.strip()) for line in text.splitlines() if line.strip()]
    return [label for label, pattern in patterns.items() if any(pattern.fullmatch(line) for line in lines)]


def classify_document_content(text: str) -> DocumentClassification | None:
    resume = _matched_sections(text, RESUME_SECTIONS)
    jd = _matched_sections(text, JD_SECTIONS)
    if len(resume) >= 2 and not jd:
        document_type, sections, suffix = "resume", resume, "经历结构"
    elif len(jd) >= 2 and not resume:
        document_type, sections, suffix = "jd", jd, "结构"
    else:
        return None
    reason = f"检测到{'、'.join(sections[:-1])}和{sections[-1]}{suffix}"
    return DocumentClassification(document_type=document_type, confidence="high", reason=reason)


def classify_document(text: str, *, user_id: int, guard=None,
                      progress_callback=None) -> DocumentClassification:
    structural = classify_document_content(text)
    if structural is not None:
        return structural
    return AgentHarness(user_id=user_id, guard=guard,
                        progress_callback=progress_callback).run_schema(
        task="document.classify",
        prompt_name="classify_document",
        schema=DocumentClassification,
        variables={"document_text": text[:24000]},
        progress_stage="classify",
        progress=35,
    )
