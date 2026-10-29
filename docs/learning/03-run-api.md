# 第三课：让任务 API 在重复请求与并发下保持一致

## 用户操作怎样变成数据库事务

[路由](../../backend/routes/agent_runs.py) 负责身份、请求校验和 HTTP 响应；[业务服务](../../backend/services/agent_runs.py) 负责归属、状态判断和事务。未来页面按钮与 Agent 工具调用都应复用服务，不各自复制一套写数据库逻辑。

本次新增接口：

| 操作 | 接口 | 当前效果 |
| --- | --- | --- |
| 创建 | POST /api/agent/runs | 保存 Run、输入版本和 Session 占用，返回 202 |
| 快照 | GET /api/agent/runs/{id} | 返回状态、输入引用、待处理动作和产物引用 |
| 取消 | POST /api/agent/runs/{id}/cancel | 未执行任务取消，执行中任务只记录取消请求 |
| 重试 | POST /api/agent/runs/{id}/retry | 失败任务在输入未变化时重新排队 |
| 回答 | POST /api/agent/runs/{id}/actions/{actionId} | 一次性保存补问/审批答案并重新排队，拒绝审批则取消 |

还没有接入 worker，所以 queued 表示数据库已接受，不表示正在生成。没有新增任务页面或 SSE；它们按计划分别在后续单元完成。

## 为什么 202 不等于“完成”

HTTP 请求的生命周期通常很短，LLM 调用可能很长。202 表示请求已被接受，结果稍后获取。当前 API 在事务成功后才返回 Run ID。下一单元增加队列通知，但即使通知失败，数据库也应保留已经接受的任务。

```json
{"kind":"tailoring","jdId":1,"resumeId":1,"requestId":"prepare-application-001"}
```

实际请求需携带自己的 Bearer token，且简历/岗位属于当前账号。这里只展示请求体，避免在笔记中保存真实凭证。

## 重复请求怎样返回同一项工作

1. 先按当前用户和 requestId 查询。
2. 已存在且语义相同，返回原 Run；同键换成别的参数，409。
3. 不存在则创建 Session/Run，并条件占用 Session。
4. 如果另一个请求抢先提交了同键，唯一约束拒绝写入；回滚本事务（包括多余 Session），重新读取原 Run。

查询已有记录只是快速路径，真正防止并发重复的是数据库唯一约束。测试让四个线程同时提交相同请求，最终只有一个 Run 和一个 Session。

同一会话的占用采用：

```sql
UPDATE agent_sessions SET active_run_id = :run_id
WHERE id = :session_id AND user_id = :user_id AND active_run_id IS NULL;
```

影响一行说明占用成功；零行表示会话正忙。新 Run 与占用同事务，失败时一起回滚。测试两个不同请求同时竞争同一空闲会话，结果一项 202、一项 409，没有留下幽灵 Run。

## 身份不来自请求体

user_id 从真实 JWT 认证结果取得。请求体多出的 user_id 被 422 拒绝；即使用户知道别人 Run ID、Session ID 或 Resume ID，也不能借用。查询使用资源 ID 与当前用户联合过滤，统一返回 404，避免暴露别人是否有这个资源。

测试没有绕过 get_current_user，而是生成仅供测试用户使用的 JWT，替换数据库连接。这样测试覆盖了实际 token 解码、查用户和业务归属链路。

新接口的错误体为 `{code,message,requestId}`。RunRoute 将该格式限定在新 Run 路由，包括认证和参数错误，不改动现有接口的错误格式。requestId 是错误关联编号，不是用户用于幂等的请求键。

## 取消与重试的真实含义

取消 queued/waiting 任务可以立即停止并释放 Session；取消 running 只设置 cancel_requested_at，因为 HTTP 服务不能声称远程模型调用已经停止。成功、失败、已取消终态不会被取消接口改写。

重试只允许 failed：使用原输入引用，比较简历/JD 的 updated_at 快照，未改变时 attempt 加一；资料改变或被删除时返回 input_changed，引导新建任务。它不声称能撤销已发生的模型费用。

## 本次发现并修复的并发问题

SQLite 不实现 SELECT FOR UPDATE。两个标签页可能这样交错：

```text
A 读取 waiting_input
B 取消任务，提交 cancelled
A 保存补充回答，并把旧的 Run 对象写成 queued
```

第三步会把已取消任务“复活”。单线程测试发现不了这个问题。本次用真实 SQLite 和另一数据库会话在读写之间提交取消，先观察到 202 的错误结果，再改成条件更新：只有数据库当前仍是对应 waiting 状态才能排队。失败返回 409，并回滚刚写入的回答。测试最终验证 cancelled 保留。

因此，事务不等于没有竞态；需要知道数据库隔离级别与锁的具体效果。MySQL 的同类测试中还遇到测试会话仍读到旧快照的问题：expire ORM 对象不会结束 REPEATABLE READ 事务，必须结束旧读事务后才能查询另一请求刚提交的数据。

## 补问与审批

同一动作只接受一次答案：相同答案重复提交复用原 Run，不同答案返回冲突。input 只接受 submit 且需有答案；approval 接受 approve/reject。拒绝审批会取消并释放会话。

目前每个动作是 checkpoint 发出的不可变问题，revision 固定为 1；更改问题应产生新动作，不支持原地编辑问题。expectedRevision 不为 1 时返回 409。以后如果引入可编辑审批单，需要再设计真正的修订流程，当前不提前建设。

回答接口只保存数据并排队。把答案传入 LangGraph Command(resume=...) 是后续运行器的责任，当前没有伪造模型结果。

## 练习

1. 对同一个 requestId 重发两次，再修改 resumeId 重发，比较“相同请求重放”与“同键不同请求”。
2. 读取消测试：为什么 running 状态必须保留，cancelRequested 却变成 true？
3. 去掉回答接口的状态条件更新，在临时库运行交错测试，观察 cancelled 如何被覆盖。
4. 给用户 B 一个用户 A 的 runId，验证读取、取消、重试和回答均被拒绝。
5. 解释为什么重试后 attempt 加一，而 requestId 与输入快照不换新。
