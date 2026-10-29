# 第二课：先让数据表达正确，再让 Agent 行动

## 为什么要先建数据契约

一个用户点击“生成简历”，可能因为网络重试发送两次请求；worker 也可能重复收到消息。只在页面禁用按钮不能解决这些情况。T02 用数据库表达“哪些记录可以重复、哪些必须唯一”，T03 再用事务和条件更新实现业务状态变化。

本次未增加页面或开始真实任务。数据模型通过不意味着任务系统已完成。

## 三种状态放在哪里

| 数据 | 保存什么 | 代码 |
| --- | --- | --- |
| AgentSession / AgentRun | 对话归属、接受的请求、输入快照、执行代次、取消请求与结果引用 | [agent_models.py](../../backend/db/agent_models.py) |
| AgentRunEvent / AgentAction | 有序进度、待补充/审批动作、回答 | 同上 |
| ToolOperation | 一项业务操作是否已有结果 | 同上 |
| ProfileFact / ResumeVersion | 有版本的事实、简历草稿和事实引用 | [career_models.py](../../backend/db/career_models.py) |
| JobApplication 新字段 | 此次投递关联的岗位、版本和提交快照 | [models.py](../../backend/db/models.py) |
| Interview 系列表 | 后续多轮面试及消息去重的数据基础 | [career_models.py](../../backend/db/career_models.py) |

checkpoint 保存的是图执行状态，不负责这些业务约束。Redis 还没有接入，即使未来接入，它也不是上述记录的唯一事实源。

## 唯一约束怎样产生产品行为

- `(user_id, request_id)`：同一用户重复提交同一请求，数据库不允许第二份 Run；不同用户可以使用相同 request_id。返回已有 Run 的逻辑在 T03 实现。
- `(run_id, seq)`：同一任务的事件序号不能重复；分配序号仍需在服务层事务中完成。
- `(run_id, interrupt_id)`：重放图中同一补问时不会插入第二份动作。
- `(run_id, operation_key)`：创建草稿重复执行时不能插入第二份操作记录。操作记录与产物必须同事务写入，唯一约束本身不等于整套幂等实现。
- `(user_id, source_site, source_job_id)`：同一个人收藏相同来源岗位不能重复；手动粘贴没有来源 ID，NULL 允许多份独立记录。

AgentRun 通过 `(session_id,user_id)` 复合外键引用 Session，数据库会拒绝把 Bob 的 Run 放进 Alice 的 Session。其它资源（简历、岗位、版本）的用户归属仍需业务服务查询校验，不能把“有外键”误解为“权限都做完了”。

`active_run_id` 是 Session 的占用指针，T03 将用条件更新领取；本单元没有实现“同时只能一个活动 Run”的服务逻辑。

## 事实与表达为什么分开

“我负责后端接口”是事实；“主导核心 API 设计与交付”是表达。Agent 可以调整表达，但不能通过换措辞发明职责。

ProfileFact 使用 `fact_key` 标识同一条事实，`revision` 区分修订，每个修订都有独立 ID。ResumeVersion 的 `fact_refs` 指向具体修订 ID。把事实从 v1 改成 v2 后，旧版本仍能解释当时采用的依据。

本单元证明两个修订可以并存、重复修订被拒绝、引用可以还原；事实的修改服务和已确认版本不可变规则将在材料业务单元落实。ORM 本身不会自动阻止应用错误地更新已确认内容。

投递的 `submitted_snapshot` 保存当时提交内容，因此之后编辑草稿不会改变历史投递材料。本次测试直接改变草稿并重新读取投递，确认快照保持原值。

## 状态与事件不是任意字符串

[agent_runs.py](../../backend/schemas/agent_runs.py) 定义唯一的 RunStatus，以及按 `type` 区分的事件联合类型。例如 `run.status` 必须有合法 status，不能塞入文本增量的 payload。序号必须为正。

事件 JSON 保持计划约定的平面结构：

```json
{"runId":"r1","seq":2,"createdAt":"2026-10-29T00:00:00Z","type":"assistant.delta","payload":{"text":"正在准备"}}
```

SQL 表对 Run 状态增加 CHECK 约束，防止绕过 Pydantic 的非法写入；具体状态转换（例如 succeeded 不能 retry）则由 T03 业务服务判断。状态集合约束与状态转换规则是两个层次。

## 为什么两种数据库要分别跑

SQLite 与 MySQL 都能拒绝非法 CHECK，但驱动抛出的异常类型不同：本机 MySQL 对 CHECK 违反返回 3819 / OperationalError，SQLite 返回 IntegrityError。测试应该验证“确实拒绝且原状态保留”，而不是要求所有驱动错误分类一致。

本次 MySQL 使用临时数据目录和 socket，关闭网络监听；测试每次创建独立随机库，结束删除自己创建的库。旧库升级测试从仓库原始 MySQL 建表 SQL 开始，实际运行新增脚本后用 ORM 读取旧投递记录。

## 不破坏旧数据的增量变更

[MySQL 脚本](../../deploy/schema/001_agent_and_versions.sql) 只建表、加列和约束；SQLite 复用现有启动升级模式。新关联允许 NULL，旧记录保留公司、职位、日期和备注。

MySQL DDL 会隐式提交，所以“放在事务里”不代表结构变更能整体回滚。脚本需要一次性执行并在失败后检查进度，说明见 [数据库操作说明](../../deploy/schema/README.md)。

## 自己动手

1. 在临时数据库里连续插入相同 request_id，观察第二次提交被拒绝；再换 user_id，解释为什么允许。
2. 增加第二条 ProfileFact 修订，确认旧 ResumeVersion 引用仍指向第一条。
3. 给 run.status 事件传入 `{text: 'hello'}`，观察 Pydantic 报错；再直接向数据库写非法状态，观察 CHECK 拒绝。
4. 阅读投递升级测试，回答：为什么新增关联不能强制所有历史记录都非空？

下一课将把这些约束接入有身份校验的 API：创建、读取、取消、重试，并明确每个操作的事务边界。
