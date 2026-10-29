# T14 B 文档迁移完成报告

工作树：`/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`。基线由父代理确认 T13 commit `26d1a35`，收到 GO 后开始修改。未运行 git、未调用付费模型、未运行完整后端套件。

## 实现

- 上传先查用户请求键，重复请求在存文件之前返回同一 Run；首次保存原件并预建 pending Resume/JD，与 durable Run/queued event 同事务提交。返回 `202 {taskId: server UUID}`。
- 上传、重解析、已保存岗位及回答分析入口均只提交统一 Run；不再依赖 FastAPI BackgroundTasks 或 progress_hub。原同步响应通过共享有限等待返回。
- `document_tasks.run_document_parse(run_id, epoch)` 使用短会话，从已保存 file_path 获取原件。Cloud 原件在受理后只删除本地缓存，worker 重新下载原件；本地原件保留。
- 保留现有 content_hash 复用结构化结果优化，未引入新摘要。失败或取消保留已受理文档及原件；受理前失败清理新原件。重试沿用同一文档身份。
- 模型与 embedding 不持有 SQL 写事务。每次模型请求由 Harness 的 sync guard 检查 execution epoch/cancellation 和来源归属；索引前、最终 SQL 写前再检查。
- `parse:<documentId>` ToolOperation、文档结果、artifact.created、不可变 result_json 和 Run 成功同一 SQL 事务。成功重新解析刷新 updated_at；后续显式重解析不改变较早 Run 的结果。重复请求同步返回较早 Run 的原响应。
- 已保存 JD 文本不读取原件、不生成向量；保留保存的岗位标题和原文，结果 vectorized=false。
- `DOCUMENT_STORAGE_ROOT` 在调用时解析，默认仍是原 data/documents；方便 E2E 隔离，避免默认参数预绑定旧目录。

## 补充实际缺口（父代理批准扩展两 RAG 文件）

Chroma/MySQL `replace_document_chunks` 原来在 embedding 返回后立即写索引。如果 embedding 等待时用户删除文档或取消任务，最终 SQL 能拒绝结果，但索引已写入。新增可选同步 `before_write` 回调，仅在 embedding 返回后、索引写入前执行；worker 传入 _guard。未增加一般化注册或兼容执行层。

测试使用真实 Chroma 临时目录、真实 SQL 索引存储和实际 worker，在 embed_many 内删除来源/取消 Run。两个业务数据库 × 两个索引实现 × 两种变化的 8 个场景，修复前均残留 1 条索引，修复后均为 0。

## 修改文件

生产：
- backend/routes/documents.py
- backend/routes/jobs.py
- backend/services/documents.py
- backend/services/document_tasks.py（新增）
- backend/rag/chroma.py
- backend/rag/mysql.py

测试：
- backend/tests/test_document_tasks.py（新增）
- backend/tests/test_document_parse_cache.py
- backend/tests/test_document_cloud_routes.py
- backend/tests/test_async_submissions.py
- backend/tests/test_jobs.py
- backend/tests/test_document_service.py

## 验证证据

原始 RED：`/tmp/t14-documents-red.log`，旧上传返回客户端 `upload-one` 而非持久 Run UUID，1 failed/1 MySQL 未启用 skipped。此后双库全部启用 socket `/tmp/resumate-mysql-t02/mysql.sock`。

第一次共享接口对接：`/tmp/t14-documents-first-green.log`，C 正在迁移 graph 旧 import 时 collection failed；随后依赖落地后 `/tmp/t14-documents-green-attempt2.log` 28 passed。

embedding RED：`/tmp/t14-document-embedding-red-clean.log`，8 failed，均是实际残留索引 count=1。更早 `/tmp/t14-document-embedding-red.log` 首个 SQLite 场景夹具建表过晚；修正夹具后重新取得 clean RED，未将夹具错误当产品缺口。

中间回归日志：`/tmp/t14-document-embedding-green.log` 检出 before_write 字符串编辑误进入检索路径，已移除；`/tmp/t14-document-embedding-green-final.log` 81 passed。

最终定向命令：

```sh
RESUMATE_TEST_MYSQL_SOCKET=/tmp/resumate-mysql-t02/mysql.sock .venv/bin/python -m pytest backend/tests/test_document_tasks.py backend/tests/test_document_parse_cache.py backend/tests/test_document_cloud_routes.py backend/tests/test_async_submissions.py backend/tests/test_jobs.py backend/tests/test_document_service.py backend/tests/test_document_structured_data.py backend/tests/test_mysql_rag.py backend/tests/test_chroma_store.py backend/tests/test_cloud_storage.py -q
```

最终原始输出：`/tmp/t14-documents-final-green.log`：**161 passed, 5 warnings in 15.25s**。警告均为现有 PyMuPDF SWIG 类型 deprecation，非任务失败。

## 集成提示与边界

- Parent E2E RAG 测试对象需接受 `before_write`，并在模拟写入前调用它；生产 Chroma/MySQL 已实现。
- C Harness 已对接 `AgentHarness(user_id=..., guard=..., progress_callback=...)` 同步回调。
- A 核心负责 queued cancellation、stale worker terminal、finish_run failed/cancelled 的 parse_status 更新，B 不再重复更新。
- 这些是实际持久 API/worker/SQL/索引定向测试，未宣称实际杀进程恢复或页面截图验收完成；父代理负责四断点与浏览器联调。
- 模型/embedding 调用在进程中断后可以重复，保证范围为 SQL 业务产物与保存响应不会重复。SQL 为权威，索引替换是可重放操作。
