# ResuMate Agent 最小 Demo 开发文档

## 1. 开发目标

实现题目场景 A 的最小端到端闭环：

```text
上传 1 份 JD 和多份简历
→ 解析并写入 Milvus
→ Agent 结构化提取
→ RAG 检索岗位相关证据
→ 计算候选人匹配度
→ 生成面试题与简历追问
→ Vue3 展示候选人排序和完整报告
```

重点展示后端 Agent 编排、RAG 证据链、结构化输出和可解释评分。不要开发完整招聘管理系统。

---

## 2. 固定技术栈

### 后端

- Python 3.11+
- FastAPI
- LangGraph
- OpenAI Python SDK，使用可配置的 OpenAI 兼容接口
- Pydantic v2
- PyMuPDF：PDF 文本提取
- python-docx：DOCX 文本提取
- PyMilvus + Milvus Standalone

### 前端

- Vue 3
- TypeScript
- Vite
- Element Plus
- Axios

前端只负责上传、触发分析和展示结果，不承载业务逻辑。

---

## 3. 核心功能

### 3.1 文档输入

- 上传 1 份 JD，格式为 PDF、DOCX 或 TXT。
- 一次上传多份简历，格式为 PDF 或 DOCX。
- 不实现 OCR；扫描件直接提示无法提取文本。

### 3.2 JD 解析 Agent

输出 `JobProfile`：

- `job_title`
- `summary`
- `responsibilities`
- `criteria`
- `interview_focus`

每个 `criterion` 必须包含：

- `criterion_id`
- `name`
- `description`
- `importance`: `must | important | bonus`
- `weight`
- `evidence_query`

约束：所有 `weight` 之和必须等于 100。

### 3.3 简历解析 Agent

输出 `ResumeProfile`：

- 基本信息
- 教育经历
- 工作经历
- 项目经历
- 技能
- 成果
- 模糊点 `ambiguities`
- 原文来源 `source_refs`

每条重要事实必须绑定页码、章节、原文片段和 `chunk_id`。

### 3.4 RAG 证据检索

1. 文档按页和章节切分，每块约 300～600 个中文字符，相邻块重叠约 50 字。
2. 使用 OpenAI 兼容 Embedding 接口生成向量。
3. 将 JD、简历 Chunk 写入 Milvus。
4. 对每个岗位标准使用 `evidence_query` 检索当前候选人的 Top-4 简历 Chunk。
5. 检索必须按 `run_id`、`candidate_id` 和 `document_type` 过滤。
6. 匹配 Agent 只能依据检索证据评分，不得凭完整简历自由推断。

### 3.5 匹配评分 Agent

对每项岗位标准输出：

- `score`: 0～5
- `status`: `strong_match | match | partial_match | no_evidence | conflict`
- `reason`
- `evidence`
- `missing_evidence`
- `risk`

评分含义：

- 5：充分且直接的实践证据
- 4：基本满足，有明确实践证据
- 3：部分满足，证据深度不足
- 2：只有关键词或间接经验
- 1：关联较弱
- 0：无证据或存在冲突

总分必须由 Python 计算，禁止 LLM 直接生成：

```python
total_score = sum(item.weight * item.score / 5 for item in evaluations)
```

推荐结论：

- `>= 80`: `strong_recommend`
- `>= 65`: `recommend`
- `>= 50`: `hold`
- `< 50`: `reject`

### 3.6 试题生成 Agent

每位候选人必须生成：

- 10 道正式面试题
- 3～5 道简历模糊点追问

10 道正式题固定分布：

- 简历经历验证：3 道
- JD 核心能力：3 道
- 场景设计：2 道
- 能力缺口验证：1 道
- 行为与复盘：1 道

每道正式题必须包含：

- 问题
- 类型
- 难度
- 考察点
- 关联岗位标准
- 出题证据
- 参考回答方向
- 评分标准
- 建议追问

---

## 4. LangGraph 工作流

```text
load_documents
→ index_documents
→ parse_jd
→ parse_resume
→ retrieve_evidence
→ evaluate_match
→ calculate_score
→ generate_questions
→ persist_report
```

其中：

- LLM 节点：`parse_jd`、`parse_resume`、`evaluate_match`、`generate_questions`
- 普通工具节点：文档提取、切分、Embedding、Milvus 检索、分数计算、结果持久化
- 多份简历在外层逐份调用同一个候选人分析子图
- JD 只解析一次并复用

所有 LLM 节点统一经过 `AgentHarness`，负责：

- OpenAI 兼容客户端配置
- Prompt 加载
- Pydantic/JSON Schema 结构化输出
- 模型名、耗时和错误日志

结构校验失败时直接返回失败，不实现 JSON 修复、重试链、模型降级或反思循环。

---

## 5. Milvus 设计

### `document_chunks`

保存 JD 和简历原文块：

- `id`: VARCHAR，主键
- `embedding`: FLOAT_VECTOR
- `run_id`: VARCHAR
- `candidate_id`: VARCHAR，JD 使用空字符串
- `document_type`: VARCHAR，`jd | resume`
- `filename`: VARCHAR
- `page_number`: INT64
- `section`: VARCHAR
- `chunk_index`: INT64
- `text`: VARCHAR
- `metadata`: JSON

向量距离使用 COSINE。

### `analysis_artifacts`

保存结构化结果：

- `id`: VARCHAR，主键
- `embedding`: FLOAT_VECTOR，使用结果摘要向量
- `run_id`: VARCHAR
- `candidate_id`: VARCHAR
- `artifact_type`: VARCHAR
- `summary`: VARCHAR
- `content`: JSON
- `created_at`: VARCHAR

`artifact_type` 只需要：

- `job_profile`
- `resume_profile`
- `candidate_report`

使用官方 Milvus Standalone Docker Compose，不自行简化为不完整的单容器配置。

---

## 6. FastAPI 接口

### `POST /api/runs/analyze`

`multipart/form-data`：

- `jd_file`: 单文件
- `resume_files`: 多文件

同步完成整个流程并返回：

- `run_id`
- 候选人排序摘要
- 每位候选人的 `candidate_id`、姓名、分数、推荐结论

### `GET /api/runs/{run_id}`

返回运行摘要和候选人排序。

### `GET /api/runs/{run_id}/candidates/{candidate_id}`

返回完整 `CandidateReport`。

### `POST /api/runs/{run_id}/candidates/{candidate_id}/evidence/search`

请求字段：

- `query`
- `top_k`，默认 4

返回 Milvus 检索到的证据块，用于 Demo 展示 RAG 能力。

---

## 7. Vue3 前端

只实现一个工作台页面，不做复杂路由。

### 页面区域

1. **上传区**
   - JD 单文件上传
   - 简历多文件上传
   - 开始分析按钮

2. **候选人列表**
   - 按匹配分数降序展示
   - 显示姓名、分数、推荐结论和前三项优势

3. **候选人详情**
   - 岗位匹配总览
   - 分项评分与原文证据
   - 结构化简历
   - 10 道正式面试题
   - 3～5 道模糊点追问

4. **RAG 证据检索**
   - 输入查询
   - 展示相似度、页码、章节和原文片段

前端状态直接保存在页面组件或 composable 中，不引入 Pinia。

---

## 8. 项目目录

```text
ResuMate-Agent/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── agents/
│   │   ├── graph/
│   │   ├── rag/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── repositories/
│   │   ├── prompts/
│   │   └── core/
│   ├── tests/
│   ├── main.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── composables/
│   │   ├── types/
│   │   └── App.vue
│   └── package.json
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 9. 环境变量

```env
OPENAI_API_KEY=
OPENAI_BASE_URL=
LLM_MODEL=
EMBEDDING_MODEL=
EMBEDDING_DIMENSION=
MILVUS_URI=http://localhost:19530
MILVUS_TOKEN=
BACKEND_CORS_ORIGINS=http://localhost:5173
```

禁止硬编码 API Key、模型名称、向量维度和 Milvus 地址。

---

## 10. 明确边界

不要实现：

- 用户登录、权限和多租户
- 人才库或岗位库管理后台
- OCR
- 场景 B 模拟面试
- WebSocket、SSE、Celery、Redis
- 异步后台任务
- 多模型路由和模型降级
- 自动重试、JSON 修复、兜底 Prompt
- 反思循环和自动补丁
- 人工编辑岗位画像或解析结果
- 报告 PDF 导出
- 前端复杂状态管理
- 与当前闭环无关的 CRUD

---

## 11. 验收标准

完成后必须满足：

1. 可上传 1 份 JD 和至少 3 份简历。
2. PDF/DOCX 文本可正确提取并写入 Milvus。
3. 每个岗位标准都有独立 RAG 检索证据。
4. 所有大于 0 的单项评分至少引用 1 条简历证据。
5. 岗位标准权重总和为 100。
6. 总分由 Python 根据分项评分计算，范围为 0～100。
7. 每位候选人生成恰好 10 道正式面试题。
8. 每位候选人生成 3～5 道模糊点追问。
9. 前端按分数展示候选人排名，并能查看完整报告和证据。
10. `docker compose up --build` 后可以完成 Demo。
11. README 包含启动步骤、架构图、数据流和关键 Prompt 说明。
12. 至少提供评分计算、Schema 校验和 Milvus 检索的基础测试。

---

## 12. Codex 执行要求

- 严格按本文档实现，不擅自扩展功能。
- 先打通单候选人完整链路，再支持多简历循环。
- 每完成一个阶段先运行测试，再进入下一阶段。
- 所有 Agent 输出先定义 Pydantic Schema，再编写 Prompt 和节点。
- 所有匹配理由和面试题必须能够回溯到 Milvus 中的简历证据。
- 优先保证核心闭环可运行，其次才是页面样式。
