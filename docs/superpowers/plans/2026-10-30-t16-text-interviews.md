# T16 多轮文字模拟面试 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. 用户已授权自主推进；由根代理分配实施，本计划本身不启动实现或提交。

**Goal:** 用户从已经关联投递材料的申请记录开始最多八轮文字面试练习，安全地重发回答、恢复当前轮，并在明确确认后保存练习反馈为业务记忆。

**Architecture:** SQL 保存面试、每轮材料、命令与事件；`interview_generation` 进入现有 Celery 单 worker 的 `execute_run` 派发，使用独立执行函数和真实 Deep Agents 图，不增加进程、队列或自写 Agent 循环。每个生成 Run 只产出本轮反馈及下一问题，SQL 决定轮数与提交权；HTTP 接口使用统一命令处理服务；用户已取消 T21，不再接 WebSocket。

**Tech Stack:** 现有 FastAPI/Pydantic、SQLAlchemy（SQLite 与 MySQL）、Celery/Redis、Deep Agents/LangGraph/SQLite checkpointer、Vue 3/Pinia、pytest/Vitest/Playwright。

**Spec:** [总计划 T16](2026-10-29-ai-fullstack-agent-development.md)、[T20 已有 SQL 事件与 Redis 通知合同](2026-10-30-t20-redis-cross-process.md)。本文细化 T16；2026-10-30 用户取消 T21，保留 HTTP 命令和快照方案。

## 全局边界

- 只实现从已关联投递材料的 Application 启动，不增加另一路岗位/版本选择器。不修改投递状态或声称练习反馈是真实面试结果。
- 最多八个问题，每题一条不可变的已接受回答。第一轮前 `expectedTurn=0`，正式问题使用 `1..8`；用户可以提前结束。
- 继续使用米棕色 `card`、`button`、`form-field` 体系。桌面历史/当前轮双列，390/320px 单列；不自动投递。
- 所有模型调用在 worker 中、数据库写事务之外；主调用、框架摘要及框架重试前均执行取消/epoch/记忆失效检查。
- 使用现有唯一约束、事务和字段比较。不增加 hash、通用任务平台、兼容层、开关或第二套调度。最大三次暂时失败重试继续遵循现有 Run 合同；不声称模型调用 exactly-once。
- 本轮实现、定向测试与浏览器使用合成资料、受控模型响应，不增加付费调用。此前 3 元 live 账本已停止，不能借面试评测重置预算。
- 每个子单元先说明要检测的实际失败，保存 RED/GREEN 原始输出；稳定后根代理统一跑必要集成检查、真实浏览器并提交。不要每位实施者重复全套。

## 已经具备与真实缺口

| 已有代码 | 正确且可以复用 | T16 必须补齐 |
|---|---|---|
| `db/career_models.py` 的 InterviewSession/Turn/Command/Event | 会话归属、每轮唯一、命令 ID 唯一、事件 seq 唯一 | 冻结输入、AgentSession 关联、问题引用、命令原请求及不可变 ack |
| `services/applications.py::attach_submission` | 只关联本人确认版本，提交快照只写一次 | 快照有简历正文/引用/版本号，**没有岗位正文**；面试开始时另冻结当前岗位，明确采集时点 |
| `services/agent_runs.py`、`worker_tasks.py` | SQL 接受、worker claim/epoch、取消、恢复、唯一执行槽 | 新 kind 输入与派发；当前 create/cancel/finish 内部 commit，需最小拆出不提交的事务核心 |
| `agent_runtime/factory.py`、`context_middleware.py` | 真实 Deep Agents、必保留业务上下文、摘要守卫、checkpoint、usage | 面试专用上下文、结构化输出与执行函数；不能调用 tailoring 的完成路径 |
| `services/interview_events.py`、`realtime_bus.py` | 按本人 SQL 分页读取事件；Redis 仅发送 interviewId/lastSeq | 在面试事务内追加 seq，提交成功后通知；通知失败不撤销 SQL 命令 |
| `services/memory.py` | 明确确认、删除后取消/失效相关图会话 | 目前只识别 tailoring；加入实际使用记忆的面试 Run，增加来源绑定的反馈确认 |
| 旧 `agent/interview_tools.py::mock_interview` | 旧接口已有的一次性问答能力 | 不具备投递快照、八轮、HTTP 命令事务，不能当作 T16 实现或权威数据源 |

现有 Interview 表是骨架，T20 的事件测试也会创建会话。增加字段采用现有 SQLite additive schema 与编号 SQL 脚本；不凭空回填不存在的历史快照。旧骨架会话允许新列为空，真正的 T16 创建必须写全；遇到缺少冻结材料的旧骨架返回 `interview_context_missing`，不自动拼最新简历冒充历史材料。

## 固定数据与业务合同

### 最小持久化增量

修改 `backend/db/career_models.py`，增加以下五列；保留已有表与约束：

```python
# InterviewSession：新会话均写入；nullable 仅用于已经存在的骨架行。
agent_session_id: str | None  # FK agent_sessions.id，索引
source_snapshot: dict | None  # immutable, JSON
# InterviewTurn
question_context: dict | None # {mode, refs}，与 question 同事务
# InterviewCommand
request_json: dict | None     # 完整规范化命令，包含 type/expectedTurn/payload
ack_json: dict | None         # 接受时的原 ack；以后不改成“完成结果”
```

`source_snapshot` 保存 `applicationId`、`resumeVersionId`、`revision`、`submittedAt`、投递时的 `structuredContent`/`factRefs`，以及 `{jdId,title,company,rawText,structuredData,capturedAt}` 岗位快照（从现有 raw_text/structured_data 读取）。简历使用 Application 的 `submitted_snapshot`，不重新读取最新主简历或重投影 ProfileFact。岗位的 `capturedAt` 是**开始此次练习时**，不是投递时。开始时校验本人 Application、已关联快照、本人确认版本和本人岗位；缺少材料返回明确 404/409。开始后修改/删除原简历、岗位或申请，不替换/破坏冻结内容；现有版本删除限制不在此新增解除。

不额外增加 current_turn/last_seq/status 副本：当前轮取最后一条 Turn，seq 在写锁住 InterviewSession 后，对事件尾行作 current locking read 再加一，生成状态读取关联 AgentSession/Run。Session 仍只有 `active|finished`。反馈中的服务端 `memoryId` 为确认记忆幂等关联，不由模型输出。

### HTTP 命令类型

新增 `backend/schemas/interviews.py`；全部 `extra='forbid'`，使用 discriminated union 校验每个 payload。ID 长度沿用命令 1..100；回答去除首尾空白后 1..4000 字。错误继续使用已有 `code/message/requestId` 响应形状。

```ts
type InterviewCreate = { requestId: string; applicationId: number };
type InterviewCommand =
  | { clientMessageId: string; type: 'answer.submit'; expectedTurn: number;
      payload: { text: string } }
  | { clientMessageId: string; type: 'generation.cancel'; expectedTurn: number;
      payload: { runId: string } }
  | { clientMessageId: string; type: 'generation.retry'; expectedTurn: number;
      payload: { runId: string } }
  | { clientMessageId: string; type: 'session.finish'; expectedTurn: number;
      payload: Record<string, never> };
type InterviewAck = {
  interviewId: string; clientMessageId: string; status: 'accepted';
  resultRef: string | null; acceptedSeq: number;
};
```

| 接口 | 返回与作用 |
|---|---|
| `POST /api/interviews` | 202 `{interviewId,runId}`；同用户 requestId+applicationId 重放返回原创建结果，不再次冻结或生成 |
| `GET /api/interviews/{id}` | 本人 SQL snapshot：材料版本/岗位采集时点、status、turns、currentTurn、generation（当前/最近 Run）、lastSeq、sessionInvalidated |
| `POST /api/interviews/{id}/commands` | 202 原始 InterviewAck；HTTP 调用 `handle_command(db,user_id,interview_id,command)` |
| `GET /api/interviews/{id}/events?after=0&limit=100` | 复用 `read_interview_events`，after≥0，limit 1..100，返回按 seq 排序持久事件 |
| `POST /api/interviews/{id}/turns/{turn_index}/memory` | `{confirmed:true}`，显示并保存该轮服务端 `practiceFocus`，返回现有 Memory 序列化结构 |

所有接口校验本人；不存在和非本人统一 404。读快照/取消/结束不受生成限流。创建、answer、retry 仅在确认为新生成命令后调用现有 Run 接受限流；已经接受的精确重放不消耗新生成额度。浏览器只关闭订阅，不自动发送 session.finish。

### 命令、重放与轮数

`handle_command` 对会新增 Run 的命令先取得 memory gate，再用父 InterviewSession 的 no-op UPDATE 取得两种数据库都生效的写锁，并作 populate_existing 的当前锁读，然后查询 `(interview_id, client_message_id)`。存在时先逐字段比较规范化 `request_json`：完全相同直接返回旧 `ack_json`，即使面试后来结束、轮数已改变；不同返回 `command_payload_conflict`。不能先做当前轮检查而误拒绝丢失 ack 的重放。

- `answer.submit`：当前轮匹配，问题存在且未回答，面试 active、无活动生成。一次事务写回答、Command、下一生成 Run、`answer.accepted`。不同 ID 再答同题返回 `answer_already_submitted`。不可修改已经接受的文本。
- `generation.cancel`：runId 必须是该会话当前生成，expectedTurn 匹配；只请求取消生成，不关闭面试。运行中显示“正在停止”，不能宣称 HTTP 返回时模型已经停止。排队中的 Run 可直接取消；接受回答保留。
- `generation.retry`：指定当前最近的 failed/cancelled 生成 Run，且旧 Run 已终态、会话仍 active。新建 Run；保留旧 Run、回答和 ack，不重新接受回答。第一问取消后也可重试。运行中的停止请求不能马上开始第二个生成。
- `session.finish`：当前轮匹配，标记 finished，并同事务取消活动生成；不另调用模型做总结。精确重放返回原 ack。
- 第一生成创建问题 1；回答 1..7 生成对应反馈并由 Agent 选择 follow_up/new_topic 创建下一问题；回答 8 只产生反馈，写 session.finished，绝不创建问题 9。用户提前结束后不再生成。

ack 只表示已经接受，不因 worker 成功/失败改写。`InterviewCommand.status` 如需反映完成，可以更新该列但不能改 ack。生成状态/错误从 Run 与 snapshot 读取。

持久事件采用 `answer.accepted/question.completed/feedback.ready/generation.cancelled/session.finished`。`generation.cancelled` 只在真正取消时写，queued 取消在命令事务内写；正常 worker 的取消收尾使用面试锁序写。通用 stale recovery/记忆删除可能直接终止 Run 且没有面试 handler，因此 T16 从关联 Run 派生真实终态，不把缺少面试事件误当还在生成。不能在持 Run 锁的通用恢复分支反向取得 InterviewSession。原先为T21规划的终态事件补投影和question.delta随T21取消，不加入当前HTTP快照方案；页面依据SQL snapshot和Run状态恢复。

### 事务与执行函数

新增 `backend/services/interviews.py`（创建/读取/确认记忆/事件辅助）、`backend/services/interview_commands.py`（唯一业务命令服务）。从 `agent_runs.py` 提取明确命名的 flush-only 核心 `create_run_in_transaction`、`cancel_run_in_transaction`；已有对外函数继续拥有自己的 commit/rollback，不新增 commit=False 兼容开关。这两个事务核心不私自 rollback 调用者。worker 成功写入沿用同事务 guard→业务写→finish_run 最后提交；finish_run 自己不是 guard，不能先写反馈后才靠它决定取消。它返回 None 也不能当作成功证据。

```python
def create_interview(db, user_id: int, request: InterviewCreate) -> dict: ...
def get_owned_interview(db, user_id: int, interview_id: str, *, lock=False): ...
def interview_snapshot(db, user_id: int, interview_id: str) -> dict: ...
def handle_command(db, user_id: int, interview_id: str,
                   command: InterviewCommand) -> InterviewAck: ...
def append_interview_event(db, interview_id: str, event_type: str,
                           payload: dict) -> int: ...  # 要求调用者已锁 Session

def run_interview_generation(run_id: str, epoch: int) -> None: ...
```

创建的 requestId 沿用 `AgentRun(user_id,request_id)` 唯一约束：先找已存在的 interview 初始 Run，比较其冻结 source selection 中的 applicationId；一致返回原 interviewId/runId。否则在同一事务创建 InterviewSession、关联 AgentSession 和首个 Run。唯一冲突后回滚整笔事务再读原结果，不能遗留孤儿 InterviewSession。

每个 Run typed input 为 `kind='interview_generation'`、`interviewId`、`expectedTurn`、`sessionId`、`requestId`；worker 从冻结 Session 与已接受 SQL Turn 构造实际输入。Run 的 input_versions 捕获本次可用确认记忆 ID；不把删除后必须失效的记忆正文放进永久 source_snapshot。通用 `/api/agent/runs` 的 create/retry/cancel 对 interview kind 返回 `interview_command_required`，避免绕过 Command/Event 事务；也禁止其他 kind 借用面试所属 AgentSession（现有代码只查归属），只限制这一实际领域边界。GET/SSE 仍可读。命令新 Run 的 requestId 直接使用新 UUID，并把 runId 存入 ack；不拼接可能已长达 100 字符的 clientMessageId。自动暂时失败重试和 stale recovery 仍使用原调度。

成功生成只提交一次：冻结材料/轮次校验 → 所有实际模型调用 → 新短事务重新读取 Session/Run → 取消、epoch、active_run_id、expectedTurn 校验 → 保存反馈与下一问题、`ToolOperation(operation_key='interview:step')`、面试事件、不可变 Run.result_json、Run 终态 → 一次 commit。业务写入失败时这些内容全部回滚。后续 Redis hint 或队列发布失败不撤销已接受 SQL；现有恢复扫描发现待执行 Run。

统一锁序为 **memory rows → InterviewSession → Run → AgentSession**；不涉及 memory 时省略第一项，禁止取得 Session/Run 锁后再捕获 memory。现有记忆删除保持 memory→Run→AgentSession，不反向锁 InterviewSession；Run invalidation/cancel fence 撤销在飞行结果。父 Session 使用 no-op UPDATE 获取写锁；Command、目标 Turn、事件尾行使用 current locking read 和必要的 populate_existing，避免 MySQL 认证查询已打开旧 RR 快照的问题。回答写入还要求 answer IS NULL 谓词。模型调用/checkpoint I/O 不在 SQL 写锁内。取消/结束先提交时，迟到输出不写任何业务结果；worker 先完成则取消不能改写成功。独立审查见 `/tmp/task-16-transaction-review.md`；实施时用 MySQL 两连接屏障和先开旧快照测试验证这些可达路径。

## 生成输出、引用与记忆

在 `factory.py` 保持唯一 Deep Agents 构造入口，增加 `build_interview_agent(...)`；新增 `agent_runtime/interviews.py` 作为执行函数，`agent_runtime/interview_context.py` 构造冻结材料/SQL 历史，技能文件 `skills/interview-prep/SKILL.md`。用已安装 SDK 的 `response_format=InterviewStep` 取结构化结果，校验后由业务服务原子落库。不要让模型直接调用写回答/写记忆/结束会话工具。继续禁用 execute/task/subagent，不给面试图加入生产写工具。

```python
class InterviewStep(BaseModel):
    feedback: InterviewFeedback | None
    question: InterviewQuestion | None

# InterviewQuestion: text(1..2000), mode(opening/follow_up/new_topic), refs(max 12)
# InterviewFeedback: summary(1..2000), strengths/improvements(各最多5项),
#                    practiceFocus(1..4000), 每个评价项含 text + refs(max 12)
# Ref 输入只允许 resume(section,quote)、job(quote)、answer(turnIndex,quote)。
```

服务端从冻结材料/已接受回答验证引用的 section/quote 确实存在，再绑定服务端 versionId/revision/turnId，不接受模型任意造 ID。岗位引用说明要求，不证明候选人做过；模拟回答只可用于练习分析，不能晋升为 ProfileFact。问题 1 允许引用岗位与简历；后续追问须能指向前一已接受回答中的具体缺口。缺引用、错 section/quote/turn 的结构化输出使当前 Run 失败，不能静默删引用后宣称通过。引用存在只是机械可验证条件，不证明文字推断正确；eval 仍需审阅反馈是否受引用支持，不能把 stub 的固定好答案算作真实模型语义通过。

每次上下文由冻结 snapshot、最多八轮 SQL 历史、本次允许的已确认 memory 构成。较大材料放现有 StateBackend 文件和分页只读工具，复用现有预算估算；必保留区保留来源版本/轮数/当前回答/约束。面试版 `BusinessContextMiddleware` 只覆盖上下文读取入口，保留现有摘要、重试守卫与预算逻辑。相同 Run 崩溃恢复读同一 checkpoint；新 Run 明确换入当前 SQL 输入并重置上轮临时图状态，不能依赖聊天历史猜哪条回答已提交。

反馈确认接口先校验本人会话与实际已落库 feedback，要求 StrictBool true，取服务端 practiceFocus 作为 memory 内容，source_ref 写 `{kind:'interview_turn',interviewId,turnId}`；UI 先展示这段内容，再让用户确认。先取得 memory gate，再在 Session 锁内检查/写 feedback.memoryId，重复确认返回同一活动记忆；该记忆已删除则返回 `memory_deleted`，不静默复活。手工 MemoryCreate 原合同不变。扩展 `memories_for_run/list_memories/delete_memory`、Run 的失效检查、worker checkpoint 清理，对 interview_generation 实施现有删除语义；删除被使用的记忆后原图会话失效，必须新建练习，不能从旧 checkpoint 恢复已删除内容。任何确认/练习路径不新增 ProfileFact。

## 实施单元与定向验证

### 单元 A：持久输入、共享命令与原子接受

**Files:** 新增 `backend/schemas/interviews.py`、`backend/services/interviews.py`、`backend/services/interview_commands.py`、`backend/routes/interviews.py`、`backend/tests/test_interviews.py`、`deploy/schema/005_text_interviews.sql`；修改 `backend/db/career_models.py`、`backend/db/database.py`、`backend/schemas/agent_runs.py`、`backend/services/agent_runs.py`、`backend/routes/agent_runs.py`、`backend/routes/api.py`、`deploy/schema/README.md`。

**Interfaces:** 提供上文 HTTP/函数/ack；`RunCreate` 精确新增 interview 字段，其他 kind 不接受它们；事务函数只 flush；单元 B 只通过这些函数落库。

- [x] RED：写创建快照和请求重放；本人/草稿/未提交/缺失岗位拒绝；源改动后原 snapshot 不变；旧 kind 字段组合仍拒绝。
- [x] RED：先写以下实际回滚和 lost-ack 测试，使用真实 `career_db`，只让队列发布变成可观察的 stub。

```python
def test_lost_ack_replays_one_answer_and_one_run(career_db, interview_factory):
    interview = interview_factory(question='如何保证事务一致？')
    command = answer_command('m-1', turn=1, text='使用单个数据库事务')
    first = handle_command(career_db, 1, interview.id, command)
    second = handle_command(career_db, 1, interview.id, command)
    assert second == first
    assert accepted_answer_count(career_db, interview.id, 1) == 1
    assert command_run_count(career_db, interview.id, 'm-1') == 1

# 同 ID 不同正文 -> 409；不同 ID 再答同题 -> 409；写 Run/事件前抛错 ->
# answer、InterviewCommand、AgentRun、InterviewEvent 均不增加。
```

- [x] GREEN：完成五列与现有部署方式的增量、创建/读取/命令、flush-only Run 核心；将 interview 通用 Run 写入口封回共享服务。
- [x] GREEN：queued/running cancel、finish、retry、旧轮提交、取消第一问、回答 8 的接受合同；精确重放在状态变化后仍返回原 ack。补 MySQL 已打开 RR 快照的两连接竞争、其他 kind 不能占用面试 AgentSession、发布失败后 SQL queued 可被既有扫描补发。
- [x] 定向双库：`RESUMATE_TEST_MYSQL_SOCKET=/tmp/resumate-mysql-t02/mysql.sock .venv/bin/python -m pytest backend/tests/test_interviews.py backend/tests/test_worker_delivery.py -q`。覆盖故障为孤儿会话/半条回答/重复 Run/误派发；出现失败先定位事务，不用新增重试装饰器掩盖。

测试 helper 在 `backend/tests/interview_fixtures.py` 提供真实行种子、查询计数与可控模型响应，不提供复刻业务判断的 fake repository。现有 career_db fixture 已支持 SQLite/MySQL；不能另建“看起来像 MySQL”的引擎。

### 单元 B：真实图执行、八轮与迟到结果

**Files:** 新增 `backend/agent_runtime/interviews.py`、`backend/agent_runtime/interview_context.py`、`backend/agent_runtime/skills/interview-prep/SKILL.md`、`backend/tests/test_interview_runtime.py`；修改 `backend/agent_runtime/factory.py`、`backend/worker_tasks.py`、按需 `backend/agent_runtime/context_middleware.py`。

**Interfaces:** `run_interview_generation(run_id,epoch)` 被现有 execute_run 调用；接受 A 的冻结 snapshot/expectedTurn；输出 typed InterviewStep；使用 A 的事务核心。两个实施者先冻结公共函数，不同时编辑 agent_runs.py。

- [x] RED：真实 create→claim→handler→SQL，一次首问、两次 follow_up、一次 new_topic；断言完整问题/答案/反馈/引用，不仅断言模型被调用。
- [x] RED：第八回答之后 feedback 存在、Session finished、Turn count=8，即使模型返回第九题也拒绝写入；错误结构/无效引用不产生业务结果。
- [x] RED：用 barrier 暂停模型返回，另连接取消或结束；释放模型后业务结果/成功事件为零。另测 epoch 改变、重复 handler、事务中间异常和同 Run checkpoint 恢复。

```python
assert after.turn_count == before.turn_count
assert after.feedback_count == before.feedback_count
assert after.completed_events == before.completed_events
assert stopped_run.result_json is None
# 取消不删除已接受 answer；generation.retry 新 Run 只生成一次合法结果。
```

- [x] GREEN：只新增独立执行函数与派发分支；沿用 worker 单槽、心跳/恢复、checkpointer/telemetry。摘要和框架重试也通过 fresh SQL guard；未配置模型/超出预算使用已有明确错误。
- [x] GREEN：成功写入 feedback/下一题/operation/events/Run result/terminal 一个事务；正常 running 取消按面试锁序收尾；覆盖 stale recovery 耗尽/排队取消后快照正确派生终态和重试资格，不依赖旧 worker 一定回来，也不在通用恢复反向锁面试。
- [x] 定向：`.venv/bin/python -m pytest backend/tests/test_interview_runtime.py backend/tests/test_agent_context.py backend/tests/test_worker_delivery.py -q`，并用现有 MySQL fixture 跑取消/回滚测试。若恢复结果重复，修持久化边界，不假定模型不重跑。

### 单元 C：确认反馈记忆与删除传播

**Files:** 修改 `backend/services/memory.py`、`backend/services/interviews.py`、`backend/services/agent_runs.py`、`backend/worker_tasks.py`、`frontend/src/types/memory.ts`；新增 `backend/tests/test_interview_memory.py`，必要时扩展现有 `backend/tests/test_agent_memory.py`。

**Interfaces:** memory sourceRef 新增 interview_turn 分支；现有手工接口不改。返回 Memory 继续由现有序列化函数负责。

- [x] RED：无确认/false/他人会话/未生成反馈拒绝；确认后 sourceRef 精确绑定真实 turn，重复只一行；前后 ProfileFact count 相同。
- [x] RED：确认后的下一 Run 可用记忆；删除后下一次主模型/摘要调用前拦截，运行中迟到输出不写，checkpoint 清理状态真实可见；再次确认不恢复已删行。
- [x] GREEN：仅增加面试实际需要的 kind 判断与来源绑定保存；不冻结已删 memory 正文、不建立另一个记忆管理器。
- [x] 双库定向：`RESUMATE_TEST_MYSQL_SOCKET=/tmp/resumate-mysql-t02/mysql.sock .venv/bin/python -m pytest backend/tests/test_interview_memory.py backend/tests/test_agent_memory.py -q`。失败意味着业务记忆删除后仍被用到，应修实际 Run/会话关联和守卫。

### 单元 D：面试页面与 HTTP 恢复

**Files:** 新增 `frontend/src/types/interview.ts`、`frontend/src/api/interviews.ts`、`frontend/src/views/InterviewView.vue`、`frontend/src/views/InterviewView.spec.ts`；修改 `frontend/src/views/ApplicationsView.vue`、`frontend/src/views/ApplicationsView.spec.ts`、`frontend/src/router/index.ts`。

**Interfaces:** 只消费固定 HTTP 合同。导航 `/interviews/:id`；Application 已关联材料卡显示“模拟面试”，同时标明投递版本/岗位取材时点。

- [x] RED：模拟丢失 ack 后同 ID/同 payload 重发；编辑草稿不改变待重发命令；刷新取 SQL 当前轮；账号变化清理 draft/pending command/旧快照，旧响应不能写入新账号视图。
- [x] GREEN：回答草稿与冻结 pending command 分离；按 userId/interviewId/turn 存当前浏览器会话的草稿和待重发命令，接受后清理。重复点击禁止再造 clientMessageId；超时显示可重发，不能当作业务失败清空正文。
- [x] GREEN：显示生成中、正在停止、失败可重试、已结束、会话因记忆删除失效；取消/结束有清楚操作含义，结束不被关页触发。反馈区标“练习反馈”，引用可展开，记忆确认先展示确切内容。
- [x] GREEN：桌面左历史右当前轮，移动单列；长问题/引用/版本名换行，按钮不遮挡输入。空状态提供回到申请材料的入口。
- [x] 定向：`npm --prefix frontend run test:unit -- src/views/InterviewView.spec.ts src/views/ApplicationsView.spec.ts`；`npm --prefix frontend run build`（含vue-tsc类型检查）。这里发现的是交互/类型问题，不能替代真实图、SQL 或浏览器截图。

### 单元 E：六个真实持久服务评测

**Files:** 新增 `evals/cases/interviews.jsonl`、`evals/interview_runner.py`、`evals/interview_verifiers.py`、`backend/tests/test_interview_evals.py`；修改 `evals/run.py`、`evals/README.md`。复用具体合成模型响应和 SQL seed，不复用 pytest 的 pass 结果当 eval。

**Interfaces:** 继续现有 case result/record/预算格式。每案有独立 create/command/claim/handler/session，保存实际输入/输出、SQL oracle、verdict、model starts。原 24 案输入和纯 verifier 默认语义不改。

| 固定 ID | 真实轨迹与 oracle |
|---|---|
| `interview-followup` | 三题两次回答，至少两次追问；上下文含已接受回答，引用指向真实冻结内容 |
| `interview-eight-turn-limit` | 八题八答、最后反馈与 finished 同事务，无第九题 |
| `interview-command-replay` | 丢 ack/重放/不同正文冲突/刷新，回答与 Run 各一份、ack 不变 |
| `interview-cancel-late-result` | 模型 barrier 后 cancel，迟到无业务写入；retry 合法，再验证 finish 阻止迟到 |
| `interview-frozen-submission` | 修改源内容后仍用提交快照与面试开始岗位；他人/缺失来源拒绝 |
| `interview-feedback-memory` | 未确认零写、确认一份、删后不复活、ProfileFact 不变 |

- [x] RED：缺轨迹/SQL snapshot/未执行时不能判 pass；一案故意错 oracle 应 fail；不支持的 live 新案必须 not_run。
- [x] GREEN：只 stub 外部模型响应，走真实持久服务与图调用边界；输出可审阅的题目、反馈、引用和 SQL 变化。
- [x] 局部验证：`.venv/bin/python -m pytest backend/tests/test_interview_evals.py -q`；测试实际调用同一CLI入口并生成六案完整产物，不额外重复同一批。完整后端内包含30案目录及普通core的26执行/4未执行回归；四次新Compose证据在T19交付验收执行。
- [x] 总数为 30。普通 stub 无本轮真实 Compose 证据仍是 26 executed / 4 not_run，退出码 2；提供同一次 invocation 的四个真实恢复证据才可算 30 executed。不能借用上轮 crash 的 pass 冒充本轮，也不能把 stub 文案质量当真实模型评测。

### 单元 F：真实浏览器、教学与收口

**Files:** 新增 `tests/e2e/interview.spec.ts`、`docs/learning/16-text-interviews.md`、`docs/learning/test-records/2026-10-30-t16.md`；由根代理维护 `tests/e2e/support/server.py`/实际 worker fixture、教学导航与总计划。

- [x] 场景 1：真实登录→Application 已关联版本→开始→第一题→两次回答/两次追问→展开引用→刷新仍为 SQL 当前轮→用户结束。验证 browser reload 并未创建新面试/重复回答。
- [x] 场景 2：冻结源材料后修改原数据，页面仍显示原取材；长问题、长引用、空状态，桌面/390/320px。
- [x] 场景 3：模型 barrier 显示生成中→取消→迟到输出不出现→重试；失败与记忆失效状态有实际后端来源，不只切前端布尔值截图。
- [x] 场景 4：实际丢弃一次成功命令的 HTTP 响应再重发，刷新并查 SQL 一条答案/一个 Run；确认反馈写记忆前后真实 API 验证，账号切换清理。
- [x] 使用现有真实 API+worker+SQL 和隔离合成模型 transport，不 route.fulfill 整个 interview API，不只组件 mock。`.venv/bin/python` fixture 和 Playwright 环境由根代理统一启动；执行 `npm run test:e2e -- interview.spec.ts`。
- [x] 保存最终桌面、390、320px 问题/反馈引用/生成/失败/结束图，实际打开图片确认换行/滚动/按钮/米棕视觉。截图只证明看到的 UI；SQL 与原始日志分别证明去重和取消，不用截图替代事务证据。
- [x] 教学解释：ack 与结果分离、冻结投递事实与练习答案的区别、单事务/epoch防迟到、框架 checkpoint 与 SQL 当前轮各自职责、为什么确认后才进入记忆。保留红绿、实际浏览器发现、修复范围、未测边界与未发生的付费调用。

## 分工与交付

A 先冻结 schema/命令/Run 事务接口；B 接真实 Deep Agents 与执行函数；C 记忆可由 A/B 中一人顺序完成，避免共享文件冲突；根代理负责 UI/浏览器/最终检查，另一个空闲工作者可独占六案 eval。不要为本计划自动增开 agent。

每单元交付行为、变更文件、明确的失败与修复、执行命令/计数、原始日志和教学要点；不在局部通过时宣布 T16 完成。根代理在实施收口时同步主计划；T21已取消，不增加WS类型或接线。


## 收口（2026-10-30）

实现与确定性验收完成，证据见[测试记录](../../learning/test-records/2026-10-30-t16.md)。A/C双库93passed/3skip；图与边界37项在根完整后端通过；六案6/6实际执行、17定向测试通过；前端148全量后追加审查修复15定向通过；四个实际浏览器场景通过、审查后受影响两场景再通过；11张截图逐张查看并修复两处可见问题。完整后端首轮1076pass/2fail/17skip，旧遥测测试对象补kind后2失败定向通过，未宣称完整首轮全绿。最终生产包816.47kB作为T17基线。T21用户取消，后续T17/T18→T19；真实模型质量未验收。
