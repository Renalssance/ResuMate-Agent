# ResuMate Agent

ResuMate Agent 是一个面向招聘场景的简历与 JD 分析工作台。系统基于 FastAPI、Vue 3、LangChain、PostgreSQL 和 Milvus，支持简历解析、岗位描述解析、候选人与岗位匹配分析，以及面试问题辅助生成。

## 功能概览

- 上传 PDF、Word 简历并提取结构化候选人信息
- 创建或导入 JD，并提取岗位要求、技能栈和关键条件
- 将简历与 JD 的关键信息写入 PostgreSQL 和 Milvus
- 基于简历与 JD 生成匹配度评分、匹配理由和风险缺口
- 根据岗位与候选人经历辅助生成面试题和追问方向
- 支持批量分析任务，将多份简历加入同一岗位分析流程

## 模块进度

- [x] 批量分析任务模块：分析任务、候选人关联、结果表结构与基础 CRUD API
- [x] 批量上传多份简历：一次任务内上传多份简历并自动解析
- [ ] 批量匹配与候选人排序：对同一 JD 下所有简历评分、排序、落库
- [ ] 向量检索匹配模块：基于 JD 向量召回候选简历并进入精评
- [ ] 正式试题生成模块：至少 10 道题，包含考察点、难度、评分标准、参考要点
- [ ] 追问模拟模块：针对简历模糊点生成 3-5 个追问
- [ ] 结果页/报告页：任务流、候选人排行榜、单人详情、题目和追问展示
- [ ] 结果导出：候选人排名、单人面试题报告、完整分析报告

## 本地部署

### 1. 环境准备

- Python 3.12+
- uv 或 pip
- Docker / Docker Compose，用于启动 PostgreSQL、Redis、Milvus、MinIO 和 Attu

### 2. 安装依赖

```bash
uv sync
```

或：

```bash
python -m venv .venv
pip install -e .
```

### 3. 创建 `.env`

参考 `.env.example` 配置：

```env
ARK_API_KEY=
MODEL=
BASE_URL=
DATABASE_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/langchain_app
REDIS_URL=redis://127.0.0.1:6379/0
JWT_SECRET_KEY=

VECTOR_STORE_ENABLED=true
MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530
PROFILE_VECTOR_COLLECTION=candidate_profile_vectors
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_DEVICE=cpu

PDF_OCR_ENABLED=true
PDF_OCR_MAX_PAGES=8
PDF_OCR_RENDER_SCALE=2.5
PDF_TEXT_MIN_CHARS=30
```

### 4. 启动基础设施

```bash
docker compose up -d
```

默认端口：

- PostgreSQL: `5432`
- Redis: `6379`
- Milvus: `19530`
- Attu: `8080`
- MinIO: `9000`, `9001`

### 5. 启动应用

```bash
uv run uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
```

访问：

- 前端: `http://127.0.0.1:8000/`
- API 文档: `http://127.0.0.1:8000/docs`
- Attu: `http://127.0.0.1:8080/`

## 项目结构

```text
backend/
├── app.py              # FastAPI 入口
├── auth/               # JWT 认证与角色解析
├── routes/             # API 路由
│   ├── api.py
│   ├── analysis.py
│   ├── chat.py
│   ├── resume.py
│   └── jd.py
├── schemas/            # Pydantic 请求/响应模型
├── db/                 # SQLAlchemy 模型、数据库连接、Redis 缓存
├── middleware/         # API 限流
├── agent/              # 面试 Agent 与简历/JD 工具
├── vector/             # Embedding 与 Milvus 向量写入
└── rag/document_loader.py
                        # PDF/Word/Excel 文本读取与分片

frontend/
├── index.html
├── script.js
└── style.css
```

## 向量入库策略

上传简历或创建 JD 后，系统会：

1. 抽取原始文本
2. 调用 LLM 生成结构化 JSON
3. 写入 PostgreSQL 的 `resumes` 或 `job_descriptions`
4. 将关键信息压缩成 profile 文本
5. 生成 embedding 并写入 Milvus 集合 `candidate_profile_vectors`

Milvus 中保存的字段包括：

- `doc_type`: `resume` 或 `jd`
- `user_id`
- `source_id`: 简历 ID 或 JD ID
- `title`
- `content`: 用于向量检索的关键 profile 文本
- `metadata_json`: 结构化元数据
- `embedding`

## API 速览

| 路由 | 说明 |
| --- | --- |
| `POST /auth/register` | 注册 |
| `POST /auth/login` | 登录，返回 Bearer Token |
| `GET /auth/me` | 获取当前用户 |
| `POST /chat/stream` | 面试助手流式对话 |
| `POST /resume/upload` | 上传、解析简历并写入向量库 |
| `GET /resume` | 简历列表 |
| `GET /resume/{id}` | 简历详情 |
| `DELETE /resume/{id}` | 删除简历并删除向量 |
| `POST /jd` | 创建、解析 JD 并写入向量库 |
| `GET /jd` | JD 列表 |
| `GET /jd/{id}` | JD 详情 |
| `DELETE /jd/{id}` | 删除 JD 并删除向量 |
| `POST /analysis/jobs` | 创建分析任务 |
| `GET /analysis/jobs` | 分析任务列表 |
| `GET /analysis/jobs/{id}` | 分析任务详情 |
| `DELETE /analysis/jobs/{id}` | 删除分析任务 |
| `POST /analysis/jobs/{id}/candidates` | 将简历加入分析任务 |
| `POST /analysis/jobs/{id}/resumes/upload` | 批量上传简历，解析后自动加入分析任务 |
| `DELETE /analysis/jobs/{id}/candidates/{candidate_id}` | 从任务移除候选人 |

## 测试工具

启动后端后，可以用内置脚本测试批量分析任务：

```bash
python scripts/test_analysis_module.py
```

脚本会自动注册或登录测试用户，然后依次创建任务、查询列表、查询详情、更新任务，并默认删除测试任务。

保留创建出来的任务：

```bash
python scripts/test_analysis_module.py --keep
```

使用已有简历 ID 测试候选人加入流程：

```bash
python scripts/test_analysis_module.py --resume-ids 1,2,3 --keep
```

测试任务内批量上传简历：

```bash
python scripts/test_analysis_module.py --resume-files data/resumes/a.pdf,data/resumes/b.docx --keep
```

单独检查扫描版或图片版 PDF 的 OCR 效果：

```bash
python scripts/ocr_pdf.py data/resumes/a.pdf --output data/resumes/a.ocr.txt
```

可选环境变量：

- `TEST_BASE_URL`: 默认 `http://127.0.0.1:8000`
- `TEST_USERNAME`: 默认 `analysis_tester`
- `TEST_PASSWORD`: 默认 `analysis_tester_123`
- `PDF_OCR_ENABLED`: 默认 `true`，PDF 无文字层时自动 OCR
- `PDF_OCR_MAX_PAGES`: 默认 `8`，单份 PDF 最多 OCR 页数
- `PDF_OCR_RENDER_SCALE`: 默认 `2.5`，渲染倍率，越高越慢但可能更准
- `PDF_TEXT_MIN_CHARS`: 默认 `30`，普通解析低于该字符数时判定为扫描版或图片版 PDF
