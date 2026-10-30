# T16 A+C 核心与记忆交付

日期：2026-10-30。工作树 `/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`。生产实现已冻结；无 git add/commit、付费模型、全后端或 E2E 重复运行。根代理负责统一全套与真实浏览器。按用户最新决定，后续采用 HTTP 文字面试方案，不实施 T21。

## 已实现行为

- 从本人已关联确认材料的 Application 创建面试。简历来自 submitted_snapshot；当前岗位另外冻结并保存 capturedAt。请求重放返回原 interviewId/runId，不再冻结当前来源。
- typed InterviewCreate、四类 discriminated command、严格确认 bool；RunCreate 精确增加 interview_generation/interviewId/expectedTurn/sessionId，旧 kind 不接受面试字段。
- 回答不可变；回答、Command、Run、answer.accepted 与原 ack 一次事务接受。相同 ID/内容重放原 ack，即使后来已结束；同 ID 异内容冲突，不同 ID 再答同题也冲突。
- queued 取消即时终态，running 仅请求停止；finish 与取消同事务。generation.retry 创建新 Run，保留旧历史；不在停止尚未完成时重试。
- create_run_in_transaction/cancel_run_in_transaction 不提交、不回滚；公开旧函数保留原调用方式。公共 Run 写入口不能绕过面试命令，其他 kind 不能借用面试 AgentSession。
- worker 共享接口为 guard_interview_execution / finish_interview_generation / append_interview_event；统一 memory→InterviewSession→Run→AgentSession，父行 no-op UPDATE、MySQL current reads 与 SQLite 写门；模型调用不在该事务内。B 拥有真实图、结构化输出/引用绑定、step 写入和 worker 调度。
- Snapshot 返回 userId/applicationId/sourceSnapshot/turns/currentTurn/generation/lastSeq/sessionInvalidated；最近生成按接受命令的 SQL 自增 id 确定，避免 MySQL 秒精度时间与随机 UUID 排错。
- HTTP 新生成先短 SQL 查精确重放，关闭请求 Session，再 await Redis admission，随后新事务重查全部提交权限。已接受重放、读取、取消、结束不消耗新生成额度。两个尚未受理的并发请求都经过 admission，SQL 最终只接受一份；计数是 admission 尝试，不是接受次数，没有 reservation 平台。
- 反馈记忆只保存本人已落库 practiceFocus，绑定实际 interviewId/turnId；确认幂等，删除后不复活，不新增 ProfileFact。面试 Run 纳入既有记忆读取/删除/失效检查；B 的 worker 清理过滤同步扩展。真实 checkpointer 验证仅持执行锁后的恢复扫描清除目标图历史与 writes，其他 thread 保留。
- SQLite 启动增量与 `005_text_interviews.sql` 增加五个 nullable 字段及 AgentSession FK/索引。旧骨架保持 NULL 与原问题/命令，返回 context_missing，不伪造历史资料。

## 文件

新增：`backend/schemas/interviews.py`、`services/interviews.py`、`services/interview_commands.py`、`routes/interviews.py`、`tests/interview_fixtures.py`、`tests/test_interviews.py`、`tests/test_interview_memory.py`、`deploy/schema/005_text_interviews.sql`。
修改：`backend/db/career_models.py`、`db/database.py`、`schemas/agent_runs.py`、`services/agent_runs.py`、`services/memory.py`、`routes/api.py`、`deploy/schema/README.md`。
B 独占 runtime/factory/worker_tasks；本代理没有改这些文件。Frontend memory sourceRef 类型由根代理处理。

## 红绿与实际发现

所有 pytest 命令均使用 `.venv/bin/python`，双库设置 `RESUMATE_TEST_MYSQL_SOCKET=/tmp/resumate-mysql-t02/mysql.sock`，为每案创建独立测试库。

| 目的/发现 | RED | GREEN |
| --- | --- | --- |
| 冻结材料、重放、原子回答/命令和两库当前读 | `/tmp/task-16-core-red-acceptance.txt`：缺新 schema | `green-acceptance.txt`：25 passed / 5.33s |
| HTTP admission 无 SQL 等待、确认记忆与删除传播 | `/tmp/task-16-core-red-memory-http.txt`：4 failed + 4 missing-route errors + 29 passed | `green-memory-http.txt`：37 passed / 7.49s |
| 两不同命令取消同 Run 不重复事件；旧表升级 | `/tmp/task-16-core-red-upgrade-cancel.txt`：4 failed | `green-upgrade-cancel.txt`：4 passed / 1.06s |
| SQLite 并发创建：后者看见已提交 Run，却因临时 Interview ID 不同返回假冲突 | `/tmp/task-16-core-red-concurrent-create.txt`：宽定向 1 failed + 90 passed + 3 skipped | `green-concurrent-create.txt`：两库 2 passed / 0.61s；回滚后按原申请选择重读接受结果 |
| MySQL 同秒 Run 排序，以及公开 Run 快照仍仅识别 tailoring 失效 | `/tmp/task-16-core-red-run-order-snapshot.txt`：6 failed | `green-run-order-snapshot.txt`：6 passed / 1.50s |

上表 GREEN 简写路径均以 `/tmp/task-16-core-` 为前缀。宽定向首次输出原路径 `green-regressions.txt` 也保留其失败事实，没有覆盖成通过。

最终定向命令：

```sh
RESUMATE_TEST_MYSQL_SOCKET=/tmp/resumate-mysql-t02/mysql.sock .venv/bin/python -m pytest backend/tests/test_interviews.py backend/tests/test_interview_memory.py backend/tests/test_worker_delivery.py backend/tests/test_agent_memory.py -q
```

**93 passed, 3 skipped, 5 existing Swig warnings in 21.30s**。原始输出 `/tmp/task-16-core-green-final.txt`。新 A 两文件共 51 passed；既有 worker_delivery/agent_memory 共 42 passed + 3 数据库专属锁测试的预期方言跳过，不是缺 MySQL。涵盖初始受理失败全回滚、并发初始请求只一份、MySQL 先建立旧 RR 快照仍读原 ack、exhausted recovery 真终态、删除原岗位/申请后冻结输入仍可合法重试、记忆清理与旧导出会话语义。

## B runtime 只读跨层审查

已查看 `agent_runtime/interviews.py`、`interview_context.py` 与双方共享接口。成功路径 guard → 校验/绑定 refs → feedback/question/operation/events → finish 最后 commit；异常原事务回滚后新短事务相同锁序收尾；取消/epoch 丢失/重复 handler 不写业务；同 Run 恢复实际 checkpoint，新 Run 清理上轮临时图状态。这些路径当前正确，无新 B finding。没有重复跑 B 已绿图测试。

## 追加授权的两个前端修复

根代理在只读审查后明确分配修复；仅改 `ApplicationsView.vue`、`InterviewView.vue` 与各自 `.spec.ts`。

1. 创建面试尚未返回时离开投递页，旧响应仍 router.push 强制跳回面试。增加页面存活判断，在卸载后不导航/改旧视图，保留原 requestId 供回来后重放。
2. 保存练习记忆过程中 refresh 可替换 snapshot，成功响应改的是旧 turn 对象；或者保存成功后旧 GET 又覆盖 memoryId。成功时按 turn.id 更新当前快照、使较早 GET 的 readRequest 失效，并恢复适用的轮询。

原有 invalidated 文案与手机 CSS 保留；未碰稳定预览端口。

RED `/tmp/task-16-core-red-frontend-races.txt`：**3 failed + 12 passed**（记忆刷新先返回/后返回各一案，离页迟到导航一案）。GREEN `/tmp/task-16-core-green-frontend-races.txt`：**15 passed / 2 files / 1.27s**。执行 `npm --prefix frontend run test:unit -- src/views/InterviewView.spec.ts src/views/ApplicationsView.spec.ts`。未重复全前端、lint 或浏览器，交根代理统一收口。

## 教学要点与剩余边界

- ack 说明“已接受”，不是模型结果；丢响应时重放的是同一份命令，不能编辑原命令正文后复用 ID。
- 业务回答与生成 Run 必须一起提交，发布只负责叫醒；发布故障不抹掉 SQL 接受事实，scanner 能补发 queued Run。
- 取消检查只有和业务写入处于同一事务才阻止迟到结果；finish_run 本身不是回滚迟到业务的 guard。
- SQL 当前轮与框架 checkpoint 各司其职，业务顺序不能靠秒级时间和随机 UUID 推测。
- 练习回答/反馈不是简历经历；只有明确确认的 practiceFocus 才进入偏好记忆，删除后旧图失效与清理状态可见。

本子单元无未完成生产项。远程 CloudBase SQL 未执行；真实模型质量、全后端、完整 eval 与最终浏览器证据由根/B/E各自单元负责，不能用此处单元结果替代。
