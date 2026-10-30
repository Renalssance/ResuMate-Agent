# T20 Redis 跨进程协作 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 在共享 MySQL、双 API、一个 worker 的真实环境中，使限流、一次性票据、统计缓存和面试事件提示跨进程一致。

**Architecture:** SQL 保存业务与持久事件；Redis 承担 Celery 投递、限流、短期票据、可丢弃缓存及唤醒提示。API 各自拥有连接池和本地订阅者，worker 仍只有一个执行槽与专属 checkpoint 卷。Redis 丢失提示不改变 SQL 事实，也不增加第二套任务状态机。

**Tech Stack:** FastAPI、SQLAlchemy/PyMySQL、MySQL 8.4、现有 Redis 7.4 镜像、redis-py（当前 lock 为 6.4.0）、Celery、Docker Compose、pytest/httpx。

**Spec:** [总计划 T20/T21](2026-10-29-ai-fullstack-agent-development.md#t20redis-应用工程与跨进程消息通知)，并保持 [T14 恢复合同](2026-10-30-t14-recovery-and-long-tasks.md) 的 SQL 受理、执行锁与恢复边界。

## Global Constraints

- T15 基线为 `a1568bc`；T20 实现及真实跨进程验收已完成。七场景 7 passed / 86.52s，旧 SQLite PDF 1 passed / 14.17s、两页已查看；完整首轮与定向修复分别记录，详见 [T20 测试记录](../../learning/test-records/2026-10-30-t20.md)。下一单元 T16。
- SQL 是状态、权限、命令与业务结果的权威；不引入 Redis Streams、MongoDB、通用事件平台、第二套 durable engine 或分布式锁替代现有 OS 执行锁。
- Redis 命令连接超时 1 秒、读取超时 2 秒；Pub/Sub 使用独立长连接超时策略，不复用命令连接。
- 票据 TTL 最多 30 秒；统计缓存 TTL 30 秒；环境名同时进入 key 和 channel。
- Redis 故障时：缓存回 SQL，通知靠 SQL 补查，票据及新任务受理限流返回 503；不得回退进程内计数。
- worker 并发仍为 1，恢复扫描仍为 15 秒，失联判定仍为 90 秒；checkpoint/OS 锁卷仅 worker 挂载。
- 不调用付费模型；集成使用合成数据与现有确定性 DraftModel/实际 checkpoint。T20 的通知测试不冒充尚未实施的 T21 WebSocket 验收。
- 不生成 hashes/checksums。证据以本次 invocation ID、原始输入、源码快照、容器/数据库版本、配置和实际结果关联。
- 每次检查前说明“具体捕获哪种失败、失败后改哪里”；先定向红绿，已通过检查仅在新改动/新失败影响时复测。此计划没有提交授权，交由根任务安排提交。

## 1. 实施前代码事实与缺口（保留起点）

| 位置 | 已正确的部分 | T20 实际需要改变的部分 |
|---|---|---|
| `deploy/compose.yaml` | API、worker、scheduler、Redis 已同处 Linux；单 worker | 目前单 API + 共享 SQLite，Redis 映射宿主端口，没有显式内存上限；不是双 API/MySQL 验收环境 |
| `backend/app.py` | HTTP 日志只记 method/path/client，不输出请求体；healthz 是存活检查 | 只有 startup init_db，没有 Redis 生命周期/退出关闭；两 API 首次启动不能竞争建表 |
| `backend/middleware/rate_limit.py` | 已有 auth 5/60 秒、chat 20/60 秒及 429/Retry-After | `FixedWindowLimiter` 是进程字典；不同 API 各算一份；Run 创建入口没有限制；身份解析重复解 JWT |
| `backend/auth/security.py` | 签名/过期校验后查 SQL User；角色来自数据库 | 返回 User 丢弃原 JWT exp，不能满足票据绑定原登录到期时间 |
| `backend/services/llm_settings.py` | usage 按 user_id 查询；调用记录先 SQL commit | `usage_dashboard` 每次 `.all()` 用户全部调用，Python 聚合，混合 recent_calls；无缓存或提交后失效 |
| `backend/services/run_delivery.py` / `agent_runs.py` | Run SQL 提交后 best-effort 发布；publish 失败保留 queued；scanner 恢复 | 保持这些语义；新增限流应在业务副作用前，不能把发布失败变成 SQL 回滚 |
| `backend/services/run_events.py` | SQL 分页、seq 游标、短 Session、500ms 补查和跨用户归属校验 | 现有 Run SSE 不需要替换成 Redis；它可作为通知丢失仍能恢复的已存在模式 |
| `backend/db/career_models.py` | 已有 InterviewSession/Turn/Event/Command；event seq 与 command ID 唯一约束 | 面试业务服务、路由与 WS 尚不存在；InterviewSession.id 实际是 UUID 字符串，不能沿用总计划示例的整数 10 |

现有前端 ApplicationsView/DocumentsView 的数字由列表计算；T20 不另造一个“面板平台”。真实缓存目标是 `GET /api/settings/usage`。其 `recent_calls` 包含模型名、错误和时间等详情，始终实时查 SQL，不把整个响应缓存。

## 2. 最小运行环境与卷合同

主 `deploy/compose.yaml` 升级为下表拓扑，供 T20/T21/T17/T19 使用。两个 API 是两个独立容器、各一个 Uvicorn worker；测试轮流直连两个 localhost 端口，暂不增加负载均衡器或 sticky session。

| 服务 | 数据/依赖 | 暴露与卷 |
|---|---|---|
| mysql | MySQL 8.4，utf8mb4，独立测试数据库；真实版本由 `SELECT VERSION()` 留证 | 仅内部网络；`mysql-data:/var/lib/mysql` |
| schema | 同应用镜像，执行一次 `python -c 'from backend.db.database import init_db; init_db()'`；等待 MySQL healthy | 无持久本地状态；完成后 API/worker 才启动 |
| api / api2 | 相同 DATABASE_URL、JWT_SECRET_KEY、REDIS_URL、RESUMATE_ENV；各一个 Uvicorn 进程 | 127.0.0.1 的两个不同端口；共享 `backend-data:/app/data`，无 checkpoint 卷 |
| worker | 同一个 MySQL、同 Redis broker；Celery concurrency=1；既有 fcntl 锁 | 共享 backend-data；独占 `agent-state:/app/agent-state`，AGENT_STATE_DIR 指向此路径 |
| scheduler | 只发送既有 15 秒 recover_runs 调度 | 无 SQL/checkpoint 卷；Redis URL 相同 |
| redis | 现有 Redis 7.4 镜像，AOF 保留；`maxmemory 256mb`、`maxmemory-policy noeviction`，容器内存留出余量（起始 512MiB） | 不映射主机端口；`redis-data:/data` |

`backend-data` 仍保存上传原件、产物与当前 Chroma 路径；统一设置 `CHROMA_PATH=/app/data/chroma`、`RESUME_EXPORT_DIR=/app/data/exports`。T20 不迁移检索存储，也不把合成数据下的 Redis 验收说成全部 RAG 并发验收。独占 agent-state 路径不得嵌套在 API 已挂载的共享目录内。

新环境是空数据库的本地 Compose，schema 一次建表不构成迁移框架；已有部署继续按 `deploy/schema/README.md` 的人工增量 SQL 顺序升级。启动依赖使用 `service_healthy` / `service_completed_successfully`。API 生命周期仍验证数据库可用；Redis 临时不可用不应使全部 SQL 查询服务无法启动。

**现有测试必须单独保留其真实 SQLite 边界：** `test_worker_compose.py`、`test_resume_export_compose.py`、`test_agent_recovery.py` 都引用当前 Compose 并在启动前 seed SQLite；直接更换主拓扑会让它们读错数据库。将当前 SQLite 配置移至 `backend/tests/fixtures/compose.sqlite.yaml`，仅供这三个明确的测试引用；调整其 build.context 为仓库根（相对路径 `../../..`）。这是已有故障实验夹具，不是生产双引擎兼容层。测试用 Redis loopback 端口只留在此夹具或显式测试 override；主环境不开放 Redis/MySQL。

`.env.example` 补齐 RESUMATE_ENV、两个 API 端口、Compose MySQL 凭据说明，保留 native DATABASE_URL 的说明；改掉“旧分析页面可不启动 worker”的过时注释。实际运行资料不记录明文 JWT、数据库密码或完整带密码 DATABASE_URL。

## 3. 共享接口与 Redis 数据合同

接口的 Redis client/env 在服务对象构造时注入，业务方法不自己创建 client。Redis 异常统一转为 `RedisUnavailable`，由调用方按下表决定 fail-closed 或降级，不捕获 SQL/业务异常伪装缓存失败。

```python
# backend/infrastructure/redis_client.py
class RedisUnavailable(RuntimeError):
    pass

# API lifespan 持有 AsyncRedisResources(commands, notifications)。
# commands: redis.asyncio.Redis；notifications: 独立 redis.asyncio.Redis。
# Celery 子进程及同步 usage recorder 使用同配置的进程级 redis.Redis。
# 所有对象在所属进程初始化，退出关闭；不得把 fork 前已有 socket 传给子进程。

# backend/middleware/rate_limit.py
class RedisRateLimiter:
    async def allow_request(self, user_id: int | str, scope: str) -> tuple[bool, int]: ...
    # user_id=int 用于已鉴权用户；auth 用固定格式 ip:<client_ip>，不靠可选 Bearer 改桶。

# backend/services/ws_tickets.py
@dataclass(frozen=True)
class WsTicketClaims:
    user_id: int
    interview_id: str
    auth_expires_at: datetime  # aware UTC；JSON 存 Unix seconds

class WsTickets:
    async def issue_ws_ticket(self, user_id: int, interview_id: str,
                              auth_expires_at: datetime) -> str: ...
    async def consume_ws_ticket(self, ticket: str) -> WsTicketClaims | None: ...

# backend/services/realtime_bus.py
class InterviewHints:
    async def publish_interview_hint(self, interview_id: str, last_seq: int) -> None: ...
    def watch(self, interview_id: str) -> AsyncContextManager[asyncio.Event]: ...

# 同步 worker 只有这两个 Redis 写操作；使用自己的进程级同步池。
def publish_interview_hint_sync(interview_id: str, last_seq: int) -> None: ...
def invalidate_usage_summary(user_id: int) -> None: ...

# backend/services/dashboard_cache.py
class DashboardCache:
    async def usage_dashboard(self, user_id: int, session_factory) -> LlmUsageDashboard: ...

# backend/services/interview_events.py：只读现有持久事件表，不生成面试状态。
def read_interview_events(session_factory, user_id: int, interview_id: str,
                          after_seq: int, limit: int = 100) -> list[dict]: ...
# 返回字段：interviewId, seq, type, payload；先查 InterviewSession.user_id。
```

上面的省略号是接口声明；各任务下列出实现算法。保持这些接口窄而明确，不引入泛型消息 Envelope、topic registry、transport adapter 或通用缓存装饰器。

| 用途 | Redis 名称 | 值与生命周期 |
|---|---|---|
| 限流 | `resumate:{env}:rl:{scope}:{subject}` | 整数；首次 hit 起 60 秒窗口，只首次设置 TTL |
| 票据 | `resumate:{env}:ws-ticket:{random}` | `{userId, interviewId, authExpiresAt}`；最多 30 秒，一次 GETDEL |
| 统计 | `resumate:{env}:stats:{user_id}` | 汇总数字、date/task 分组标签及 last_called_at；TTL 30 秒 |
| 提示频道 | `resumate:{env}:interview-hints` | `{interviewId, lastSeq}`；无正文、无认证、无业务结果；不持久化 |

命名中的 env 必须所有进程一致。不同 Redis DB 编号不能隔离 Pub/Sub 频道或内存淘汰策略。单一 Compose project 使用自己的 Redis；测试仍使用唯一 env，避免误消费其他集成用例。

### 3.1 生命周期和同步调用边界

API lifespan 创建命令池与 Pub/Sub 独立池，启动一个 InterviewHints reader task；退出先取消并 await reader，再关闭 PubSub、通知 client、命令 client。命令池设置 connect=1s/read=2s，显式不自动重试具有副作用的 INCR/GETDEL。Pub/Sub socket 不使用 2 秒空闲读取超时，以有界 get_message 等待让 reader 可取消；断线重新订阅，等待期间 SQL 补查继续工作。

实际 worker 是同步 Celery，`record_llm_usage` 也是同步函数。因此同步发布/失效使用一个进程级 `redis.Redis` 池，参数与命令池一致，在 API lifespan 或 Celery worker_process_init 创建、相应 shutdown 关闭。API 限流、票据和缓存读取继续使用 async 池；不为每次调用创建 asyncio.run/client，不把协程池从另一个 loop 或 fork 父进程拿来用。这是现有同步入口的边界，不新增调度平台。

容量告警复用已有 `recover_runs` 的扫描机会：读取 Redis INFO memory，若 `(used_memory - mem_not_counted_for_evict) / maxmemory >= 0.8`，记录一条结构化 WARNING（env、数值、上限）；OOM/连接失败也有不含凭据的告警。该读取失败不能阻断 SQL recovery。无需新增常驻监控服务；T19 再接运维告警出口。noeviction 会返回写入错误，而不会为缓存清掉队列键；这不是无限容量保证。

### 3.2 原子限流与实际受理入口

保留 auth 5/60、chat 20/60；新增 run 10/60 作为单执行槽环境的初始明确策略（不是性能实测结论）。auth/register 与 auth/login 共享 IP 桶；已登录 chat/run 用 SQL 确认后的数字 user_id。沿用当前受信任本地/代理的地址来源，代理信任范围由 T18/T19 收口，不在 T20 重写认证体系。

固定小脚本直接 EVAL，避免自行维护脚本缓存或重试平台：

```lua
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
local ttl = redis.call('PTTL', KEYS[1])
return {count, ttl}
```

`allowed = count <= limit`；允许时 retry_after=0，拒绝时 `max(1, ceil(ttl / 1000))`。此窗口从第一次请求开始，替代旧代码按墙钟整分钟切窗的行为；拒绝请求不延长 TTL。429 携带 Retry-After；RedisUnavailable 返回 503。不得异常后再 INCR 重试造成多次记账，也不得静默本地放行。

新增 async `require_run_capacity` FastAPI dependency；在函数执行/写文件前完成，认证复用 get_current_user。明确覆盖：

- `POST /api/agent/runs`，`POST /api/agent/runs/{run_id}/retry`。
- `POST /api/documents`、`POST /api/documents/{document_id}/parse`、`POST /api/jobs/{job_id}/parse`。
- `POST /api/runs`、`POST /api/runs/{run_id}/candidates/{candidate_id}/questions`。
- `POST /api/followups/analyze`、`POST /api/resume-versions/{version_id}/export`。

不限制 GET 快照/下载/SSE、取消、以及已受理 Run 的 action 回答；已有 action 回答必须仍能 SQL 提交并等待 Redis 恢复。T16 新面试生成 Run 在同一受理边界接入，不能绕开。每次 HTTP 受理尝试都计数，包含同 requestId 的重放；达到限额时返回 429，但已存在的 Run 不受影响且仍可 GET。这个选择免去为每种旧入口再造一份 dedupe 预检查；原 create_run 的 SQL 幂等行为保留。

RunRoute 维持 `{code,message,requestId}` 错误格式，增加 503→`dependency_unavailable`；旧路由继续既有 detail 格式。上传限流失败不得留下文件/Document/Run。Redis 在通过限流之后、publish 之前中断时，必须仍返回 SQL 已接受的结果，由扫描器补投。

### 3.3 票据与 T16/T21 的分界

`secrets.token_urlsafe(32)` 生成随机票据；SET EX 30，若原登录更早到期则缩短 TTL。GETDEL 返回内容后验证原 auth_expires_at 尚未到期，否则返回 None；missing/expired/replayed 都返回 None。连接/超时/OOM 抛 RedisUnavailable，不能当成“无票据”从而混淆 401 与 503。GETDEL 的响应若在网络中丢失，不重试恢复票据；客户端重新申请即可。

在 auth/security.py 增加从同一验证逻辑取得 `AuthContext(user, auth_expires_at)` 的依赖；exp 取自签名验证后的 JWT，禁止由请求参数输入；保留现有 get_current_user 给已有调用方。真实 create_access_token 已签发 exp。没有 exp 的测试 token 不能用于新的票据测试，测试应使用真实签发函数。

T20 可以完成 WsTickets 和真实 Redis 原子消费验收。生产 `POST /api/interviews/{interview_id}/ws-ticket` 在 T16 的 `backend/services/interviews.py::get_owned_interview(db, user_id: int, interview_id: str) -> InterviewSession` 存在后接入：先验证登录，再调用该业务服务确认 SQL 归属（不存在/他人会话 404），才 issue；响应 `{ticket,expiresIn}`，不得进 URL/日志。票据层不自行决定 active/finished 的命令权限；它只证明本次连接身份，面试服务继续负责业务状态。T21 首帧 `{type:'auth',ticket,afterSeq}` consume 后再次确认 SQL 归属，并按原登录到期关闭。T20 不先建一个不可用的生产 WS 路由。

### 3.4 汇总缓存和 SQL 会话边界

可缓存字段逐一为 `total_calls`、`successful_calls`、`failed_calls`、`success_rate`、`total_tokens`、`prompt_tokens`、`completion_tokens`、`last_called_at`、`daily[{date,calls,total_tokens}]`、`by_task[{task,calls,total_tokens}]`。`recent_calls` 整个数组不得入缓存；它每次只读取最近 12 行，模型名与错误明细留在这条 SQL 查询里。

把 llm_settings 的 usage 查询拆成 `load_usage_summary(db,user_id)` 和 `load_recent_usage(db,user_id,limit=12)`。前者使用 SQL 聚合（总量、按日期、按 task），后者 ORDER BY called_at DESC LIMIT 12；保持 LlmUsageDashboard 响应字段。cache 存汇总，不存 recent_calls、model/base_url/API Key/简历/权限。缓存 miss 时在短 Session 中读取汇总并 SET EX 30；GET/SET 失败直接返回 SQL 结果。详情每次查询，缓存命中不省略鉴权。

`record_llm_usage` 成功 commit 后调用 invalidate_usage_summary；DELETE 失败只告警，不能把已记录的调用变成业务失败。并发旧快照填回允许在 30 秒缓存寿命内过期，不增加锁/版本号/哈希。查询窗口短且每次独立 Session；若缓存计算耗时接近 TTL，使用计算开始时间推导剩余 TTL，已耗尽则不写，避免把旧快照重新缓存满 30 秒。

路由改成 async 后，SQL 聚合与 recent 查询通过 run_in_threadpool 的短闭包执行；不要在 await Redis 的期间保留已开启的 MySQL 事务。命中与未命中的 recent_calls 都返回 ORM 之外的 schema 数据。

### 3.5 SQL 提交后的提示和补查

T20 实现固定 InterviewHints 频道和 `read_interview_events`；T16 负责写 InterviewEvent：锁定 InterviewSession 行后分配 seq，把命令/回答/待执行 Run/事件在业务事务中提交；只有 commit 成功后发送 `{interviewId,lastSeq}` 提示。同步 worker 使用同 payload 的同步 publish。提示失败不能回滚 SQL，也不重复业务操作。

每个 API 一条独立 Pub/Sub reader，收到提示只 set 本地已注册会话的 asyncio.Event；Event 合并重复提示，不堆积无界消息列表。`watch()` 负责注册/退出清理；没有本地连接的会话无需保存提示。消费者先注册 watch，再读 SQL；每次先 clear 唤醒位、短 Session 读取 `seq > cursor ORDER BY seq LIMIT 100`，发送后按实际 seq 前进；有提示立即查，无提示最多 3 秒再查。每次使用新的 SQL Session，避免 MySQL 默认隔离级别下沿用旧快照。提示的 lastSeq 只是唤醒信息，不能据此跳过 SQL 行。

T20 用 tests-only consumer 验证跨 API 唤醒/丢失后补查；真实 WebSocket 的 Origin、首帧 5 秒、队列 100/消息 64KiB、心跳 20/60 秒、登录到期、断线重连、命令 ack 和浏览器缓冲由 T21 实施。HTTP/WS 的共同命令服务与 clientMessageId 幂等属于 T16/T21，不在 T20 增加第二套状态机。

## 4. 故障策略（按真实路径）

| 故障点 | 对外结果/保存状态 | 恢复动作 |
|---|---|---|
| Redis 限流 INCR 不可用或 OOM | 新受理 503；无文件/SQL 新任务；不回退本地桶 | Redis 恢复后重新请求 |
| 已通过限流并 SQL commit，发布失败 | 原接受响应；Run 仍 queued | 保持 15 秒 scanner 补投；重复投递仍由 SQL claim 幂等 |
| 票据 SET/GETDEL 不可用 | 新票据/新连接 503；不延长登录 | 恢复后重新申请票据；不复用不确定消费结果 |
| stats GET/SET/DELETE 失败 | SQL 结果可用；详情正常；提交不回滚 | 下一请求/TTL 自然恢复 |
| Pub/Sub 断开、漏信号或重复信号 | 持久事件不丢；本地消费者按 seq 去重 | <=3 秒补查；reader 重订阅后先补查 |
| Redis 重启且丢失临时数据 | 旧票据失效；计数可以重置一窗；缓存冷启动；不得声称跨重启严格配额不变 | SQL Run/事件仍在，scanner 重发；验证不同 API 使用同一新计数 |
| MySQL 不可用 | 业务/鉴权失败，不能用 cache 或 Redis 授权/伪造状态 | 不提交新任务；按既有 SQL 错误语义恢复 |
| API 重启/关闭 | 仅关闭本地 client 和订阅；不结束面试/取消 Run | 另一 API 重新认证/按 seq 补查 |

## 5. 文件职责与可并行界限

| 子单元 | 文件归属 | 交付与依赖 |
|---|---|---|
| A：环境与连接生命周期 | 新 infrastructure/redis_client.py；修改 app.py、worker.py、worker_tasks.py（仅容量读取）、compose.yaml、.env.example、pyproject/uv.lock；SQLite fixture/三个测试路径 | 先冻结 client/error/env 接口；拥有所有共享生命周期编辑 |
| B：限流与受理入口 | middleware/rate_limit.py、routes/api.py、chat.py、agent_runs.py、documents.py、jobs.py、runs.py、resume_versions.py；test_rate_limit.py | 使用 A 注入 client；不改 create_run/worker 算法；与 T15 的 jobs.py 串行整合 |
| C：统计缓存 | services/dashboard_cache.py、llm_settings.py、routes/settings.py；新增 test_dashboard_cache.py | 使用 A 同步/异步池合同；不改模型调用/usage 归属 |
| D：票据与提示 | services/ws_tickets.py、realtime_bus.py、interview_events.py、auth/security.py；test_realtime_primitives.py、test_realtime_bus.py | 只提供现有 SQL 表的读取/票据；auth 接口先给 B；不改尚未实施的 T16 核心 |
| 根/独立集成负责人 | tests/test_redis_integration.py、tests-only backend/tests/fixtures/redis_api.py / redis_worker.py、最终文档 | 使用 A 环境，合并四分支后真实双 API 测试；fixture 不进入生产路由 |

最多按实际可用 agent 槽位并行；先 A 接口/最小 Compose 与 D 的 auth 合同，再 B/C/D，最后单一负责人整合。T16 的 interviews.py、worker 新 kind、事件写入与原子命令事务不交给 T20 并发修改。T21 直接复用 watch/read/票据接口；不得为先过测试造一套假生产面试流程。

## 6. 实施任务与定向红绿（已完成）

### Task 1：共享环境和生命周期

- [x] 完成 `test_redis_lifecycle.py` 的资源/lifespan/worker/容量测试：新 lifespan 获得新资源，reader 在 pool 前关闭，fork 后同步资源重建；14 passed。它们创建真实 redis-py 客户端但不连接 Redis，真实连接另由七场景验证，不混写覆盖范围。
- [x] 写/运行环境断言：两个 `/healthz` 来自不同容器；API 内检查同一 MySQL 数据库和同一 SQL seed；API 看不到 `/app/agent-state`；worker 看得到锁目录。未达标不得运行后续跨进程用例。
- [x] 按第 2/3.1 节实现 Compose 和进程生命周期；依赖声明显式加入 `redis>=6.4.0,<7`，lock 保持目前 6.4.0；不顺带升级 Celery/SDK。
- [x] 在最终完整本单元七场景中验证 topology，记录 MySQL 8.4.13、Redis 7.4.12、redis-py 6.4.0、双 API/同库与 worker 专属 checkpoint；生命周期单元结果另记。

### Task 2：原子计数和所有实际受理入口

- [x] 写最小失败断言（真实 Redis，多协程；测试通过 A/B 两个 API 交替发起）：

```python
results = await asyncio.gather(*(client.allow_request(7, 'run') for client in clients))
assert sum(allowed for allowed, _ in results) == 10  # clients 共 20 次，分属两个 API
assert all(retry > 0 for allowed, retry in results if not allowed)
```

- [x] 补实际路由测试：Redis down 时上述每一入口返回 503，SQL 新 Run/Document 数量和上传文件数不变；GET/cancel/action 不被这个 dependency 拦截。失败说明遗漏路由或副作用次序不对，修依赖位置，不新增 service 内同步限流。
- [x] 用第 3.2 节 Lua 替换进程字典，加入依赖和 503 错误映射；删除未被测试使用的 RATE_LIMIT_ENABLED 生产绕过开关；测试按第9节注入边界，不新增开关或本地 fallback。
- [x] 完成新限流合同 35 passed、旧相关路由两库 18 passed；最终七场景验证用户/scope 隔离、TTL 不续期、auth 共用 IP 桶及 10/20 拒绝，原始结果分别留证。

### Task 3：统计缓存有用且不污染详情

- [x] 写真实 SQL+Redis 用例：两个用户有不同 usage；20 次相同用户 GET（A/B 交替）除 recent 查询外只执行一次缓存填充的聚合查询组；新 record_llm_usage 提交后下一 GET 看见新汇总；user B 不读到 A 数据。
- [x] 加故障用例：停止 Redis 后 GET 返回 SQL 正确汇总与最新 recent_calls；DELETE 失败不使 record_llm_usage 失败；TTL 到期可重新读取。失败分别修查询拆分、key 归属、异常边界或 commit→DEL 次序。
- [x] 按第 3.4 节拆查询、接路由、在唯一生产 usage 写入口 commit 后失效；不缓存整个 LlmUsageDashboard。
- [x] 完成缓存/设置定向与最终七场景 cache 验证；20 次 HTTP 实测 3 条聚合+20 条 recent，含鉴权共 43 条 SQL。审查后鉴权 Session 先释放再 await，双库 RED 后相关 22 passed。

### Task 4：一次性票据与丢失提示的持久补查

- [x] 写两个实际 API 进程并发消费同一票据的断言：`sum(claim is not None) == 1`；TTL 到期/原登录已到期为 None；票据字段 user/interview/exp 不被请求覆盖；Redis 故障是 503。失败改 GETDEL/过期验证，不引入本地票据存储。
- [x] 写已拥有两个用户/两个面试 SQL seed 的补查测试：先注册 API2 consumer，API1 提交 seq=1 后 publish，API2 得到 seq=1；断开 API2 的 PubSub，提交 seq=2，不 publish，API2 在 <=3 秒通过 SQL 读到；重复 hint 不重复发送；异用户 404。失败修订阅顺序、短事务或游标，而非提高提示重试次数。
- [x] 按第 3.3/3.5 节实现 service 和只读 SQL helper。tests-only API fixture 提供 issue/consume/consumer 观测入口，所有测试路由都不挂到生产 app。生产 ticket 路由等 T16 归属服务接线。
- [x] 完成实际文件 `test_realtime_primitives.py`、`test_realtime_bus.py` 的定向测试和最终七场景 ticket/notification 验证；正常提示 27.98ms、漏提示补查 1.758s。没有真实 WS 双向连接验收。

### Task 5：真实故障整合与交接

- [x] 用 tests-only publish barrier 在限流已成功、SQL 已提交后暂停发布。实际停止 Redis，再释放 barrier；断言 API 返回 accepted、SQL queued；重启 Redis 后由原 scheduler/worker 完成，同一 Run 只有一份业务产物/operation/终态事件。失败说明 SQL 受理或恢复协议被回归，修对应实现；不手工修改 DB 状态或直接调用 finish。
- [x] 在同一次 Redis 重启中覆盖 stats 回 SQL、tickets/new admission 503、SQL SSE/事件补查仍可读、reader 恢复。重启后重新计数/申请票据；不把 AOF 的可能保留误说成所有临时数据必丢，也不要求其成为新权威。
- [x] 在独立测试 Redis 设置可复现的低内存上限填充测试键，确认 noeviction/OOM：原队列标记不被移除、容量 WARNING 出现、限流/票据拒绝、cache SQL fallback。结束销毁该 project；不修改开发 Redis。失败修部署策略或异常映射。
- [x] 执行完整**本单元** `RESUMATE_REDIS_INTEGRATION=1 python -m pytest backend/tests/test_redis_integration.py -q -s`。此开关仅是显式集成测试门禁；未启用时 skip，不能记录通过。之后只复测受默认 Compose 路径移动影响的 SQLite fixture 启动/原有相关用例，根任务决定需要重跑哪一项既有长实验，不无条件重复四个 T14 崩溃点。
- [x] 输出稳定证据目录与本单元报告，确认 T16/T21 接入界限和未执行内容。此阶段不增加案例数量来虚构 T16/T21 评测已执行。

## 7. 真实集成验收与证据格式

由显式入口启动唯一 Compose project，端口随机、数据库/Redis/卷均独立。build 当前应用镜像一次；不得复用缺少新依赖的 T11 镜像而只改一两个源文件。需复用依赖镜像时，明确完整源码 bind mount 与依赖版本符合本次代码。

验收顺序：拓扑/同库 seed → 双 API 原子计数 → 跨 API 票据唯一消费 → stats SQL 减少/隔离/失效 → 提示正常与丢失补查 → Redis down 与提交后投递间隙 → restart → 独立 OOM 资源。外部模型始终确定性 stub；真正调用 SQL、Redis、Celery、API 进程和 checkpoint。

证据目录使用独立持久 `/tmp/task-20-artifacts-<invocation>/`，不放 pytest 自动清理目录。每案记录：case_id、输入、开始/结束时间、API 容器身份、SQL 数据库版本、Redis 版本/配置、实际客户端版本、执行状态、观察结果及原始日志路径。关键观察为 HTTP 状态/允许数/TTL、ticket 成功消费数（不保存票据原值）、cache 的查询数量和用户ID、SQL event seq 与读取时刻、Run ID/status/attempt/execution_epoch、业务 operation/产物计数。配置输出脱敏；不保存 Bearer、ticket、请求认证体或 MySQL 密码。`executed:false` 的环境启动失败不能计成业务验收通过。

T20 没有压力性能结论。T21 的 30 WS+30 SSE、ack P95<=300ms、正常提示 P95<=1s 与故障补查<=3s 中，前三者等待真实 WS；T20 只验证补查机制及受控事件的实际时间。T17 再按规定硬件和数据规模测量，不用 stub 模型速度代替 Agent 性能。

## 8. 官方依据（查阅于 2026-10-30）

- [redis-py 6.4 async 连接池生命周期](https://redis.readthedocs.io/en/v6.4.0/examples/asyncio_examples.html)：async client/外部池需明确 aclose；PubSub 自己持有连接。这里只采用当前 lock 已有版本的 API。
- [Redis GETDEL](https://redis.io/docs/latest/commands/getdel/)：6.2 起支持单命令读取并删除；当前 7.4 环境可用。
- [Redis INCR 限流模式](https://redis.io/docs/latest/commands/incr/)：计数与过期需在原子脚本中完成，避免分开请求时留下无过期计数。
- [Redis Pub/Sub 交付与数据库范围](https://redis.io/docs/latest/develop/pubsub/)：提示至多交付一次且不按 DB 编号隔离；由此采用环境频道和 SQL 补查。
- [Redis 内存淘汰策略](https://redis.io/docs/latest/develop/reference/eviction/)：noeviction 在达到上限时拒绝增加数据，不能拿缓存淘汰策略保护队列；同时观察内存与拒绝写入。
- [Docker Compose 启动依赖](https://docs.docker.com/compose/how-tos/startup-order/)：用 health 与一次性服务完成条件建立 schema→API/worker 顺序。


## 9. 追加：现有 HTTP 单测的统一注入与认证 override 边界

本节边界已经实施。实施前 `backend/tests/conftest.py` 只有环境变量/路径设置；`test_document_tasks.py`、`test_jobs.py` 等自己创建局部 FastAPI，`test_agent_run_routes.py` 等直接 `TestClient(app)` 而不运行 lifespan。许多测试以 `app.dependency_overrides[get_current_user]` 返回 `SimpleNamespace(id=1)` 或 User，不带 Bearer。这些是已有业务测试的合理隔离边界，不能为加 Redis 逐个改造所有 router 测试。

### 9.1 选择一个运行时 getter，不捕获 client

生产依赖仍为 FastAPI dependency，但取得限流服务只走 `backend.middleware.rate_limit.get_rate_limiter(request)`。它读取 lifespan 放入的 `request.app.state.rate_limiter`；未初始化时显式抛 RedisUnavailable，走 503。没有 lazy 本地 limiter、测试环境识别、默认 allow 或新生产开关。

```python
# backend/middleware/rate_limit.py：生产结构合同
# _enforce_limit 保留本计划已定义的 RedisUnavailable→503、拒绝→429/Retry-After。
def get_rate_limiter(request: Request) -> RedisRateLimiter:
    try:
        return request.app.state.rate_limiter
    except AttributeError as exc:
        raise RedisUnavailable('限流服务未初始化') from exc

async def _enforce_limit(request: Request, subject: int | str, scope: str) -> None:
    try:
        allowed, retry_after = await get_rate_limiter(request).allow_request(subject, scope)
    except RedisUnavailable as exc:
        raise HTTPException(status_code=503, detail='限流服务暂不可用') from exc
    if not allowed:
        raise HTTPException(status_code=429, detail='请求过于频繁',
                            headers={'Retry-After': str(retry_after)})

async def require_run_capacity(request: Request,
                               user: User = Depends(get_current_user)) -> None:
    await _enforce_limit(request, user.id, 'run')
```

现有 auth/chat dependency 也调用同一个 `_enforce_limit`，各自按第 3.2 节计算 subject/scope。getter 必须在 `_enforce_limit` 执行时通过本模块全局名称查找；不要把它提前捕获进 `Depends(get_rate_limiter)`、默认参数或闭包变量。FastAPI 会保存 Depends 的 callable 对象，仅 monkeypatch 同名模块属性无法替换已捕获对象。这个运行时 getter 让收集阶段已导入的 router、全局 app 和测试内新建 app 使用同一个明确注入点。

### 9.2 conftest 一个 tests-only fixture

只在 `backend/tests/conftest.py` 增加下述小型可控对象与 function-scope autouse fixture。对象不实现限流算法、不存窗口、不模拟 Redis；默认允许业务路由测试继续检查 SQL/响应，需要验证 429/503 的测试显式设置 result/error。它记录 subject/scope，允许核对依赖确实走过。pytest 结束自动恢复 getter，不写 app.dependency_overrides，因此既有测试的 `.clear()` 不会干扰它。

```python
class ControlledRateLimiter:
    def __init__(self):
        self.result = (True, 0)
        self.error = None
        self.calls = []

    async def allow_request(self, user_id, scope):
        self.calls.append((user_id, scope))
        if self.error is not None:
            raise self.error
        return self.result

# 在同一 conftest 注册 marker，避免 pytest unknown-marker warning。
def pytest_configure(config):
    config.addinivalue_line('markers',
        'real_redis: exercise actual Redis resources without the controlled limiter')

@pytest.fixture(autouse=True)
def controlled_rate_limiter(request, monkeypatch):
    if request.node.get_closest_marker('real_redis'):
        yield None
        return
    from backend.middleware import rate_limit
    service = ControlledRateLimiter()
    monkeypatch.setattr(rate_limit, 'get_rate_limiter', lambda request: service)
    yield service
```

不 monkeypatch FastAPI/TestClient 构造器，不增加统一 App 工厂，不给所有测试启动 Redis，不把 stub 放进 production infrastructure。原 900 左右后端测试不是 900 个 Redis 集成证据；业务测试仍只证明自己的业务断言。

新增 Redis 原子算法/生命周期专测，以及整个 `test_redis_integration.py` 使用 `pytest.mark.real_redis`，绕开上述注入。实际双 API 是独立容器进程，也不会继承 pytest 主进程的 monkeypatch；它们必须运行真实 lifespan、真实池和 Redis 实现。tests-only Compose API fixture 只增加观测入口，不导入 conftest 或替换生产 limiter。集成门禁未开启只能 skip；不得无 Redis 时悄悄改用 ControlledRateLimiter 让原子性用例变绿。

### 9.3 保持 get_current_user 的依赖身份和行为

`require_run_capacity` 与已有业务路由继续引用原 `get_current_user` 对象，不改成 `Depends(get_current_auth)`，也不在依赖体内手动调用 `get_current_user()` 或重新读取 Bearer。这样 FastAPI 的既有 override 仍生效；同请求中相同依赖可按原缓存规则共享结果。返回值只要求 `.id`，不要求旧测试的 SimpleNamespace 额外提供 token/exp。

票据独用新 `get_current_auth` 依赖，返回 `AuthContext(user, auth_expires_at)`。实施时将原 JWT 验证和 SQL 用户读取提取到 `_authenticated_user_and_claims(token, db)`，旧 `get_current_user` 调用它并仍返回 User；新依赖调用它并额外要求 exp。这样各入口只验证一次 JWT，没有新增请求缓存或隐藏状态。角色仍来自 SQL，原 exp 保持 UTC 到期时间。

票据测试若需要隔离身份，覆盖 `get_current_auth` 本身；验证真实票据链路的用例则用 create_access_token 和 SQL 用户，不覆盖它。仅 override get_current_user 不代表可以跳过票据需要的 Bearer/exp。

### 9.4 最小回归目标（已按定向测试实施，集成结果另记）

- 局部 FastAPI、无 lifespan、`get_current_user -> SimpleNamespace(id=7)`，仅挂一个使用 require_run_capacity 的 probe 路由；不带 Bearer 请求成功，controlled.calls 恰为 `(7, 'run')`。失败表示旧 override 被绕开或 getter 提前捕获，修依赖图/运行时查找，不改每个旧测试。
- 同一 probe 设置 result=(False,12) 得 429/Retry-After=12，设置 error=RedisUnavailable 得 503；未配置用户 override/不带 token 时仍 401 且 limiter 无调用。失败修 HTTP 适配，不能关闭限流或认证。
- `real_redis` 的局部 app 不跑 lifespan 时不得默认放行；运行实际 lifespan 后才得到真实资源。两个 API 的原子计数、TTL、故障策略仍按第 6/7 节验证，禁止用 controlled 对象证明。
- 保留现有 `test_document_tasks.py`、`test_jobs.py`、`test_agent_run_routes.py` 的测试构造方式，定向运行其受影响用例；新票据 auth context 用例验证真实 exp 与原 get_current_user override 边界。通过后由根任务安排一次必要全套，不反复扫描/改写旧测试。

文件归属补充：B 拥有 `conftest.py` 的上述注入以及限流 HTTP 适配测试；D 保持 auth 依赖身份并提供 get_current_auth；A 仍只负责 app.state.rate_limiter 的生命周期。B 与 D 先按此接口同步，不互改共享认证文件。


## 10. 最终验收与真实限制（2026-10-30）

- [x] 最终 invocation `723a546aee5345e294ef62a0ab12f421` 七个真实场景 7 passed / 86.52s；独立 project 已清理。真实停机后同一 queued Run 由原 scheduler/worker 完成，一份版本/operation/成功终态，未手工改状态。
- [x] 三次业务未执行均留存：Docker export/unpack 只读/磁盘不足 `241c20c7`；旧底座六项依赖不符 `647e42b1`；fresh backend-data copy-up 冲突 `21db45b0`。第三项以 `volume.nocopy: true` 红绿修复后 fresh 并行启动通过。
- [x] 最终镜像路径为当前 lock 的依赖对齐层（uv sync 使用 --no-cache）+ 当前完整源码快照；安装包与 lock 差异 `{}`、缺直接依赖 `[]`。它不等于完整生产 Dockerfile fresh 构建完成，T19 显式保留该交付项。
- [x] 完整后端首轮 969 passed / 2 failed / 10 skipped；eval 子进程限流 fixture 修复后定向 2 passed；另有鉴权 Session 审查修复 22 passed。未把这些结果合并冒称一次全绿。
- [x] 真实浏览器 27 passed、三张桌面/手机图实际查看；旧 SQLite Linux 中文 PDF 1 passed / 14.17s，两页 1218 字及版面实际查看。未重复旧四崩溃实验。
- [x] 仅测试清理追加 `--profile oom` 后，实际精确清理命令通过；没有为一行收尾重复七个已绿场景，as-run 源码快照保持原样。

[测试记录及稳定证据](../../learning/test-records/2026-10-30-t20.md)保存各次 invocation、完整源码/依赖核验、原始输出、PDF 和截图。没有付费模型调用、真实 WebSocket 或压力性能结论。后续按 [T16 计划](2026-10-30-t16-text-interviews.md)接入持久命令，再完成 T21；T19 负责完整生产新镜像与发布交付。
