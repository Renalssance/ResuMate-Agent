# ResuMate Agent：LLM Prompt 优化证据包

> 用途：将本文档直接交给 ChatGPT 或其他 Prompt 优化专家，使其在理解真实架构、真实数据流、真实模型输出与失败案例的基础上，改进项目 Prompt。  
> 证据时间范围：`log/llm.log` 中截至 2026-06-14 10:52:40 的调用记录。  
> 当前真实模型：`mimo-v2.5-pro`，通过 OpenAI-compatible Chat Completions API 调用。  
> 隐私说明：本文只保留诊断所需的真实案例结构，手机号、邮箱、公司名等个人信息已省略或概括。

## 1. 希望 ChatGPT 完成的任务

请基于本文档，为以下五类任务分别设计可投入生产的 Prompt：

1. `parse_jd`：将 JD 解析为结构化 `JobProfile`。
2. `parse_resume`：将简历 chunks 解析为带来源引用的 `ResumeProfile`。
3. `evaluate_match`：只根据检索证据，逐项评估候选人与 JD 标准的匹配度。
4. `generate_questions`：根据候选人报告生成正式面试题与歧义追问。
5. `generate_followup`：根据当前问题、回答和上下文生成下一条追问。

优化时必须遵守以下边界：

- 不把所有问题都归因给 Prompt。OCR 乱码、chunk 切分、RAG 召回、Schema 设计和代码校验问题应单独指出。
- 不建议让模型计算最终总分。最终分数由 Python 根据权重与 0-5 分项评分计算。
- 不允许模型创造、改写或补全不存在的证据。
- 输出必须满足现有 Pydantic Schema，或明确提出需要配套修改的 Schema。
- 对每项建议说明：解决什么真实问题、具体改法、预期收益、潜在副作用、如何验收。

建议输出物：

- 五份改进后的 Prompt。
- 每份 Prompt 的设计说明。
- 建议增加的 Pydantic 校验规则。
- 建议增加的自动评测用例与指标。
- Prompt-only 改动与必须修改代码/Schema 的改动清单。

## 2. 当前系统架构

### 2.1 核心技术栈

- API：FastAPI
- LLM 编排：`AgentHarness` + LangGraph
- 结构化输出：Pydantic v2 + JSON Schema
- 业务持久化：PostgreSQL / SQLAlchemy
- 文档存储：本地持久化文件
- 文本提取：PyMuPDF、DOCX parser、必要时 OCR
- RAG：本地 embedding service + Milvus
- 前端：Vue 3 + Pinia
- 日志：`log/backend.log` 与 `log/llm.log`

### 2.2 LLM 统一入口

新的生产路径统一经过 `backend/agents/harness.py::AgentHarness.run_schema()`：

1. 从 `backend/prompts/<prompt_name>.md` 加载业务 Prompt。
2. 将变量替换进 Prompt。
3. 从 Pydantic 模型生成 JSON Schema。
4. 在 system message 中注入完整 JSON Schema，并要求严格 JSON。
5. 调用 OpenAI-compatible API：
   - `temperature=0.1`
   - `response_format.type=json_schema`
   - `strict=true`
6. 使用 `schema.model_validate_json(content)` 做本地验证。
7. 验证失败时，将验证错误附加到对话，最多重试一次。
8. 在 `llm.log` 中记录完整 Prompt、原始响应、错误、模型、Schema、attempt 与耗时。

system message 当前固定为：

```text
Return strict JSON only. No markdown, no commentary.
The response must match this JSON Schema exactly:
<完整 JSON Schema>
```

### 2.3 当前仍可从日志观察到的旧路径

日志前半部分仍包含旧式自由文本 Prompt，例如：

- `service.resume_upload.parse_resume`
- `route.jd.create.parse_jd`

旧路径通过示例 JSON 描述输出格式，但没有完整 JSON Schema 与严格本地校验。它的特点是：

- 更容易输出可解析但字段不完整的 JSON。
- JD 解析单次耗时约 58-77 秒。
- 简历解析曾接收到严重乱码的 OCR 文本。

这部分应作为“迁移前基线”，不应继续作为新 Prompt 的设计基础。

### 2.4 LangGraph 候选人分析流程

当前匹配主流程为：

```text
持久化 JD / 简历
  -> 提取文本或 OCR
  -> chunk_pages
  -> parse_jd / parse_resume
  -> PostgreSQL 保存结构化 profile
  -> Milvus 保存 chunks 与 profile
  -> load_structured_profiles
  -> 按每个 JD criterion 的 evidence_query 检索简历证据
  -> evaluate_match
  -> Python calculate_total_score
  -> Python recommendation_for_score
  -> PostgreSQL + Milvus 持久化报告
  -> 用户请求时 generate_questions
```

注意：当前 `CandidateAnalysisGraph` 本身只负责加载 profile、检索证据、匹配评估、计算分数和持久化报告。面试题由独立 API 请求后生成，不在初始分析图内。

### 2.5 数据责任边界

| 数据 | 责任方 | 说明 |
|---|---|---|
| 原始文件、raw text、structured profile | PostgreSQL + 本地文件 | PostgreSQL 是业务事实源 |
| 文档 chunks、profile artifact、报告 artifact | Milvus | 用于检索，不是报告事实源 |
| JD criteria 与 evidence_query | LLM `parse_jd` | 决定后续 RAG 查询质量 |
| 每项匹配分数与理由 | LLM `evaluate_match` | 必须只基于提供的证据 |
| total_score | Python | `sum(weight * score / 5)` |
| recommendation | Python | 根据总分阈值映射 |
| 面试问题 | LLM `generate_questions` | 当前输出体积最大、耗时最长 |

## 3. 当前结构化 Schema

### 3.1 JobProfile

关键字段：

```text
job_title
summary
responsibilities[]
criteria[]:
  criterion_id
  name
  description
  importance: must | important | bonus
  weight: 0..100
  evidence_query
interview_focus[]
```

代码校验：

- `criteria` 至少 1 项。
- 所有 criterion 权重之和必须等于 100。

Prompt 额外要求：

- 生成 3-6 个 criteria。
- 每项必须提供可用于检索简历证据的 `evidence_query`。

当前缺口：Schema 没有约束 3-6 项，也没有约束 `criterion_id` 唯一性、`evidence_query` 的检索质量或必备项/加分项的权重策略。

### 3.2 ResumeProfile

关键字段：

```text
candidate_name
contact{}
education[]
work_experience[]
projects[]
skills[]
achievements[]
ambiguities[]
source_refs[]
```

教育、工作、项目均可携带 `source_refs`：

```text
page_number
section
text
chunk_id
```

Prompt 要求“重要事实必须引用 source_refs”，但 Schema 允许所有 `source_refs` 为空。当前没有代码检查引用是否来自输入 chunk、引用文本是否为原文子串。

### 3.3 MatchEvaluation

每个 criterion 的输出：

```text
criterion_id
name
weight
score: 0..5
status: strong_match | match | partial_match | no_evidence | conflict
reason
evidence[]
missing_evidence[]
risk
```

代码校验：

- `score > 0` 时，至少需要一个 evidence。

当前缺口：

- 不检查输出是否覆盖全部 criterion。
- 不检查是否返回重复或额外 criterion。代码后续会对齐并丢弃额外项。
- 不检查 `score` 与 `status` 是否一致。
- 不检查 evidence 是否来自输入候选集合。
- 不检查 evidence 的 `text`、`section`、`score` 是否被模型改写。
- 不检查 `score=0` 时 evidence 必须为空。

### 3.4 QuestionSet

正式问题固定为 10 道，类型分布固定：

```text
resume_experience: 3
jd_core_capability: 2
scenario_design: 2
gap_validation: 2
behavior_review: 1
```

另需 3-5 道 `ambiguity_followups`。

每道问题包含：

```text
question
question_type
difficulty
assessment_points[]
related_criteria[]
evidence[]
reference_answer_direction
scoring_rubric[]
suggested_followups[]
```

当前缺口：

- Prompt 说每道正式问题都必须引用报告中的证据，但 Schema 没要求 `evidence` 非空。
- 不检查 evidence 是否来自 candidate report。
- 不检查问题之间是否重复。
- 不检查 gap 问题是否真的对应缺失证据。
- 13-15 道完整问题一次生成，响应非常大，延迟约 97 秒。

## 4. 当前 Prompt 设计

### 4.1 parse_jd

当前业务 Prompt：

```text
You are a recruiting analyst. Extract a structured JobProfile from the JD text.

Rules:
- Return only JSON matching the provided schema.
- Build 3 to 6 criteria.
- Criterion weights must sum to exactly 100.
- Each criterion must include a practical evidence_query that can retrieve resume evidence.
- Do not add features or data outside the JD.
```

优点：

- 角色与任务清晰。
- 将权重、criteria 数量、检索查询作为显式要求。
- 配合 JSON Schema 后能稳定生成完整结构。

不足：

- 没有说明多职位 JD 应如何处理。
- 没有给 `importance`、权重分配、criterion 粒度的决策规则。
- 没有要求 criterion 互斥、避免重复。
- `evidence_query` 容易写成冗长自然语言，而不是检索友好的概念组合。
- 没有要求保持输入语言，真实失败案例中曾将中文多职位 JD 输出成英文并包裹在错误的 `job_profile` 顶层。

### 4.2 parse_resume

当前业务 Prompt：

```text
You are a resume parser. Extract a structured ResumeProfile from the resume text and chunk references.

Rules:
- Important facts must cite source_refs with page_number, section, exact text snippet, and chunk_id.
- If a fact is unclear, put it in ambiguities.
- Do not infer facts that are not present in the resume.
```

优点：

- 强调可追溯引用和不推断。
- 输入为带 chunk_id 的结构化 chunks，而不是纯文本。
- 能提取丰富的工作、技能和成果信息。

不足：

- “Important facts” 未定义，模型不知道哪些字段必须引用。
- 没有要求 `source_refs.text` 必须逐字复制输入 chunk 子串。
- 没有处理 OCR 易错字符的规则，例如 `AI` 被识别为 `Al`、`0` 被识别为 `O`。
- 没有处理 chunk 重叠导致的重复事实。
- 没有限制 contact 中的敏感信息是否应保留。

### 4.3 evaluate_match

当前业务 Prompt：

```text
You are a hiring match evaluator.

Rules:
- Evaluate only from the provided evidence chunks.
- For any score greater than 0, cite at least one evidence chunk.
- Score meanings: 5 direct and sufficient evidence; 4 clear practical evidence;
  3 partial evidence; 2 keyword or indirect evidence; 1 weak relation;
  0 no evidence or conflict.
- Do not calculate total_score.
```

优点：

- 明确限制只能使用检索证据。
- 评分尺度相对清晰。
- 总分交由 Python 计算，避免模型算术与权重漂移。
- 真实输出能识别“公司账号粉丝 50W”不等于“个人粉丝 1W+”这一重要语义差异。

不足：

- 没有要求“每个输入 criterion 恰好返回一次”。
- 没有明确 `status` 与 `score` 的映射。
- 没有要求 evidence 对象原样复制，只允许通过 `chunk_id` 引用。
- 模型会缩写或改写 evidence text，破坏证据不可变性。
- RAG 即使对无关标准返回相似度约 0.45-0.54 的 chunks，模型仍需自己判断“无证据”；Prompt 没明确“召回不等于匹配”。
- 一次真实调用因验证失败触发二次生成，总耗时达到 83.2 秒。

### 4.4 generate_questions

当前业务 Prompt：

```text
You are an interview designer.

Rules:
- Generate exactly 10 formal_questions with a fixed type distribution.
- Generate 3 to 5 ambiguity_followups.
- Every formal question must cite resume evidence chunks that appear in the candidate report.
- Questions must verify the candidate against the JD and the retrieved evidence.
```

优点：

- 类型分布清楚。
- 真实输出问题质量整体较高，能结合具体指标、缺口与职责边界设计追问。
- 能生成参考答案方向、评分 rubric 和 suggested followups。

不足：

- 单次要求生成 13-15 个复杂对象，输出极长，真实平均耗时约 97.6 秒。
- Prompt 没要求证据原样引用，模型会改写 `section` 和 `text`。
- 真实输出中出现 evidence `score: 0`，且引用文本并非 candidate report 中原始 evidence 对象。
- 题目容易重复覆盖同一强项，缺少去重与覆盖率规则。
- 没有明确“正式题验证能力，歧义题验证真实性，gap 题验证缺口”的不同目标。
- `reference_answer_direction` 可能暗示候选人迎合标准答案，不一定适合真实面试。

### 4.5 generate_followup

当前业务 Prompt 已要求结合当前问题、回答、JD、简历、问题上下文与历史，并识别：

- ownership 不清
- metrics 缺失
- 技术深度不足
- 矛盾
- gaps

当前 `llm.log` 中没有该任务的真实调用记录，因此不能用本日志判断真实效果、耗时或失败模式。优化时应将其视为待建立基线的任务。

## 5. 真实调用统计

以下统计直接来自当前 `llm.log`。测试用 `compatible-model` 的 0ms 模拟响应包含在日志中，但不应视为真实模型性能。

| task | 真实模型响应数 | 平均耗时 | 最大耗时 | 观察 |
|---|---:|---:|---:|---|
| `document.parse_jd` | 4 个真实成功/失败响应，另有测试响应 | 约 15-18 秒（Schema 注入后的成功调用） | 18.3 秒 | 早期未注入 Schema 时出现 13 个与 3 个校验错误 |
| `document.parse_resume` | 2 | 33.5 秒 | 35.1 秒 | 输出体积较大，包含大量 source refs |
| `evaluate_match` | 4 | 45.9 秒 | 83.2 秒 | 一次触发二次重试 |
| `generate_questions` | 3 | 97.6 秒 | 98.3 秒 | 当前最慢，输出体积最大 |
| `route.jd.create.parse_jd` 旧路径 | 4 | 66.2 秒 | 76.5 秒 | 无新 Schema 约束，明显更慢 |
| `service.resume_upload.parse_resume` 旧路径 | 1 | 40.1 秒 | 40.1 秒 | 输入 OCR 文本严重乱码 |

重要结论：

1. 完整 JSON Schema 注入显著提高了字段完整性；注入后的成功样本也表现出更低延迟，但当前样本不足以证明二者存在直接因果关系。
2. Prompt 越复杂、输出对象越大，耗时越高。
3. 重试会放大延迟；应通过更清晰的约束和更强的本地验证减少无效重试。
4. `generate_questions` 的主要性能问题不只是 Prompt 文案，而是“一次生成过多复杂对象”的任务设计。

## 6. 真实案例分析

### 案例 A：未完整约束的 JD 输出缺少 13 个必填字段

输入是“新媒体运营（AI 方向）”JD。模型输出了职位名和四个 criteria，但缺少：

- `summary`
- 每个 criterion 的 `criterion_id`
- 每个 criterion 的 `description`
- 每个 criterion 的 `importance`

Pydantic 最终报告 13 个 validation errors。

这说明仅写“matching the provided schema”不够；模型必须实际看到完整 Schema，或 Prompt 必须明确列出必填字段。后续 `AgentHarness` 注入完整 JSON Schema 后，同类 JD 成功返回完整结构。

### 案例 B：多职位 JD 被错误合并并改变语言

输入同时包含：

- 职位一：新媒体运营（AI 方向）
- 职位二：AI 业务探索

模型曾输出：

```json
{
  "job_profile": {
    "title": "AI-Savvy New Media Operations & Business Explorer",
    ...
  }
}
```

问题：

- 顶层结构不符合 `JobProfile`。
- 将两个岗位未经规则地合并为一个岗位。
- 输入为中文，输出变成英文。

Prompt 必须明确多职位输入策略。例如：拒绝并写入明确错误、选择第一个职位、或生成一个明确标注为组合岗位的 profile。当前 Schema 只能容纳一个 JobProfile，因此最稳妥策略是要求调用方先拆分，或 Prompt 明确选择主职位并在 `summary` 说明。

### 案例 C：Schema 注入后的 JD 输出显著改善

同类中文 JD 在完整 JSON Schema 注入后，输出包含：

- 中文 `job_title` 与 `summary`
- 完整职责
- 5 个带 ID、描述、importance、weight 和 evidence_query 的 criteria
- 权重合计 100

说明当前“系统层 Schema + 简洁业务规则”的方向正确。后续重点应从“能否返回合法 JSON”转向“criterion 质量、检索质量和业务一致性”。

### 案例 D：真实 RAG 能召回相关证据，但也会召回无关证据

针对新媒体运营岗位，模型从跨境电商候选人简历中正确识别：

- TikTok Shop 从 0 到 1 账号搭建
- 半年粉丝 50W、单月 GMV 150 万美元
- Midjourney / Runway / HeyGen 使用经验
- 数据分析、爆款、ROAS 等量化结果

但对于“B2B/供应链经验”和“个人影响力”这类缺口标准，Milvus 仍返回相似度约 0.45-0.54 的 chunks。模型最终能判断为 `no_evidence`，这是好的，但也说明：

- RAG top-k 不代表证据成立。
- Prompt 必须明确“检索相似度不是匹配分数”。
- 应允许并鼓励模型在所有召回结果都不支持标准时返回 0 分。
- 更理想的代码设计是在 LLM 前加入阈值、rerank 或 evidence classifier。

### 案例 E：匹配输出会改写证据

输入 evidence 是完整 chunk；模型返回时经常只截取相关段落，并省略原始 `score` 或改变 text。

例如输入 chunk 包含长段工作经历，输出 evidence 只保留：

```text
TikTok Shop矩阵操盘：负责北美区TikTokShop账号从O到1的搭建...
```

语义上更易读，但系统层面存在风险：

- 返回的 evidence 已不是 Milvus 中不可变的原始对象。
- 后续无法严格验证“证据是否真实来自输入”。
- 模型可能在截取时修正 OCR、拼接文本或添加不存在内容。

最佳方案不是继续强化“请勿改写”一句话，而是修改输出 Schema：LLM 只返回 `evidence_chunk_ids`，由 Python 根据 ID 回填原始 evidence。

### 案例 F：一次匹配评估触发重试

真实调用中，`evaluate_match` 第一次响应后触发 Pydantic validation retry，第二次响应成功，总耗时从约 43 秒放大到 83.2 秒。

日志没有在 `llm.log` 中直接附带该次 validation error 文本，但 `backend.log` 明确记录：

```text
Structured LLM response failed validation; retrying |
task=evaluate_match schema=MatchEvaluation
```

改进方向：

- Prompt 明确每个 criterion 恰好输出一次。
- 明确所有必填数组，即使为空也返回 `[]`。
- 明确 `score/status/evidence` 一致性。
- 在第一次调用前提供更紧凑的输出契约，而不是依赖失败后再修复。
- 日志应为 retry 记录 validation error 摘要，方便 Prompt 评测。

### 案例 G：问题生成质量高，但证据完整性不足

真实问题能基于具体事实生成高质量追问，例如：

- 要求候选人说明 TikTok Shop 从 0 到 1 的关键决策与挑战。
- 要求量化 Midjourney / Runway 工作流的效率提升。
- 区分公司账号粉丝与个人影响力。
- 追问 LLM 客服 Agent 中候选人到底负责技术架构、Prompt 工程还是流程设计。

但真实输出也出现：

- evidence 的 `section` 被统一改写成 `【工作经历】`。
- evidence 的 text 被模型重新摘录。
- 部分 evidence 的 `score` 为 0。
- 某些问题使用了不在匹配评估 evidence 中的简历事实，可能来自 `resume_profile`，但 Prompt 声称应引用 candidate report 中的 evidence。

这说明问题质量与证据忠实度是两个独立指标。不能因问题“听起来专业”就认为输出完全正确。

### 案例 H：上游 OCR 乱码不是 Prompt 能解决的问题

旧路径中，一份中文简历进入 Prompt 前已经出现大量乱码，例如中文变成不可读字符。模型仍尝试输出结构化结果，但任何 Prompt 都无法可靠恢复已经丢失的原文。

必须在 LLM 前进行：

- 编码检查。
- OCR 可读性检查。
- 中文字符比例、乱码字符比例检测。
- 低质量文本拒绝或重新 OCR。

Prompt 可以要求“遇到不可读文本写入 ambiguities”，但不能代替上游质量门禁。

## 7. 问题归因：哪些应改 Prompt，哪些不应

| 问题 | Prompt 可改善 | 还需要 Schema/代码/数据流 |
|---|---|---|
| 缺少必填字段 | 是 | JSON Schema + Pydantic 校验已证明有效 |
| 多职位 JD 如何处理 | 是 | 最好在上传/解析前拆分或拒绝 |
| criterion 重复、粒度不一致 | 是 | 可增加唯一性与数量校验 |
| evidence_query 不适合检索 | 是 | 应加入检索评测与 rerank |
| evidence 被模型改写 | 有限 | 最佳方案是只返回 chunk_id，由代码回填 |
| RAG 返回无关 chunks | 有限 | embedding、阈值、rerank、chunking 应改进 |
| OCR 乱码 | 否 | OCR 与文本质量门禁 |
| 总分错误 | 不应让 Prompt 负责 | Python 计算 |
| 问题生成太慢 | 可缩短输出 | 更应拆分任务、减少单次对象数量 |
| 问题重复 | 是 | 增加覆盖矩阵和去重校验 |
| retry 原因不可观察 | 否 | 日志应记录 validation error 摘要 |

## 8. 推荐的 Prompt 优化原则

### 8.1 通用原则

1. 将“任务目标、输入事实边界、决策规则、输出规则”分开写。
2. 不重复完整 JSON Schema 中已经明确的类型信息，避免 Prompt 过长。
3. 对业务语义给出明确规则，尤其是 Schema 无法表达的约束。
4. 强制保持输入主要语言。
5. 明确空值策略：不知道就返回空数组/空字符串/0 分，不得补全。
6. 明确 evidence 不是让模型重写的内容。
7. 在 Prompt 中加入自检步骤，但要求只输出最终 JSON，不输出思考过程。
8. 将高复杂度任务拆成更小调用，降低超长输出和重试成本。

### 8.2 parse_jd 应重点增加

- 多职位处理规则。
- criterion 设计规则：
  - 互斥、可评估、简历中可能找到证据。
  - 不把同一能力拆成多个重复标准。
  - 明确 must / important / bonus 的判定。
- 权重策略：
  - must 总权重应高于 bonus。
  - bonus 不应主导总分。
- evidence_query 规则：
  - 查询应包含技能/场景/成果同义词。
  - 不写完整问句，不包含“简历中提及”等无检索价值套话。

### 8.3 parse_resume 应重点增加

- 明确哪些事实必须引用：
  - candidate_name
  - 每项工作经历
  - 每项项目
  - 每项 achievement
  - 非通用技能或关键能力结论
- 同一事实只保留一次，处理重叠 chunk。
- OCR 疑似错误不得自行修正为确定事实，应写入 `ambiguities`。
- source ref 只引用 chunk_id 与原文片段，不得拼接多个 chunk。

### 8.4 evaluate_match 应重点增加

- 每个输入 criterion 恰好返回一次，顺序与输入一致。
- `score/status` 映射固定，例如：
  - 5 -> strong_match
  - 3-4 -> match 或 partial_match，需给出明确规则
  - 1-2 -> partial_match
  - 0 -> no_evidence 或 conflict
- 召回相似不等于证据支持。
- 没有直接证据时必须给 0，不因常识或相邻能力加分。
- 只返回 evidence chunk IDs，或至少要求 evidence 对象逐字复制。
- 对 must criterion 的冲突与风险写得更严格。

### 8.5 generate_questions 应重点增加

- 先生成“问题蓝图/覆盖矩阵”，再生成问题正文，或拆成多次调用。
- 每道题只服务一个主要评估目标，减少重复。
- 正式题、gap 题、歧义追问的目的分别定义。
- 问题必须能通过候选人的回答被判定，而不是纯开放讨论。
- 证据只引用 chunk ID。
- 对每道题限制数组长度与文本长度，以降低输出规模。
- 考虑将 `suggested_followups` 从每题 2-3 条缩减为 1 条，或按需生成。

## 9. 建议增加的代码与 Schema 校验

这些不是 Prompt 替代品，但会显著提高可靠性。

### JobProfile

- `criteria` 长度限制为 3-6。
- `criterion_id` 必须唯一。
- `name` 去重或相似度检查。
- 权重和继续由 Pydantic 校验。
- 可选：限制 bonus 总权重。

### ResumeProfile

- 所有 `source_refs.chunk_id` 必须来自输入 chunk 集合。
- `source_refs.text` 必须是对应 chunk text 的子串。
- 工作、项目、achievement 至少一个 source ref。
- 对重复事实做后处理去重。

### MatchEvaluation

- 输出 criterion ID 集合必须与输入完全一致。
- `score > 0` 必须引用输入 evidence。
- `score == 0` 时 evidence 必须为空。
- evidence 仅接受 chunk ID，其他字段由代码回填。
- `score/status` 映射校验。
- evidence chunk 必须属于对应 criterion 的候选 evidence 集合。

### QuestionSet

- 每道正式问题 evidence 非空。
- evidence 必须属于 candidate report。
- `related_criteria` 必须存在。
- gap_validation 必须关联低分/缺证据 criterion。
- 问题文本相似度去重。
- 限制每个数组和字符串长度。

## 10. 建议的 Prompt 评测集

至少建立以下固定案例：

1. 单一清晰中文 JD。
2. 同时包含两个职位的 JD。
3. 极短 JD。
4. 只有软技能、没有技术栈的 JD。
5. 中文简历，含 OCR 易错字符。
6. 简历 chunks 重叠且事实重复。
7. 简历明确满足全部 must criteria。
8. RAG 对缺失标准召回多个“看起来相关但不支持”的 chunks。
9. 公司账号粉丝量与个人粉丝量的语义区分。
10. 候选人存在明确冲突信息。
11. 问题生成输入中强项很多但缺口很少。
12. 问题生成输入中几乎没有直接证据。

建议指标：

- JSON/Pydantic 首次通过率。
- 平均重试次数。
- 每任务耗时 P50/P95。
- criterion 完整覆盖率。
- evidence chunk ID 忠实率。
- evidence text 原文一致率。
- 无证据时 0 分准确率。
- 问题类型分布通过率。
- 问题重复率。
- 问题对 JD criterion 的覆盖率。
- Prompt token、响应 token 与总成本。

## 11. 建议的交付验收标准

Prompt 优化不能只看几个“更好听”的输出。建议按以下标准验收：

1. 所有固定评测案例首次 Pydantic 通过率达到 98% 以上。
2. 不再发生 evidence chunk ID 幻觉。
3. 无直接证据时不得给正分。
4. 每个输入 criterion 恰好评估一次。
5. 问题生成不引用 candidate report 之外的证据。
6. 问题重复率显著下降。
7. `generate_questions` P95 延迟降低；若 Prompt-only 无法达到，应拆分调用或精简 Schema。
8. OCR 乱码案例必须在 LLM 前被拒绝或重新处理。
9. 日志能区分 Prompt 问题、Schema validation 问题、RAG 问题和上游文本质量问题。

## 12. 关键源码与日志索引

### Prompt 与 LLM 调用

- `backend/agents/harness.py`
- `backend/prompts/parse_jd.md`
- `backend/prompts/parse_resume.md`
- `backend/prompts/evaluate_match.md`
- `backend/prompts/generate_questions.md`
- `backend/prompts/generate_followup.md`
- `backend/agent/interview_tools.py`：旧式 Prompt 基线

### Schema 与工作流

- `backend/schemas/workflow.py`
- `backend/graph/candidate_workflow.py`
- `backend/services/analysis.py`
- `backend/routes/documents.py`
- `backend/routes/runs.py`

### 文档、RAG 与持久化

- `backend/services/documents.py`
- `backend/rag/milvus.py`
- `backend/repositories/runs.py`

### 真实证据

- `log/llm.log`：完整 Prompt、模型原始响应、validation error、耗时
- `log/backend.log`：API、重试与端到端运行证据

## 13. 可直接发送给 ChatGPT 的指令

```text
你是一名负责生产级结构化 LLM 系统的 Prompt Engineer 和 LLM Evaluation Engineer。

请阅读这份《ResuMate Agent：LLM Prompt 优化证据包》，基于其中的真实架构、真实日志案例、Pydantic Schema、RAG 数据流和真实模型输出，完成 Prompt 优化方案。

你的目标不是让输出“更像专家”，而是提高：
1. 首次 Schema 通过率；
2. 证据忠实度；
3. 无证据时的保守性；
4. JD criterion 与面试问题的业务质量；
5. 任务延迟与输出效率；
6. 可自动评测性。

请分别为 parse_jd、parse_resume、evaluate_match、generate_questions、generate_followup：
- 给出改进后的完整 Prompt；
- 解释每项关键改动对应的真实失败案例；
- 标明哪些问题不能靠 Prompt 解决；
- 给出需要配套增加的 Schema/Pydantic 校验；
- 给出自动化评测用例和量化指标。

特别要求：
- 不让模型计算 total_score；
- 不允许模型创造、改写或补全证据；
- 优先建议模型只返回 evidence chunk IDs，由代码回填原始证据；
- 明确处理多职位 JD、OCR 低质量文本、RAG 无关召回和重复 chunks；
- 对 generate_questions 评估是否应该拆成多次调用，并给出推荐调用设计；
- 输出最终建议时区分 Prompt-only 改动与需要代码/Schema 配合的改动。
```
