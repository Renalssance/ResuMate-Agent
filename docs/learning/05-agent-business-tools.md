# 第五课：让 Deep Agents 执行可恢复的业务工具

日期：2026-10-29。对应 T05。当前自动测试使用确定性本地模型；未据此声称真实模型的简历生成质量已通过验收。

## 从 SDK 到业务应用

框架提供模型与工具调度、interrupt、checkpoint 和状态恢复。项目负责用户归属、输入版本、取消、业务事务、幂等产物与任务状态。二者职责不同；本项目没有再写一套模型—工具循环。

唯一入口是 [factory.py](../../backend/agent_runtime/factory.py)：读取个人模型设置、构建 ChatOpenAI、加载简历技能，再调用 `create_deep_agent`。密钥留在客户端对象里，不进入 checkpoint。通用 execute 和 task 工具被显式禁用；默认文件后端属于图内存状态，不可访问宿主机任意文件。

[runner.py](../../backend/agent_runtime/runner.py) 使用持久化 session_id 作为 thread_id：

1. 第一次运行传入任务请求。
2. 工具 `ask_applicant` 调用 interrupt，图保存暂停点。
3. 项目将 interrupt_id 和问题写入 AgentAction，并将 Run 记为 waiting_input。
4. 回答先由 API 持久化，然后重新入队。
5. 新 worker 重新打开官方 SqliteSaver，用持久回答构建 Command(resume=...)，继续原图。

页面离开不影响这个链路。持久 SSE 和可操作界面仍属于 T06/T07，不能因为后端测试通过就说用户流程已完成。

## 业务工具为什么不接收 user_id

[tools.py](../../backend/agent_runtime/tools.py) 的工具闭包绑定 run_id 与执行代次。用户、岗位、简历都从已鉴权 Run 得出，模型无法替换身份或把任意岗位 ID 当成工具参数。

- `get_application_context`：读取任务资料、输入版本与本人已确认事实。
- `ask_applicant`：缺少真实经历时暂停补问。
- `create_resume_draft`：保存一个待审阅草稿，返回版本 ID。

当前事实引用验证确保 ID 属于本人、已确认、未删除；它不等于语义真实性证明。空事实列表仍可基于原简历起草。逐项修改理由、内容级依据检查与确认后的不可变版本属于 T08/T09/T10。

## 为什么操作键不能用 tool_call_id

一次工具调用可能在 SQL 提交后、checkpoint 保存前崩溃。重放时模型或 SDK 的调用标识可能不同，但用户仍只要“一份初始草稿”。

因此键为 `draft:{jd_id}:initial`，并与 run_id 组成唯一约束。ResumeVersion 与成功 ToolOperation 同事务提交；重放读到成功记录时返回同一版本 ID，不用新的输出覆盖已经提交的草稿。

同一 Run 内的重放复用产物；用户明确发起新的 Run 才能创建另一份初始草稿。这种操作键来自业务含义，不是内容哈希。

## 为什么同一会话的新任务要清状态

只删除消息是不够的。Deep Agents 还可能保留临时文件、待办和摘要事件。实测新 Run 会读到旧文件；旧摘要也会改变实际送入模型的内容。

本次修复在新 Run 开始前清除这些任务私有状态，保留 thread_id；同一个 Run 恢复则保留原状态。摘要字段属于当前锁定 SDK 的内部状态契约，已有回归覆盖，升级 SDK 时必须复验此边界。T12 再处理跨任务、经用户确认的业务记忆，不能默认把整个旧工作区当成长期记忆。

## 测试代表什么

[test_agent_runtime.py](../../backend/tests/test_agent_runtime.py) 使用真实 Deep Agents、真实 SQL 和磁盘 checkpoint；仅模型选择工具的部分可控。覆盖正常生成、补问重开、工具失败、重复工具、新任务状态隔离、有限重试及取消冲突。

[test_tool_idempotency.py](../../backend/tests/test_tool_idempotency.py) 直接验证实际数据库产物和操作记录，覆盖重放、无效引用回滚、旧执行代次与取消后禁止写入。

这证明业务协议与恢复行为可重复验证，不证明模型会始终选择正确工具或不会编造经历。后续真实模型 smoke 与 T13 live 评测必须单独记录模型、案例、成本和未通过项。

## 学习练习

1. 分别解释 Run、checkpoint、ToolOperation 保存了什么，以及各自不能替代谁。
2. 在测试里开启 `repeat=True`，跟踪两次调用为何只产生一份 ResumeVersion。
3. 解释为什么“用户回答已经保存”与“resume 消息已发出”不是同一个原子操作，以及扫描器如何补偿。
4. 对照回归测试说明 `autoflush=False` 和 MySQL 可重复读快照如何影响测试可信度。
