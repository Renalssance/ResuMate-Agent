# T12 后端独立审查

审查基线：`f3042d2`；固定包 `/tmp/t12-backend-review-package.diff`。工作区 `/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`。合同以 `docs/superpowers/plans/2026-10-30-t12-context-and-memory.md` 及主范围规格为准。范围仅后端、模型设置、存储和 E2E fixture；前端不在本次结论内。

## 结论

- **Spec compliance：主要合同符合，1 个 P2 事务问题修复前不建议判定后端全部完成。** 必保留区、显式模型容量、SDK 摘要、固定来源、确认记忆、旧会话失效和 worker 清理等已实现；问题在两库合同中的 MySQL 并发创建/删除路径。
- **Code quality：整体实现清楚且范围合适，需修复下述锁顺序问题。** 没有发现需要另建记忆平台、迁移框架、摘要引擎或通用重试层的理由。除下述问题外，本次审查未发现其他应阻断交付的后端问题。

## 唯一发现

### [P2] 创建任务与删除记忆的锁顺序相反，MySQL 可死锁并回滚用户请求

位置：`backend/services/agent_runs.py:149–151`（相关前置写入在 145–148）；对应 `backend/services/memory.py:82–90`。

`create_run` 先将新的 AgentRun 写入事务并占用 Session，再调用 `capture_memory_ids(...).with_for_update()` 锁定 BusinessMemory。`delete_memory` 恰好相反：先锁定并更新该 Memory，再用 `FOR UPDATE` 扫描该用户的 tailoring Runs。

对已有确认记忆，同时调用这两个公开接口时存在确定的锁循环：创建事务已经持有新 Run 行锁；删除事务取得 Memory 行锁后，在 Runs 扫描处等待创建事务；创建事务又在冻结记忆 ID 时等待删除事务。MySQL 因此选择一个事务作为死锁牺牲者。`create_run` 只处理 IntegrityError/RunError，删除路径与 RunRoute 也没有处理此 OperationalError，结果是一个合法请求返回 500；若删除被回滚，记忆正文与使用权也仍然保留。无需恶意请求或损坏数据；这是已支持的“开始任务”和“删除记忆”请求交叠。

修复应局限于这两条业务事务，统一 Run/Memory 的获取锁顺序，同时保留 SQLite 的事务起点和“创建冻结 ID 与删除撤销”一致性。补一个可控交叠的临时 MySQL 测试即可，证明两个请求能按顺序完成或给出既有业务冲突，且不会漏掉应失效会话；不需要新增通用重试框架。

该发现依据真实事务代码及 MySQL 行锁语义；本次按只读要求未做新的数据库写入复现，也未重跑已通过测试。现有记忆测试逐次创建/删除，未覆盖这两个事务的并发锁顺序。

## 已确认正确的实现

- 保留 T09 完整 SQL contextSnapshot 及 before/sourceRefs 校验；memory ID 没有加入 EvidenceSource 判别联合，不能作为经历事实引用。
- 模型缺显式容量即报 `model_context_not_configured`；输出 reserve 与必保留 system/tools 超限会在 provider 前失败。计数标为估算，统一采用 SDK 字符系数，未重复扣除 SDK reserve。
- middleware 按同名替换 SDK SummarizationMiddleware，在 SDK 计数前加入 SQL 必保留区；SDK 负责摘要、历史文件、溢出压缩和最终完整请求预算检查。摘要重试内部也重新检查撤销状态，没有另写摘要循环。
- 原文镜像保存在 StateBackend，manifest 使用稳定业务 ID、来源版本、用途和文件路径；长段落分块保留全部正文。`/inputs/**` 写权限被拒绝；SQL 快照仍是业务校验权威。
- 保存记忆要求本人登录、明确 confirmed=true、限定类型及内容长度；来源由服务写 manual。删除立即清空正文和来源，冻结信息仅含 ID。新记忆只影响新 Run。
- 受影响 graph Session 的 create/idempotent create/retry/answer/claim/执行边界均有 fence；排队和等待任务取消，运行中协作停止。历史产物保留，同 Session 的 PDF 导出不受 graph 失效限制。
- 只有 worker 在已有 execution_lock 内调用 SqliteSaver.delete_thread；所有 checkpoint 版本与 writes 交给官方 saver 清理，成功后才写 checkpoint_deleted_at。失败状态保留 pending，恢复扫描可继续处理。
- SQLite 增量补列与 MySQL 003 手工增量脚本沿用现有约定，旧容量保留 NULL。个人设置部分更新保持字段未显式提供时不变。

## 采用的验证证据

未重新运行任何已通过测试。

- `/tmp/resumate-t12-models-green.txt`：模型设置、存储、旧库升级，14 passed。
- `/tmp/task-12-memory-report.md` 与其回归记录：记忆定向 26 passed；相关回归 110 passed、1 个原有 MySQL 不适用跳过。
- `/tmp/task-12-context-report.md`、`/tmp/resumate-t12-context-final.txt`：双库上下文 13 passed；真实 SDK、磁盘 checkpoint 关闭重开、摘要故意不保留事实、文件原文引用和唯一合法草稿均有断言。
- 最终 SQLite 长案：原固定资料快照估算 88620；实际主请求完整估算 13567–20745；摘要请求完整估算 8559–12478；输入预算 27476；7 次摘要。不同口径不能据此声称真实费用节省；报告对此表述正确。
- 额外只读核对了锁定安装版本的 SDK `_input_budget`、`_call_with_budget`、`wrap_model_call`，确认应用注入顺序与 SDK 最终请求预算检查一致。

前端体验、实际截图、整体双库最终回归及教学交付由主控另行验收；本审查不以这些范围外工作缺席构造后端发现。
