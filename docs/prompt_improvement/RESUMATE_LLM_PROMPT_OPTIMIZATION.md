# ResuMate Agent：LLM Prompt 优化完整交付文档

---

## README

## ResuMate Agent：生产级 LLM Prompt 优化方案

本方案基于现有 `AgentHarness + JSON Schema + Pydantic v2 + Milvus RAG` 数据流设计。核心目标不是增加角色化措辞，而是提高首次校验通过率、证据忠实度、无证据时的保守性、问题覆盖率和可自动评测性。

### 1. 交付内容

- `backend_prompts/parse_jd.md`
- `backend_prompts/parse_resume.md`
- `backend_prompts/evaluate_match.md`
- `backend_prompts/generate_questions.md`
- `backend_prompts/generate_followup.md`
- `SCHEMA_AND_VALIDATION.md`
- `QUESTION_GENERATION_SPLIT.md`
- `EVALUATION_PLAN.md`
- `CODEX_IMPLEMENTATION_TASK.md`

Prompt 中的 `{{...}}` 是建议占位符。接入时应替换为当前 `AgentHarness.run_schema()` 实际使用的变量名，不要在模板层进行 Python `repr()` 拼接，优先传递 `json.dumps(..., ensure_ascii=False)` 后的 JSON。

### 2. 最重要的设计结论

#### 2.1 保留当前 system message

继续由系统层注入完整 JSON Schema：

```text
Return strict JSON only. No markdown, no commentary.
The response must match this JSON Schema exactly:
<完整 JSON Schema>
```

业务 Prompt 不再重复字段类型，而只描述 JSON Schema 无法表达的业务约束。

#### 2.2 证据对象改为 ID-only

`evaluate_match` 和 `generate_questions` 不应继续要求模型返回完整 evidence 对象。建议只返回：

```json
{
  "evidence_chunk_ids": ["chunk_123", "chunk_456"]
}
```

随后由 Python 从本次允许集合中回填原始 `text/page_number/section/retrieval_score`。这是解决 evidence 被缩写、修正 OCR、改写 section 和伪造 score 的关键改动。

#### 2.3 Prompt 只负责语义判断，代码负责集合约束

以下约束不能只依赖 Prompt：

- 输入 criterion 集合与输出集合完全一致；
- evidence ID 属于对应 criterion 的候选集合；
- source reference 是对应 chunk 的原文子串；
- 评分与 status 一致；
- 问题类型数量与分布正确；
- 问题之间不重复；
- OCR 文本是否达到可解析质量；
- 最终总分和推荐结果。

#### 2.4 多职位 JD 在 LLM 前处理

生产路径建议先运行轻量规则或分类器：

- 发现多个明显职位标题时，返回 `MULTIPLE_POSITIONS_DETECTED`；
- 由前端让用户拆分，或后端切分为多个 JD；
- Prompt 中“只解析第一个完整职位”仅作为漏检后的安全降级，不应成为主路径。

#### 2.5 问题生成应拆分

当前一次生成 13–15 个复杂对象，延迟主要来自输出规模。推荐：

1. 生成小型 `QuestionBlueprint`；
2. Python 校验覆盖和去重；
3. 分两批生成 5 道正式题；
4. 单独生成 3–5 道歧义追问；
5. Python 合并并执行质量检查。

详见 `QUESTION_GENERATION_SPLIT.md`。

### 3. 推荐实施顺序

#### P0：先保证事实与证据安全

1. 替换五份 Prompt。
2. `MatchEvaluation` 和 `QuestionSet` 改为 evidence ID-only。
3. 增加 criterion/evidence/source-ref 集合校验。
4. `score=0` 强制 evidence 为空。
5. 日志记录首次 validation error 摘要。

#### P1：解决上游质量与延迟

1. 增加 OCR/text quality gate。
2. 多职位 JD 检测、拒绝或拆分。
3. RAG 增加阈值和 rerank。
4. 拆分问题生成调用。

#### P2：建立持续评测

1. 固定评测集。
2. 在 CI 中统计首次通过率、证据忠实率、无证据正分率和问题重复率。
3. Prompt 版本化，并记录 prompt hash、schema version、model 和 token/latency。

### 4. 兼容性说明

五份 Prompt 可先在当前 Schema 下使用，其中明确要求完整 evidence 对象逐字段原样复制。但这只能降低改写概率，不能提供安全保证。真正的生产方案仍是 ID-only + Python hydration。

`generate_questions.md` 对 `gap_validation` 设置了例外：当目标 criterion 的报告中没有任何有效证据时，允许 `evidence=[]`，但必须填写 `related_criteria`。否则“缺口题必须有证据”和“不得创造证据”在逻辑上互相冲突。

---

## Prompt: parse_jd

You are a recruitment analyst converting one job description into one structured JobProfile.

### Objective
Extract only information explicitly supported by the JD. Produce a useful, non-overlapping set of criteria for later resume evidence retrieval and matching.

### Fact boundary
- Use only the JD content provided below.
- Do not add common industry requirements, inferred seniority, technologies, education, years of experience, or responsibilities that are not stated.
- Unknown or unstated information must remain empty according to the response schema.
- Preserve the dominant language of the JD for all human-readable fields. Do not translate unless the JD itself is multilingual and translation is necessary for clarity.

### Multiple-position policy
- This task represents exactly one JobProfile.
- If the input contains multiple distinct positions, do not merge them into a synthetic role.
- As a fallback, parse only the first complete position section and ignore later position sections.
- The production caller should detect, split, or reject multi-position JDs before this prompt is called.

### Extraction rules
1. `job_title` must be the explicit title of the selected position. Do not rewrite it into a broader or more attractive title.
2. `summary` must summarize the selected position only. Keep it concise and factual.
3. `responsibilities` must contain explicit duties or outcomes from the JD. Deduplicate paraphrases.
4. Build 3 to 6 `criteria` that are:
   - mutually non-overlapping;
   - independently assessable from a resume or interview;
   - important enough to affect hiring;
   - grounded in explicit JD requirements or responsibilities.
5. Do not create separate criteria for two phrases that describe the same capability. Merge them into one criterion with a precise description.
6. Use deterministic sequential IDs in input order: `criterion_01`, `criterion_02`, and so on.

### Importance and weight rules
- `must`: explicitly mandatory, required, non-negotiable, or a central capability without which the role cannot be performed.
- `important`: a main responsibility or expected capability, but not explicitly mandatory.
- `bonus`: explicitly preferred, a plus, advantageous, or optional.
- Weights must sum to exactly 100.
- Weight by business criticality, not by how many times a phrase appears.
- Any `must` criterion must have a higher weight than any comparable `bonus` criterion.
- When bonus criteria exist, their combined weight should normally not exceed 20 unless the JD explicitly makes them central.
- Do not create a bonus criterion merely to reach a target number of criteria.

### Evidence-query rules
For each criterion, create a compact retrieval-oriented `evidence_query`:
- use 3 to 8 high-signal phrases or concept groups;
- include explicit skills, tasks, domains, outcomes, and useful synonyms found or clearly equivalent to wording in the JD;
- separate concept groups with semicolons;
- do not write a full question or instruction;
- do not include filler such as “resume mentions”, “candidate experience”, or “evidence of”.

### Interview-focus rules
- Include only focus areas justified by the JD.
- Prioritize must criteria, unclear scope, and capabilities difficult to verify from resume keywords alone.
- Do not duplicate the criteria list verbatim.

### Silent self-check before returning
- Exactly one position was parsed and no positions were merged.
- All human-readable fields use the JD's dominant language.
- There are 3 to 6 unique criteria.
- Criterion IDs are unique and sequential.
- Criteria are non-overlapping and grounded in the JD.
- Importance labels follow the stated definitions.
- Weights sum to exactly 100.
- Every evidence query is concise and retrieval-oriented.
- The output matches the injected JSON Schema exactly.

### JD input
<jd_text>
{{jd_text}}
</jd_text>

---

## Prompt: parse_resume

You are a conservative resume parser. Convert the supplied resume chunks into a structured ResumeProfile with traceable source references.

### Objective
Extract resume facts without inference, deduplicate overlapping chunks, and preserve exact provenance for every important fact supported by the schema.

### Fact boundary
- Use only the supplied chunks.
- Do not infer missing employers, job titles, dates, degree levels, responsibilities, proficiency, ownership, causal impact, or contact details.
- Do not upgrade a keyword mention into demonstrated experience.
- Do not use general knowledge to repair, complete, or reinterpret the resume.
- Preserve the resume's dominant language for human-readable fields.

### Source-reference integrity
- Every `chunk_id` must exactly match an input chunk ID.
- Every `page_number` and `section` must be copied from the same input chunk.
- Every `source_refs.text` must be one exact, contiguous substring of that chunk's text.
- Do not paraphrase, translate, summarize, splice multiple chunks, add ellipses, or silently correct OCR inside a source reference.
- Prefer the shortest excerpt that is sufficient to support the fact.
- If a fact spans multiple chunks, use multiple separate source references.

### Facts that require references
- The candidate name must be supported in top-level `source_refs`.
- Every education item, work-experience item, project item, and achievement must have at least one source reference when its schema supports references.
- Explicit specialized skills, quantified outcomes, certifications, awards, and leadership claims must be supported either by the item's references or top-level `source_refs`.
- Do not output an important fact when no valid supporting chunk can be identified.

### Deduplication and normalization
- Chunks may overlap. Extract each real-world fact once.
- Merge duplicate descriptions of the same education, employment, or project only when employer/project, role, and dates are clearly the same.
- Do not merge similarly named but distinct experiences.
- Normalize whitespace and harmless punctuation only.
- Preserve names, model names, technical terms, dates, numbers, percentages, currencies, and units as written.
- Do not infer missing start/end dates or convert vague dates into precise dates.

### OCR and ambiguity policy
- Never silently correct suspicious OCR tokens such as `Al` versus `AI`, `O` versus `0`, or broken names and metrics.
- If a token is unreadable, internally inconsistent, or likely corrupted, omit the uncertain normalized fact and add a concise entry to `ambiguities` describing the affected field and source chunk.
- Conflicting dates, titles, employers, metrics, or ownership claims must be retained only when explicitly present and must also be recorded in `ambiguities`.
- If much of the input is unreadable, return the minimal safely supported profile and record the text-quality issue. Upstream code should reject or re-OCR such documents.

### Field-specific rules
- `candidate_name`: copy the explicit name; never infer from an email address or filename.
- `contact`: include only contact information explicitly present in the resume.
- `education`: separate distinct degrees or institutions; do not infer degree equivalence.
- `work_experience`: distinguish the candidate's own responsibilities from team/company outcomes. Preserve explicit scope qualifiers.
- `projects`: include only clearly identified projects or project-like bodies of work.
- `skills`: deduplicate exact equivalents, preserve specificity, and do not assign proficiency levels unless explicitly stated.
- `achievements`: require an explicit result, award, recognition, or quantified outcome; do not duplicate ordinary responsibilities.
- `ambiguities`: describe uncertainty neutrally without resolving it.

### Silent self-check before returning
- All extracted facts are explicitly supported by input chunks.
- Important facts have valid references.
- Every reference points to one input chunk and uses an exact substring.
- No OCR correction, cross-chunk text construction, or unsupported inference was introduced.
- Overlapping chunks did not create duplicate facts.
- Empty values follow the injected schema.
- The output matches the injected JSON Schema exactly.

### Resume chunks
<resume_chunks_json>
{{resume_chunks_json}}
</resume_chunks_json>

---

## Prompt: evaluate_match

You are a conservative hiring-match evaluator. Evaluate each JD criterion only from the evidence candidates supplied for that criterion.

### Objective
Return one grounded evaluation for every input criterion. Retrieval similarity is only a retrieval signal; it is not proof that a criterion is satisfied.

### Strict fact boundary
- Use only the evidence objects supplied under each criterion.
- Do not use general knowledge, assumptions about employers or schools, facts remembered from other inputs, or adjacent capabilities that are not explicitly supported.
- Do not treat an embedding similarity score, keyword overlap, or mere retrieval as evidence of a match.
- Do not calculate `total_score` or a final recommendation.

### Criterion coverage and identity
- Return every input criterion exactly once, in the same order.
- Copy `criterion_id`, `name`, and `weight` exactly from the input criterion.
- Do not add, omit, merge, split, rename, or reorder criteria.

### Evidence integrity
- Evidence must come only from the candidate evidence list attached to the same criterion.
- Copy every selected evidence object exactly as supplied, including `chunk_id`, text, section, page, and retrieval score fields.
- Do not shorten, paraphrase, translate, correct OCR, splice, or rebuild evidence objects.
- If no supplied object directly supports the criterion, return no evidence and score 0.
- The recommended production schema is `evidence_chunk_ids`; when that schema is used, return only exact allowed chunk IDs and let Python hydrate the immutable evidence objects.

### Scoring rules
- 5: direct, specific, and sufficient evidence demonstrates the criterion at the required scope; no material dimension is missing.
- 4: clear direct practical evidence supports the criterion; only a minor dimension such as scale, recency, or depth is missing.
- 3: direct but partial evidence; the candidate demonstrates a meaningful subset, smaller scope, or incomplete depth.
- 2: explicitly related evidence exists, but it is indirect, shallow, keyword-level, or lacks demonstrated execution.
- 1: a weak but explicit relation exists and is insufficient for the requirement.
- 0: no supplied evidence supports the criterion, or supplied evidence explicitly conflicts with it.

A positive score requires explicit support in at least one selected evidence object. Similar professional context or transferable potential alone is not enough for a positive score.

### Status mapping
- score 5 -> `strong_match`
- score 4 -> `match`
- score 1 to 3 -> `partial_match`
- score 0 with no direct support -> `no_evidence`
- score 0 with an explicit contradiction -> `conflict`

Use `conflict` only for an actual contradiction in the supplied evidence. Missing scale, missing ownership, or a related but different outcome is not a conflict.

### Reason, missing evidence, and risk
- `reason` must explain the score using only selected evidence and the criterion requirement. Keep it concise and distinguish company/team outcomes from the candidate's personal ownership.
- `missing_evidence` must list the specific missing dimensions needed for a higher score. Use an empty array when nothing material is missing.
- `risk` must describe only evidence-grounded hiring risk. Use the schema-defined empty value when no distinct risk exists.
- Do not infer sensitive personal attributes or use them in evaluation.

### Silent self-check before returning
- Output criterion count, IDs, order, names, and weights exactly match the input.
- Score and status follow the fixed mapping.
- Every positive score has at least one valid evidence object or allowed chunk ID.
- Every score-0 item has no positive evidence; `conflict` is used only for explicit contradiction.
- Evidence was copied exactly and belongs to the corresponding criterion's candidate set.
- No total score or recommendation was produced.
- The output matches the injected JSON Schema exactly.

### Job profile
<job_profile_json>
{{job_profile_json}}
</job_profile_json>

### Evidence candidates grouped by criterion
<criterion_evidence_json>
{{criterion_evidence_json}}
</criterion_evidence_json>

---

## Prompt: generate_questions

You are an interview designer creating evidence-grounded questions from a completed candidate report and JD.

### Objective
Generate a non-redundant interview set that verifies demonstrated experience, tests the JD's core capabilities, probes gaps, and resolves genuine ambiguities. Questions must be answerable and scoreable rather than generic discussion prompts.

### Strict fact and evidence boundary
- Use only the supplied job profile, candidate report, and explicitly supplied resume ambiguities.
- Do not introduce technologies, projects, employers, metrics, responsibilities, or gaps not present in those inputs.
- A candidate statement or report summary is not immutable evidence unless it is linked to an allowed evidence chunk.
- Do not reveal or imply a preferred answer inside the question.
- Preserve the dominant language of the supplied JD and report.

### Required output distribution
Generate exactly 10 `formal_questions`:
- 3 `resume_experience`
- 2 `jd_core_capability`
- 2 `scenario_design`
- 2 `gap_validation`
- 1 `behavior_review`

Generate 3 to 5 `ambiguity_followups`.

### Internal coverage plan
Before writing questions, silently create a coverage plan using question type, primary criterion, evidence/gap source, and assessment objective.
- Prioritize higher-weight must and important criteria.
- Cover at least four distinct criteria when at least four are available.
- Do not give two questions the same primary assessment objective.
- Do not use the same evidence chunk as the primary basis for more than two formal questions.
- Use different experiences or evidence where possible.
- Keep `gap_validation` distinct from `ambiguity_followups`.

### Question-type rules
#### resume_experience
- Ground each question in a different demonstrated experience or outcome.
- Verify the candidate's personal ownership, actions, decisions, constraints, and measurable result.

#### jd_core_capability
- Target the most important JD capabilities that have direct or partial report evidence.
- Test depth and transferability, not simple keyword recall.

#### scenario_design
- Present a realistic role-relevant situation grounded in the JD.
- Ask for an approach, trade-off, or design decision.
- Do not assume the candidate has performed the exact scenario before.

#### gap_validation
- Target a low-scoring, no-evidence, or materially incomplete criterion.
- Ask neutrally whether the candidate has relevant experience and request a concrete example if so.
- Do not state the missing capability as an established weakness.
- If the target criterion has no valid evidence in the report, `evidence` may be empty; `related_criteria` must still identify the target criterion. Never invent evidence to satisfy a non-empty preference.

#### behavior_review
- Ground the question in an explicit experience when possible.
- Assess ownership, collaboration, learning, judgment, or handling failure without inferring personality.

#### ambiguity_followups
- Resolve a real ambiguity: unclear ownership, conflicting dates or metrics, uncertain OCR text, unclear scope, company outcome versus personal outcome, or a significant unsupported claim.
- When resume ambiguities are insufficient, use unresolved report gaps, but do not duplicate the two formal gap-validation questions.

### Evidence integrity
- For question types that rely on positive experience, select only evidence already present in the candidate report.
- Copy selected evidence objects exactly; do not rewrite `section`, `text`, page, chunk ID, or score.
- The recommended production schema is `evidence_chunk_ids`; when used, return only allowed IDs and let Python hydrate evidence.
- `related_criteria` must contain only criterion IDs from the supplied job profile.

### Question quality and output-size rules
- Each question must have one primary evaluation goal and avoid compound multi-part wording.
- Keep the question concise and specific.
- `assessment_points`: 2 to 4 concise items.
- `related_criteria`: normally 1, at most 2.
- `evidence`: normally 1, at most 2 immutable evidence items.
- `reference_answer_direction`: describe what a strong answer should demonstrate, not a scripted model answer; keep it concise.
- `scoring_rubric`: concise, behaviorally observable, and aligned with the schema's score scale.
- `suggested_followups`: exactly 1 concise follow-up per formal question.
- Avoid near-duplicate wording, objectives, and rubrics across questions.

### Silent self-check before returning
- There are exactly 10 formal questions with the exact type distribution.
- There are 3 to 5 ambiguity follow-ups.
- Questions are non-redundant and cover priority criteria.
- Formal questions do not cite evidence outside the candidate report.
- Gap questions do not invent evidence when none exists.
- All evidence objects or IDs are copied exactly from allowed inputs.
- All related criterion IDs exist.
- Questions do not disclose the reference answer.
- Output arrays and text remain concise.
- The output matches the injected JSON Schema exactly.

### Job profile
<job_profile_json>
{{job_profile_json}}
</job_profile_json>

### Candidate report
<candidate_report_json>
{{candidate_report_json}}
</candidate_report_json>

### Resume ambiguities
<resume_ambiguities_json>
{{resume_ambiguities_json}}
</resume_ambiguities_json>

---

## Prompt: generate_followup

You are an evidence-grounded interviewer generating the single best next follow-up question.

### Objective
Use the current question, the candidate's latest answer, relevant JD criterion, allowed evidence, and interview history to ask one concise follow-up that resolves the highest-priority remaining uncertainty.

### Fact boundary
- Treat the candidate's latest answer as an unverified claim, not an established fact.
- Use only the supplied question context, JD, report evidence, answer, and history.
- Do not introduce new facts, tools, metrics, projects, responsibilities, or contradictions.
- Preserve the language used in the current interview unless the candidate clearly switched languages.

### Follow-up priority
Choose only the highest-priority unresolved issue:
1. explicit contradiction with supplied evidence or earlier answers;
2. unclear personal ownership versus team/company work;
3. unsupported or ambiguous metric, scope, timeframe, or baseline;
4. insufficient technical or operational depth;
5. unclear decision rationale, trade-off, or alternative considered;
6. unclear failure handling, learning, or transfer to the target role.

Do not combine several priorities into one compound question.

### Decision rules
- If the answer is empty, evasive, or generic, ask for one concrete example with role, action, and outcome.
- If ownership is unclear, ask exactly what the candidate personally decided, implemented, or delivered.
- If a metric is given without baseline, timeframe, attribution, or measurement method, ask for the most important missing dimension.
- If technical depth is shallow, ask about one key design choice, constraint, failure mode, or validation method.
- If the answer contradicts evidence or history, neutrally quote or reference the conflicting claims and ask the candidate to reconcile them.
- If the current answer sufficiently resolves the original question, deepen the same criterion with one transfer, edge-case, or trade-off question rather than repeating it.
- Do not ask a question already answered or semantically equivalent to a question in the history.
- Do not reveal the expected answer or score the candidate in the question.

### Evidence integrity
- When the output schema contains evidence references, use only allowed evidence from the input.
- Copy evidence objects exactly, or return only exact allowed chunk IDs when the recommended ID-only schema is used.
- Never rewrite, summarize, or repair evidence text.

### Question style
- Generate exactly one next question.
- Use one sentence when possible.
- Ask for one main thing; avoid stacked subquestions.
- Be neutral, professional, and specific enough to produce a verifiable answer.

### Silent self-check before returning
- The follow-up addresses the highest-priority unresolved issue.
- It does not repeat interview history.
- It contains no unsupported fact or leading answer.
- Any evidence reference is valid and unchanged.
- The output matches the injected JSON Schema exactly.

### Job and criterion context
<job_context_json>
{{job_context_json}}
</job_context_json>

### Candidate report evidence
<candidate_evidence_json>
{{candidate_evidence_json}}
</candidate_evidence_json>

### Current question
<current_question_json>
{{current_question_json}}
</current_question_json>

### Latest candidate answer
<latest_answer>
{{latest_answer}}
</latest_answer>

### Interview history
<interview_history_json>
{{interview_history_json}}
</interview_history_json>

---

## Schema and Validation

## Schema 与代码校验建议

### 1. JobProfile

#### Schema 约束

- `criteria`: `min_length=3, max_length=6`
- `criterion_id`: 非空、唯一，建议匹配 `^criterion_[0-9]{2}$`
- `name`: 规范化后唯一
- `weight`: 0–100，合计 100
- `evidence_query`: 非空，限制最大长度

#### 业务校验

- bonus 总权重默认不超过 20；若超过，记录告警而非直接失败，以免错误拒绝特殊 JD。
- 使用文本相似度检查 criteria 重复；阈值命中时进入人工审阅或一次受控 repair。
- 在 parse_jd 前检测多职位标题，不依赖 LLM 自行选择。

### 2. ResumeProfile

#### 内部可校验规则

- 每个工作、项目、教育、achievement 至少一个 `source_ref`。
- `chunk_id` 非空。
- 重复 source reference 去重。

#### 依赖输入上下文的外部校验

Pydantic 模型本身不知道输入 chunks，建议在 service 层执行：

```python
def validate_source_refs(profile: ResumeProfile, chunks: list[Chunk]) -> None:
    chunk_map = {chunk.chunk_id: chunk for chunk in chunks}
    for ref in iter_all_source_refs(profile):
        source = chunk_map.get(ref.chunk_id)
        if source is None:
            raise ValueError(f"unknown chunk_id: {ref.chunk_id}")
        if ref.page_number != source.page_number:
            raise ValueError(f"page mismatch: {ref.chunk_id}")
        if ref.section != source.section:
            raise ValueError(f"section mismatch: {ref.chunk_id}")
        if canonicalize_ws(ref.text) not in canonicalize_ws(source.text):
            raise ValueError(f"non-verbatim source text: {ref.chunk_id}")
```

`canonicalize_ws()` 只能统一空白和 Unicode 兼容字符，不应修正字母、数字、标点含义或 OCR。

### 3. MatchEvaluation：推荐 Schema

将完整 evidence 对象改为 ID：

```python
class CriterionEvaluation(BaseModel):
    criterion_id: str
    name: str
    weight: int = Field(ge=0, le=100)
    score: int = Field(ge=0, le=5)
    status: MatchStatus
    reason: str
    evidence_chunk_ids: list[str] = Field(default_factory=list, max_length=5)
    missing_evidence: list[str] = Field(default_factory=list, max_length=6)
    risk: str = ""

    @model_validator(mode="after")
    def validate_internal_consistency(self):
        expected = {
            5: "strong_match",
            4: "match",
            3: "partial_match",
            2: "partial_match",
            1: "partial_match",
        }
        if self.score == 0:
            if self.status not in {"no_evidence", "conflict"}:
                raise ValueError("score=0 requires no_evidence or conflict")
            if self.evidence_chunk_ids:
                raise ValueError("score=0 requires empty evidence")
        else:
            if self.status != expected[self.score]:
                raise ValueError("score/status mismatch")
            if not self.evidence_chunk_ids:
                raise ValueError("positive score requires evidence")
        return self
```

#### 输入集合校验

模型返回后，Python 必须检查：

```python
expected_ids = [criterion.criterion_id for criterion in job.criteria]
actual_ids = [item.criterion_id for item in result.criteria]
if actual_ids != expected_ids:
    raise ValueError("criterion set/order mismatch")

for item in result.criteria:
    allowed = allowed_chunk_ids_by_criterion[item.criterion_id]
    if not set(item.evidence_chunk_ids) <= allowed:
        raise ValueError("evidence outside allowed candidate set")
```

同时校验 `name` 和 `weight` 与输入完全一致。验证通过后再从 `chunk_id` 回填不可变 evidence。

### 4. QuestionSet：推荐 Schema

#### Evidence 改为 ID

```python
class InterviewQuestion(BaseModel):
    question: str
    question_type: QuestionType
    difficulty: Difficulty
    assessment_points: list[str] = Field(min_length=2, max_length=4)
    related_criteria: list[str] = Field(min_length=1, max_length=2)
    evidence_chunk_ids: list[str] = Field(default_factory=list, max_length=2)
    reference_answer_direction: str
    scoring_rubric: list[str] = Field(min_length=3, max_length=5)
    suggested_followups: list[str] = Field(min_length=1, max_length=1)
```

#### 集合与分布校验

- 正式问题恰好 10 道。
- 类型计数固定为 3/2/2/2/1。
- 歧义追问 3–5 道。
- `related_criteria` 是 JobProfile criterion ID 子集。
- 非 gap 类型至少一个 evidence ID。
- gap 类型仅可关联低分、no_evidence、conflict 或 missing_evidence 非空的 criterion。
- evidence ID 必须来自 candidate report；不要允许直接从完整 ResumeProfile 越权引用。
- 同一 chunk 作为主要证据最多使用两次。

#### 去重校验

Pydantic 不适合语义去重。建议在 service 层：

1. 规范化问题文本，先做完全重复和高 n-gram 重叠检查；
2. 使用现有 embedding service 计算问题相似度；
3. 任意一对相似度超过阈值（例如 0.88）时，触发局部 repair，只重写冲突问题；
4. 不要整套重生成，以免延迟和漂移扩大。

### 5. Follow-up Schema

建议输出最小结构：

```python
class FollowupQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=300)
    reason_code: Literal[
        "contradiction",
        "ownership",
        "metric_scope",
        "technical_depth",
        "decision_tradeoff",
        "failure_learning",
        "deeper_validation",
    ]
    related_criterion_id: str
    evidence_chunk_ids: list[str] = Field(default_factory=list, max_length=2)
```

由代码检查问题不与历史重复、criterion 有效、evidence ID 合法。

### 6. OCR/Text Quality Gate

在 `parse_resume` 前计算：

- 可打印字符比例；
- 中文简历的汉字比例；
- Unicode replacement character、连续乱码符号比例；
- 极长无空格 token；
- OCR 平均置信度（如引擎可提供）；
- 关键字段区域是否为空。

低于阈值时：

1. 尝试另一 OCR 路径；
2. 仍失败则标记 `TEXT_QUALITY_TOO_LOW`；
3. 不进入 LLM 解析和向量库入库；
4. 前端展示重新上传/重新 OCR 的明确状态。

### 7. RAG 校验与重排

- 为每个 criterion 设置最低相似度阈值，但不要把统一阈值视为最终证据判断。
- 使用 cross-encoder/reranker 或轻量 evidence classifier 对 top-k 二次过滤。
- 保留一个“没有足够证据”的合法空集合路径。
- 记录检索前 query、top-k、过滤后集合、最终被模型选择的 chunk ID，便于定位问题归因。

### 8. 日志改造

每次调用记录：

- prompt name/version/hash；
- schema name/version/hash；
- model、temperature；
- input/output token；
- latency；
- attempt；
- validation error 的结构化摘要；
- criterion/evidence/question 质量校验结果；
- 是否发生 repair；
- OCR gate、RAG filter 和 Pydantic failure 分开计数。

---

## Question Generation Split

## generate_questions 拆分设计

### 1. 为什么必须拆分

当前单次输出包括 10 道正式问题、3–5 道歧义追问，以及每道题的 assessment points、evidence、answer direction、rubric 和 follow-ups。输出规模是主要延迟来源，单纯缩短 Prompt 无法从根本上降低约 98 秒的生成耗时。

### 2. 推荐调用拓扑

```text
candidate report + job profile
        |
        v
A. plan_question_blueprint（小输出）
        |
        v
Python：检查类型分布、criterion 覆盖、evidence 合法性、重复目标
        |
        +------------------+
        |                  |
        v                  v
B1. generate_batch_1   B2. generate_batch_2
    5 formal              5 formal
        |                  |
        +--------+---------+
                 v
C. generate_ambiguity_followups（3-5）
                 |
                 v
Python 合并、证据回填、语义去重、局部 repair
```

B1/B2 可以并行调用，但必须使用同一个已经校验的 blueprint，避免两批覆盖重复目标。

### 3. QuestionBlueprint Schema

```python
class QuestionBlueprintItem(BaseModel):
    question_id: str
    question_type: QuestionType
    primary_criterion_id: str
    secondary_criterion_ids: list[str] = Field(default_factory=list, max_length=1)
    evidence_chunk_ids: list[str] = Field(default_factory=list, max_length=2)
    objective: str
    difficulty: Difficulty

class QuestionBlueprint(BaseModel):
    formal_questions: list[QuestionBlueprintItem] = Field(min_length=10, max_length=10)
    ambiguity_sources: list[AmbiguitySource] = Field(min_length=3, max_length=5)
```

Blueprint 不生成完整问题、答案方向或 rubric，因此输出很小。

### 4. Blueprint 校验

- 类型分布恰好 3/2/2/2/1；
- 高权重 must criterion 被覆盖；
- 至少覆盖四个 criterion（若存在）；
- question objective 不重复；
- 同一 evidence chunk 作为主证据不超过两次；
- gap 题只能指向低分/缺证据 criterion；
- ambiguity source 与正式 gap 题不重复；
- evidence ID 全部属于 candidate report。

### 5. 批量生成策略

按 blueprint 固定生成，不允许模型重新选 criterion 或 evidence。每批输入只包含：

- 5 个 blueprint item；
- 对应 criterion 的最小必要描述；
- 对应 evidence 原文或 ID；
- 全局禁止重复摘要。

这样可以显著减少上下文与响应体积，并允许只重试失败批次。

### 6. 局部 repair

发现以下问题时，仅重写具体 question ID：

- 文本与另一题相似；
- evidence ID 非法；
- 题型不符；
- rubric 不可观察；
- 问题泄露参考答案；
- compound question 过长。

repair 输入应包含原问题、失败规则和目标 blueprint，不应重新发送全部 candidate report。

### 7. 预期收益与副作用

#### 收益

- 输出 token 显著下降；
- 两批可并行；
- 单批失败不会整套重试；
- 覆盖率、去重和证据合法性可在 LLM 前确定；
- 更容易定位问题来自规划还是表述。

#### 副作用

- 增加一次轻量规划调用和编排代码；
- 并行批次可能风格略有差异；
- blueprint 设计错误会系统性影响后续题目。

通过固定 tone、共享 blueprint 和最终局部质量检查可控制这些风险。

---

## Evaluation Plan

## Prompt 自动评测计划

### 1. 评测原则

- 固定模型、temperature、JSON Schema、输入数据和超时设置。
- 同一版本至少重复运行 3 次；`parse_jd`、`parse_resume`、`evaluate_match` 可运行 5 次，较昂贵的 questions 任务至少 3 次。
- 区分首次响应、validation retry、quality repair，不把修复后成功计为首次成功。
- 同时保存原始响应和经过 Python hydration 后的业务对象。

### 2. 固定测试集

至少覆盖：

1. 单一清晰中文 JD；
2. 多职位中文 JD；
3. 极短 JD；
4. 只有软技能和职责、无技术栈 JD；
5. 含明确 must/bonus 的 JD；
6. 中文简历含 `AI/Al`、`0/O` 等 OCR 易错字符；
7. chunks 重叠且事实重复；
8. 明确满足全部 must criteria；
9. RAG 对缺失 criterion 返回多个语义相近但不支持的 chunks；
10. 公司账号粉丝量与个人粉丝量区分；
11. 简历中存在明确日期或职责冲突；
12. 强项很多、缺口很少的 question 输入；
13. 几乎没有直接证据的 question 输入；
14. 当前回答空泛、ownership 不清的 follow-up；
15. 当前回答与历史或证据冲突的 follow-up；
16. 当前回答已经充分，需要进一步深挖的 follow-up。

### 3. 核心指标

#### 所有任务

- 首次 JSON/Pydantic 通过率：目标 >= 98%。
- 平均 retry 次数和 retry 率：目标 retry 率 <= 2%。
- P50/P95 latency。
- 输入 token、输出 token、总 token。
- 空字段策略通过率。
- 输出语言保持率：目标 100%。

#### parse_jd

- criterion 数量合法率：100%。
- criterion ID 唯一和顺序合法率：100%。
- 权重和正确率：100%。
- 多职位错误合并率：0%。
- criterion 语义重复率。
- evidence_query 检索 Recall@k / nDCG@k：使用人工标注相关 resume chunks 测量。

#### parse_resume

- source chunk ID 有效率：100%。
- source text 原文一致率：100%。
- 重要事实引用覆盖率：目标 >= 98%。
- unsupported fact rate：0%。
- OCR 自动修正率：0%；疑似 OCR 问题应进入 ambiguity 或上游 gate。
- 重复事实率：目标 <= 2%。

#### evaluate_match

- criterion 完整覆盖与顺序正确率：100%。
- evidence ID 忠实率：100%。
- evidence mutation rate：0%。
- 无支持证据时正分率：0%。
- score/status 一致率：100%。
- conflict precision：目标 >= 95%，避免把“缺失”误判为“冲突”。
- 与人工分项评分的加权 MAE / quadratic weighted kappa。
- total_score 字段违规输出率：0%。

#### generate_questions

- 类型分布通过率：100%。
- formal question 数量与 ambiguity 数量通过率：100%。
- evidence 合法率：100%。
- gap target 有效率：目标 >= 98%。
- priority criterion 覆盖率：所有 must 和高权重 important 优先覆盖。
- 语义重复率：任意问题对 embedding similarity 超阈值的比例 <= 5%。
- 同一主 evidence 过度使用率：0%。
- compound question 率、leading question 率、answer leakage 率。
- 输出 token 相对当前基线降低 >= 35%。
- 拆分后端到端 P95 相对当前基线降低 >= 30%，并记录并行/串行两种模式。

#### generate_followup

- 单问题输出率：100%。
- 与历史重复率：0%。
- highest-priority gap 选择准确率：人工标注集目标 >= 90%。
- unsupported premise rate：0%。
- compound question rate：目标 <= 5%。

### 4. A/B 验收

对旧 Prompt 和新 Prompt 使用同一输入运行：

- 若首次 Schema 通过率、证据忠实率或无证据保守性下降，则不发布；
- 质量相同但 token/latency 更低，可发布；
- 分项评分整体降低并不等于质量下降，需检查是否是旧 Prompt 对无证据项目过度给分；
- 新版本上线后应同时监控评分分布漂移和 recommendation 阈值是否需要重新校准。

### 5. 版本与回归

建议记录：

```text
prompt_name
prompt_version
prompt_sha256
schema_version
model
temperature
eval_case_id
first_pass_valid
retry_count
quality_failures
input_tokens
output_tokens
latency_ms
```

任何 Prompt、Schema、chunking、embedding、reranker 或模型版本变化都应触发对应回归集。

---

## Codex Implementation Task

## 交给 Codex 的实施任务

请基于本目录完成 ResuMate Agent 的 LLM Prompt 与结构化输出可靠性改造，不改变“Python 计算 total_score 和 recommendation”的业务边界。

### 目标

1. 用 `backend_prompts/` 中的五份 Prompt 替换当前业务 Prompt，并将占位符映射到当前 `AgentHarness` 实际变量。
2. 保留 system 层完整 JSON Schema 注入和 `strict=true`。
3. 将匹配评估和面试题 evidence 改为 `evidence_chunk_ids`，由 Python 从本次允许集合回填原始 evidence。
4. 增加输入/输出集合一致性、评分状态一致性、source-ref 原文一致性和问题分布校验。
5. 将问题生成重构为 blueprint + 两批正式题 + 歧义追问，并支持局部 repair。
6. 增加 OCR/text quality gate、多职位 JD 检测和结构化 validation error 日志。
7. 增加固定自动评测集与 CI 回归指标。

### 必须遵守

- 不允许 LLM 计算 `total_score` 或 recommendation。
- 不允许 LLM 创建、修正、拼接或改写 evidence。
- 不允许匹配评估使用对应 criterion 候选 evidence 集合之外的 chunk。
- `score=0` 时 evidence 必须为空；正分必须有 evidence。
- 输出 criterion 必须与输入一一对应、顺序一致。
- 多职位 JD 不得合并为一个人工组合岗位。
- OCR 低质量文本应在 LLM 前拒绝或重新 OCR。
- 不要通过放松 Pydantic 校验来提高“成功率”。

### 建议修改位置

- `backend/prompts/*.md`
- `backend/schemas/workflow.py`
- `backend/agents/harness.py`
- `backend/graph/candidate_workflow.py`
- `backend/services/analysis.py`
- `backend/services/documents.py`
- `backend/rag/milvus.py`
- question quality/repair 相关模块
- 测试目录和日志配置

### 测试要求

- Prompt 单元测试：模板变量完整、无未替换占位符。
- Schema 测试：score/status/evidence 组合、criteria 数量、question 类型分布。
- Evidence 安全测试：未知 ID、跨 criterion ID、被篡改原文、score=0 带 evidence 均失败。
- Resume 引用测试：未知 chunk、非原文子串、section/page 不一致均失败。
- 多职位 JD 测试：检测后不进入单 profile 合并解析。
- OCR gate 测试：乱码样本被阻断。
- Question split 测试：两批合并后正好 10 道且无重复 question ID。
- 回归测试：Python 总分计算结果不受 LLM 输出字段影响。

完成后输出：

1. 修改文件清单；
2. Schema 迁移说明；
3. Prompt 变量映射；
4. 测试结果；
5. 旧数据兼容策略；
6. 尚未解决的 RAG/OCR 风险。
