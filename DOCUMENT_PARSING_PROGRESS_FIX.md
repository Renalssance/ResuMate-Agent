# ResuMate Agent 文档解析进度与状态修复说明

**目标分支：** `new-agent`  
**目标：** 修复上传/解析进度不真实、解析时历史文档消失、批量任务进度串扰、解析完成后列表状态不更新。  
**原则：** 只修改文档上传、解析进度、列表状态同步相关代码；不改简历/JD 解析业务、Prompt、Milvus 数据结构和页面整体视觉风格。

---

## 1. 必须修复的问题

| 编号 | 问题 | 根因 |
|---|---|---|
| P0-1 | 文件上传、文本提取没有真实进度 | 上传使用普通请求；后端只发布固定 5%/20%，文件保存与提取在单个阻塞函数中完成 |
| P0-2 | 解析期间历史文档不可见 | `store.loading` 同时控制列表加载与上传解析，页面用 `v-if` 替换了整个列表 |
| P0-3 | 多文件进度重叠、旧任务未清理 | 页面只有一个 `useTaskSse` 实例；多个文件共用同一 `taskId`、步骤数组和进度卡 |
| P0-4 | 解析完成后列表仍显示“处理中” | SSE 只更新进度组件，没有更新/刷新 `documentStore.documents`；文档状态与任务状态未闭环 |

`StatusTag` 已支持 `success -> 已完成`，不要修改显示文案；应修复数据同步链路。

---

## 2. 目标行为

1. 多选文件后，**每个文件独立创建 taskId、HTTP 请求、SSE 连接和任务状态**。
2. 历史文档列表在上传、解析、删除、重解析期间始终可见。
3. 文件上传显示浏览器真实字节进度：`loaded / total`。
4. PDF 文本提取显示真实页进度：`current_page / total_pages`。
5. LLM 单次调用无法获得真实百分比时，显示“LLM 分析中”及不确定状态，禁止按时间伪造递增百分比。
6. 每个任务独立成功、失败和清理，不得重置或关闭其他任务。
7. 后端完成数据库提交后，前端列表必须自动更新为 `success/已完成`，无需手动刷新。
8. 单个文件失败不得影响同批其他文件。

---

## 3. 前端修改

### 3.1 拆分 Store 状态

修改 `frontend/src/stores/document.ts`：

```ts
const listLoading = ref(false)
const uploadingCount = ref(0)
const deletingIds = ref<Set<string>>(new Set())
const reparsingIds = ref<Set<string>>(new Set())
```

要求：

- `loadDocuments()` 只修改 `listLoading`。
- 上传、删除、重解析不得修改 `listLoading`。
- 增加 `upsertDocument(s)`，按 `document.id` 更新或插入，禁止重复记录。
- 增加 `refreshDocumentsSilently()`，刷新列表但不触发整页 loading。
- 保留已有历史数据；刷新失败不得清空 `documents`。

### 3.2 一文件一任务

删除 `DocumentsView.vue` 中单例：

```ts
const task = useTaskSse(PARSE_STEPS)
```

新增文档任务集合，建议封装为 `useDocumentParseTasks.ts`：

```ts
interface DocumentParseTask {
  taskId: string
  filename: string
  documentType: DocumentType
  status: TaskStatus
  stage: ParseStage
  uploadProgress: number
  stageProgress?: number
  overallProgress: number
  message: string
  errorReason: string
  steps: ProgressStep[]
}
```

使用：

```ts
const tasks = reactive(new Map<string, DocumentParseTask>())
```

要求：

- 每个文件单独生成 `taskId`。
- 每个文件单独调用上传接口。
- 每个 taskId 单独订阅和关闭 SSE。
- 新任务启动不得调用会关闭其他连接的全局 `reset()`。
- 任务结束后保留终态至少 3 秒；随后可自动折叠或由用户关闭。
- 不再使用一个进度卡表示多个文件。

### 3.3 批量上传队列

多选简历后由前端拆成单文件请求：

```ts
for (const file of files) {
  enqueueUpload(type, file)
}
```

默认并发数设为 `1`，最多允许配置为 `2`，避免多个 LLM/Milvus 任务同时挤占资源。禁止无上限 `Promise.all()`。

上传接口增加 Axios `onUploadProgress`：

```ts
onUploadProgress(event) {
  if (!event.total) return
  updateUploadProgress(taskId, Math.round(event.loaded * 100 / event.total))
}
```

说明：

- 该数值只表示浏览器到服务端的请求体传输进度。
- 后端“保存文件”不得继续标记为“上传进度”。
- 未提供 `event.total` 时显示不确定状态，不伪造百分比。

### 3.4 历史列表始终可见

修改 `DocumentsView.vue`：

```vue
<div v-if="store.listLoading && !store.documents.length">
  正在加载文档列表...
</div>
<div v-else>
  <!-- 文档表格 -->
</div>
```

要求：

- 有历史数据时，即使正在刷新也继续显示表格。
- 上传、解析、删除、重解析只影响对应按钮或对应行。
- 新任务可在进度区域展示，不得覆盖文档列表。

### 3.5 任务完成后同步文档状态

SSE 收到终态时：

```ts
if (event.stage === 'completed' && event.status === 'success') {
  await store.refreshDocumentsSilently()
}
```

同时上传 HTTP 返回后调用 `upsertDocuments(response.documents)`。两条路径必须幂等，解决 SSE 与 HTTP 返回顺序不确定的问题。

要求：

- 后端 `completed` 事件发布前必须已完成 `db.commit()`。
- 前端不得仅根据进度条 100% 推断文档成功。
- 列表最终状态以服务端文档记录为准。
- `failed` 任务不得被标记为 `success`。
- 重解析完成后同样刷新对应文档。
- 刷新失败时保留现有记录，并显示可重试提示。

### 3.6 进度组件

将单个 `TaskProgress` 替换为任务列表组件，例如：

```vue
<DocumentParseTaskList :tasks="[...tasks.values()]" />
```

每个任务至少显示：

- 文件名
- 当前阶段
- 当前阶段进度
- 总体进度
- 成功/失败状态
- 失败原因

禁止复用上一个文件的步骤状态。

---

## 4. 后端修改

### 4.1 单文件请求边界

前端批量选择必须拆成单文件请求。后端 `/api/documents` 应明确保证每个请求只处理一个文件：

- 推荐将 `files: list[UploadFile]` 改为 `file: UploadFile`；
- 或保留字段但校验 `len(files) == 1`，否则返回 422。

不要继续让多个文件共享一个 taskId。

### 4.2 拆分保存与提取

修改 `backend/services/documents.py`，将：

```py
store_and_extract_upload(file)
```

拆成可观测阶段：

```py
stored = await store_upload(file)
pages = extract_stored_pages(
    stored.path,
    stored.filename,
    progress_callback=callback,
)
```

要求：

- 文件写入完成后发布 `server_save` 完成事件。
- PDF 提取打开文档后先获得总页数。
- 每处理一页发布一次真实页进度。
- DOC/DOCX/TXT/MD 无可细分页数时，只发布开始和完成，不伪造中间百分比。
- OCR 只能在能够获得页级状态时发布页进度；否则显示不确定状态。
- 回调不得依赖 FastAPI 请求对象，保持服务层可测试。

### 4.3 SSE 事件契约

扩展 `SseProgressEvent`：

```json
{
  "task_id": "task_parse_xxx",
  "document_id": "resume:12",
  "filename": "resume.pdf",
  "stage": "extract",
  "status": "running",
  "stage_progress": 60,
  "overall_progress": 28,
  "current": 6,
  "total": 10,
  "message": "正在提取第 6/10 页",
  "data": {}
}
```

字段要求：

- `task_id`、`stage`、`status`、`message` 必填。
- `document_id` 在数据库记录创建后提供。
- `current/total/stage_progress` 仅在真实可计算时提供。
- `overall_progress` 必须单调不减。
- 终态仅允许：
  - `stage=completed,status=success`
  - `stage=failed,status=failed`

建议阶段：

```text
upload_client -> server_save -> extract -> llm_analyze
-> embedding -> milvus_save -> local_save -> completed
```

`upload_client` 由前端维护，不要求后端重复发布。

### 4.4 完成状态一致性

后端成功顺序必须固定：

```text
LLM 完成
Embedding/Milvus 完成
row.parse_status = "success"
db.commit()
db.refresh(row)
发布 completed 事件
返回 HTTP 响应
```

失败顺序：

```text
捕获异常
db.rollback()
更新可保留记录为 failed（若记录已提交）
发布 failed 事件
返回明确错误
```

禁止在数据库提交前发布 `completed`。

`_record()` 不得无条件返回 `vectorized=True`。若当前模型没有独立字段，至少根据真实成功状态返回；不要新增数据库迁移，除非仓库已有对应字段设计。

### 4.5 SSE 生命周期

修改 `useTaskSse.ts` / `services/sse.ts` 对应逻辑：

- 连接按 taskId 管理。
- 只关闭当前终态任务。
- 页面卸载时关闭全部属于该页面的连接。
- 正常终态关闭不得触发“连接异常”。
- `EventSource.onerror` 需区分任务终态后的正常关闭与真正断线。
- 同一 taskId 重复订阅应复用或显式替换，不得静默绑定错误回调。

本次不引入 Redis/Celery；保留当前单进程 `progress_hub`。需在代码注释中说明：多 worker、服务重启后的任务恢复不属于本次修复范围。

---

## 5. 状态机

```text
pending
  -> uploading
  -> server_saving
  -> extracting
  -> llm_analyzing
  -> embedding
  -> milvus_saving
  -> local_saving
  -> success

任意非终态 -> failed
```

约束：

- `success`、`failed` 为终态，不允许回退。
- 新文件必须创建新状态对象。
- 重解析必须创建新 taskId，但更新原 documentId。
- 任务进度不得跨 taskId 继承。
- 列表 `parseStatus` 与任务 `status` 分离；列表状态只以服务端文档记录为准。

---

## 6. 主要修改文件

前端：

```text
frontend/src/views/DocumentsView.vue
frontend/src/stores/document.ts
frontend/src/api/documents.ts
frontend/src/services/request.ts
frontend/src/services/sse.ts
frontend/src/composables/useTaskSse.ts
frontend/src/composables/useDocumentParseTasks.ts   # 新增
frontend/src/components/DocumentParseTaskList.vue   # 新增或重构
frontend/src/components/TaskProgress.vue
frontend/src/types/task.ts
frontend/src/types/document.ts
```

后端：

```text
backend/routes/documents.py
backend/services/documents.py
backend/services/progress.py
backend/schemas/workflow.py
backend/routes/tasks.py
```

同时更新相关前后端测试。不要修改无关 Agent、Prompt、匹配、试题生成逻辑。

---

## 7. 测试要求

### 前端单元测试

至少覆盖：

1. 上传时历史文档仍显示。
2. 两个文件生成两个 taskId 和两个独立状态。
3. 第二个任务开始不改变第一个任务状态。
4. 一个任务完成只关闭自己的 SSE。
5. SSE `completed` 后触发静默刷新并显示“已完成”。
6. HTTP 返回与 SSE 完成先后顺序变化时不产生重复文档。
7. 单任务失败不影响队列后续任务。
8. 上传进度使用 `loaded/total`。
9. 列表刷新失败不清空现有数据。

### 后端测试

至少覆盖：

1. 单文件上传成功事件顺序正确。
2. `completed` 在数据库提交后发布。
3. PDF 页级提取的 `current/total` 正确且单调。
4. 不可计算阶段不返回伪造 `stage_progress`。
5. 多文件请求按新契约拒绝或拆分，不共享 taskId。
6. 失败任务发布 `failed`，不会发布 `completed`。
7. 文档查询最终返回 `parse_status=success`。
8. `_record()` 不再无条件报告已向量化。

### 执行命令

Codex 先读取仓库现有脚本，再执行等价命令：

```bash
# backend
pytest
ruff check backend tests

# frontend
npm run lint
npm run test
npm run build
```

若仓库脚本名称不同，使用 `package.json`、`pyproject.toml` 中的实际命令，不得跳过测试。

---

## 8. 验收标准

- 上传大文件时，上传百分比连续变化，不再固定显示 5%。
- PDF 提取显示 `第 n/N 页`，数据来自真实处理进度。
- 解析期间历史文档表格始终可见。
- 一次选择 3 份简历时，出现 3 个独立任务，状态互不覆盖。
- 上一任务完成后不会污染下一任务，也不会残留为运行状态。
- 任一文件失败时，其他文件继续处理。
- 解析完成后 1 秒内列表状态自动变为“已完成”，无需刷新页面。
- 重解析完成后原文档行更新为“已完成”。
- 不出现重复文档、重复 SSE 连接或全局进度重置。
- 前后端测试、Lint、Build 全部通过。

---

## 9. 非目标与边界

本次禁止：

- 修改简历/JD Prompt、Schema 业务字段和解析结果内容。
- 修改匹配、试题生成、追问功能。
- 引入 Celery、Redis、Kafka 等新基础设施。
- 用定时器伪造 LLM、OCR、Milvus 进度。
- 为解决 UI 问题删除 SSE。
- 使用全局 `loading` 再次覆盖文档列表。
- 用刷新整页代替状态同步。
- 未经评估进行数据库迁移。
- 大规模重写页面样式。

---

## 10. Codex 执行要求

1. 先审计上述文件及现有测试，确认实际调用链。
2. 按“状态隔离 → 单文件任务 → 真实进度 → 完成状态同步 → 测试”顺序修改。
3. 保持现有接口兼容性；若必须调整上传字段，前后端与测试一次性同步修改。
4. 不得通过硬编码 `success`、延时刷新、假进度或隐藏组件绕过问题。
5. 完成后报告：
   - 根因确认；
   - 修改文件；
   - API/SSE 契约变化；
   - 测试结果；
   - 手工验证步骤；
   - 未解决的已知边界。
