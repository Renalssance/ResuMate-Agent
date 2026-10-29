# T12 后端限定复审

范围：仅复核 `/tmp/t12-memory-scoped-fix.diff` 中的原 P2 MySQL 锁顺序修复，以及新增 `sessionInvalidated` 后端合同。沿用原 T12 brief 和绑定合同；没有扩展到无关旧实现或前端，没有重复运行已通过测试。

## 结论

- **Spec compliance：本次范围通过。** 原 P2 已解决；历史任务会话失效信息与 PDF 隔离符合合同。
- **Code quality：本次范围通过。** 修复直接统一现有事务锁顺序，复用已有表和生命周期；未引入通用重试、额外锁表、迁移或队列机制。
- **新重要回归：未发现。** 先前后端审查的唯一阻断项可关闭。

## 逐项复核

### 原 P2：创建 Run / 删除记忆的 MySQL 反向锁顺序 — ADDRESSED

位置：`backend/services/agent_runs.py:126–129`；`backend/services/memory.py:29–39`、`:89–98`。

创建任务现在在任何 Session/Run INSERT、Session 占用和相关外键锁之前冻结记忆 ID。创建与删除先执行相同的按本人 user_id 限定的 memory no-op UPDATE，然后才继续获取 Run/Session 锁，因此原来的 Run→Memory / Memory→Run 环路已经解除。等待删除提交的创建请求读取的是仍有效的记忆 ID：新 Session 不带已删除记忆，旧失效 Session 则通过既有业务错误拒绝。

no-op UPDATE 也在 SQLite 中先建立写事务，避免仅把 SELECT 提前后，让删除漏掉尚未插入的 Run。这是当前两种数据库真实事务语义所需的小修复；没有修改记忆内容或删除时间。

证据：已读 `/tmp/t12-memory-concurrent-red.txt`，新建 Session 和复用 Session 两种原实现均实际触发 MySQL 1213；已读对应 green 记录，2 passed、2 个 SQLite 不适用跳过。新增 SQLite 独立连接测试直接验证冻结后到 Run 提交前的 writer 排他，以及提交后删除能识别并取消该 Run。测试使用同步事件/SQL 执行钩子或即时 writer 探测，未依赖随机压力或睡眠猜测。

### 历史 Run 的会话失效派生字段 — ADDRESSED

位置：`backend/services/agent_runs.py:221–235`。

`run_snapshot` 在现有同一条 SELECT 中 JOIN AgentSession，并与 Run status、待处理动作、事件 cursor 一起读取 context_invalidated_at；返回 `sessionInvalidated` 仅在 tailoring 且 Session 已失效时为 true。它是独立派生信息，不覆写原 status、errorCode、events 或业务产物；同 Session 的 resume_export 明确返回 false。新增 JOIN 不改变既有归属过滤、动作索引或 cursor 取值。

新增两库测试保存历史 failed/model_timeout，断言 snapshot 暴露失效状态而历史事件数量未变，并验证同 Session PDF 仍为 queued 且字段为 false。前端如何使用字段由前端 reviewer 单独复核。

## 采用的最终证据与边界

- `/tmp/task-12-memory-fix-report.md`：修复范围、两库专项证据及跳过原因。
- `/tmp/t12-memory-scoped-fix.diff`：仅三个文件变更，生产改动与所述修复对应。
- `/tmp/t12-memory-concurrent-red.txt` / `/tmp/t12-memory-concurrent-green.txt`：原缺陷复现与修复结果。
- `/tmp/t12-memory-snapshot-red.txt`：原先缺字段在 SQLite/MySQL 的失败记录。
- `/tmp/t12-memory-fix-final.txt`：最终 90 passed、4 个明确数据库适用性跳过；警告为已有依赖/生命周期警告。

本次未重新执行测试、未修改产品代码。全后端最终回归、E2E 和截图以主控正在进行的独立验收为准；不把本次限定复审当作它们的替代。
