# T12 实施合同：上下文预算与可维护业务记忆

工作区：`/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`。日期：2026-10-30。

基线 `f3042d2`（T11 功能提交 `1d7c211`）。用户已授权自动推进，每单元保留测试与教学，前端必须实际截图查看。以下 SDK 事实已基于锁定安装包核实，作为实施依据；最终通过以测试记录为准。保持 T09 固定来源与 T11 确认材料边界。

## 已定接口与并行文件边界

- 新模型名 `BusinessMemory`，表 `business_memories`，置于 career_models.py；字段 id/user_id/kind(preference|interview_feedback)/content(text)/source_ref(JSON)/confirmed_at/created_at/deleted_at。保存只接受本人明确确认的手工内容，content 为1–4000字符。删除真正清空 content/source_ref，仅身份/时间用于幂等清理状态。
- AgentSession 增加 nullable `context_invalidated_at` 与 `checkpoint_deleted_at`。Run 创建冻结 input_versions.memories=[{memoryId}]（不含正文）。所有受影响旧 graph thread 禁止 tailoring 复用；PDF 不读 graph，不取消也不阻止。
- GET /api/memories → {items:[{id,kind,content,sourceRef,confirmedAt,createdAt}],pendingDeletions:[{memoryId,affectedRunIds,cleanupStatus:'pending'}]}。
- POST /api/memories 请求 {kind,content,confirmed:true}，返回 item；source_ref 由服务写 {kind:'manual'}，不接受伪造面试来源。DELETE /api/memories/{id} → {memoryId,cleanupStatus:'pending'|'complete',affectedRunIds,newSessionRequired}，重复调用可读清理状态。响应即使200也必须按cleanupStatus显示，不能把pending称清理完成。
- services.memory 提供 `capture_memory_ids(db,user_id)->list[dict]` 与 `memories_for_run(db,run)->list[dict]` 给创建/上下文；后者只读Run冻结ID中仍有效且归属正确记忆。记忆不是可用于简历事实引用的新来源。
- Settings 新字段 nullable `context_window_tokens`，保持旧 max_tokens 为输出上限；更新仅在字段显式给出时改变。所有自定义兼容模型都要求显式容量，不依模型名字猜容量；已有旧记录未配置仍可查看/保存，Agent执行给明确错误。容量需大于输出reserve，实际必保留开销另在发模前检查。
- 主代理负责 models/agent_models/career_models/database、schemas/settings.py、services/llm_settings.py、数据库迁移003与模型设置/存储测试，声明字段稳定后交接。
- 上下文代理独占 agent_runtime/context.py、factory.py、tools.py、新context middleware、业务skill、test_agent_context.py及必要agent_fixtures兼容；不改runner/worker/agent_runs。
- 记忆代理独占 services/memory.py、schemas/memory.py、routes/memory.py及路由注册、services/agent_runs.py、agent_runtime/runner.py、worker_tasks.py、test_agent_memory.py；复用execution_lock与recover_runs清理，不另造通用删除任务框架。
- 前端代理独占前端模型设置字段/记忆面板/任务错误说明与组件测试；父代理负责真实E2E、截图、整体测试和教学。
- 删除影响识别限tailoring Run冻结的记忆ID，所有旧会话可恢复checkpoint都清除。排队/等待当场终止，运行中在下一主模型、摘要或工具安全边界停止；已有外部请求无法回收，文案不宣称已擦除一切历史。

## 1. 已核实的基线

- T09 `context.py:capture_context/read_context` 已经保存完整 `AgentRun.input_json.contextSnapshot`：原简历原文及结构、岗位原文及结构、创建时确认的事实版本正文、最新已有匹配报告。`input_versions` 另记版本身份。本 Run 实际回答从 `AgentAction` 拼入。此快照不是待删除的冗余：`resume_versions.py` 的 `before` 校验、逐条审阅基底和来源面板都依赖它。
- `read_context` 当前会在原简历/岗位被删除或归属变化时阻止新生成；历史快照和版本审阅仍保留。`test_tailoring_context.py` 明确验证这一边界。这个设计对既定 T09 合同是正确的，T12 不应为节省 prompt Token 截断或删除它。
- `ProfileFact` 是保留历史的追加版本事实；现有删除会新增带原正文的 tombstone，旧正文/版本仍在。它适合来源审计，不能直接复用为宣称“删除正文”的 BusinessMemory 存储。
- Agent 目前只有 3 个业务工具：完整返回资料的 `get_application_context`、幂等创建草稿、interrupt 补问。没有 memory 工具或向量记忆；不需要先搭向量召回。
- `factory.py` 使用 `ChatOpenAI`、默认 `StateBackend`，明确排除 `execute/task` 并关闭默认子 Agent。保持这个边界。
- `runner.py` 用 `session_id` 作 `thread_id`，同 Run 恢复原 checkpoint；同 Session 新 Run 会清最新 `files/todos/_summarization_event/_summarization_session_id/messages`。这已解决新任务误用上一任务状态，但没有物理删除旧 checkpoint 历史。
- API 不打开 graph checkpoint；唯一 worker 用 `execution_lock()` 排斥执行/恢复重叠。这是删除 graph 副本应继续复用的所有权边界。
- 个人模型设置仅有 key/base_url/model、`max_tokens` 和 timeout。`max_tokens` 是输出上限。当前无上下文容量配置。新用户不继承环境密钥是有意并已测试的行为；T13 live 不可误认为填 `.env` 即给用户 Run 配好模型。

## 2. 本机 SDK 的确切能力与容易踩错的地方

安装版本：DeepAgents **0.7.32**、LangChain **1.4.7**、LangGraph **1.2.18**、SQLite saver **3.1.2**，直接核实 `.venv/lib/python3.12/site-packages` 实现。

1. `deepagents.middleware.summarization.SummarizationMiddleware` 是应复用的摘要实现。`create_deep_agent(middleware=[...])` 按 `.name` 替换默认中间件，不是总会再叠一层。只替换一次摘要中间件。
2. SDK 若看到 `model.profile['max_input_tokens']`，默认 `trigger=('fraction', .85)`、`keep=('fraction', .10)`；未知模型回退到 **170000 tokens / 保留 6 条消息**。不能拿该默认推断任意兼容 API 的上下文容量。
3. `ChatOpenAI` 未显式传 profile 时仅按 `model_name` 查默认 profile，没有用自定义 `base_url` 验证实际部署能力。同名模型代理、不同厂商兼容端点都不能靠名字自动确认容量。
4. SDK `_input_budget` 会从 profile 容量减去 5% 余量和实际配置的输出上限；完整计数包括 system message 和 tools（counter 支持 `tools` 时）。不要在应用再减同一份 reserve 两遍。
5. SDK 摘要保留原始 `state['messages']`，摘要写到 `_summarization_event`；原消息还外置到 `/conversation_history/{内部session_id}.md`。仅清 summary 或在记忆表做软删除不足以清除副本。
6. `StateBackend` 的文件存入图状态并随 checkpoint 落盘，跨本线程步骤/worker 重启可恢复，不是宿主机任意路径文件。文件可通过初始 graph input 的 `files` 预填，也可在图执行内 `StateBackend.write()`；不可在图外直接调用 backend.write。
7. `FilesystemMiddleware(tool_token_limit_before_evict=...)` 可替换默认实例，将大型工具文本外置并返回预览/路径，也约束 `read_file` 返回长度。默认 20000 tokens 不适合直接照搬给小窗口；限制基于字符近似。业务摘要仍应返回清楚的 ID/类型/版本/原文读取路径，而非让模型猜文件。
8. 手动构造摘要中间件时 `trim_tokens_to_summarize` 默认 **4000**，而 SDK factory 默认 **None**。这个参数限制“送去摘要的旧历史”，不是压缩触发点或摘要输出长度；不得误用为整个上下文预算。T12 应明确设置并在长案例验证更早信息来自必保留区/文件仍可获得。
9. `SqliteSaver.delete_thread(thread_id)` 已实现，删除该 thread 的全部 `checkpoints` 和 `writes`。需要完整清理时用它，不自行解析 checkpoint blob，更不做字符串替换。
10. middleware 新条目默认插在 core 之后；默认摘要属于 core。若在更内层 `wrap_model_call` 才追加必保留 system 内容，外层摘要计数可能看不到新增内容。实现必须让“注入必保留内容 + 撤销检查”发生在 SDK 摘要/预算处理之前，并测试模型最终实际收到的请求。

本轮没有需要网络文档才能解决的 API 不确定性；以锁定安装版本源码为依据。升级 SDK 时，摘要私有状态与替换顺序需要定向复验。

## 3. 建议的最小 T12 合同

### 3.1 固定证据与工作上下文分开

保留现有 `capture_context/read_context/changed_inputs` 给来源校验和审阅使用。新增 `build_context(user_id, run_id) -> ContextBundle`，读取归属受限的 Run，产生本次模型输入视图；不改写 T09 快照。

`ContextBundle` 至少包含：

- `required`：任务种类、run/session ID、简历/JD ID 与固定版本、当前请求和不能编造/不能自动提交的约束；已确认事实的确切正文与 `factId/revision`；本 Run 待回答动作及 question/action ID；本 Run 已提交回答及 action ID；当前已存在业务产物引用；本 Run 选定且仍有效的确认记忆。
- `artifacts`：长简历原文/结构、JD、历史 match 的稳定 ID、类型、版本、简短描述、SDK 文件路径。标清 JD 不是经历证据、match 不是新评分、摘要不能替代原来源。建议 ID 使用业务身份，例如 `run:{runId}:context:resume`，不加 hash。
- `budget`：实际模型名称、显式容量、输出 reserve、可用输入估算、必保留区估算、估算方法；只记录数字与引用，不复制敏感正文到事件。

“必须保留”不是只放在第一次工具消息里期待摘要记住。每次主模型调用前，从 SQL 重建上述小的必保留区，进入摘要不能丢失的 system 部分。事实和本 Run 回答不可悄悄截断；如果必保留内容本身加系统/工具开销已经超预算，返回明确 `context_budget_exceeded`，引导提高已核实的容量或减少本次输入。不要偷偷丢约束或丢引用后继续生成。

可用的最小接法：一个薄的 `SummarizationMiddleware` 子类，保持公开 `.name == 'SummarizationMiddleware'`，仅在 `wrap_model_call` 入口完成运行权/记忆撤销检查及 `request.override(system_message=...)`，然后调用 SDK `super().wrap_model_call`。摘要引擎、分区、历史外置、工具消息配对和 overflow 恢复全部由 SDK 处理。这样注入后的内容被 SDK 预算计数包含；不要另写摘要循环。若选其他接法，也必须用实际模型输入捕获测试证明注入顺序正确。

### 3.2 当前长工具结果不需要新建通用 Artifact 平台

今天唯一大的业务工具结果就是 `get_application_context`，其完整权威内容已在 SQL 快照中。优先把已有快照当作持久受控产物，按 resume/job/match 分成可分页的 JSON/文本文件写入当前 StateBackend。工具返回简明 manifest、必保留内容、稳定 artifact ID 与文件路径；短输入可维持当前易读正文形态，但两种形态须有清晰契约，测试模型也须真正支持读外置文件。

模型用已有 `read_file(offset, limit)` 取精确字段和 source_refs。`before` 与来源校验继续回到 SQL 完整快照，不能信任模型可修改的文件镜像。可用 SDK 原生 `FilesystemPermission` 让 `/inputs/**` 仅可读，业务工具直写镜像；保留 SDK 自己的 `/conversation_history` 可写。不要给模型宿主机文件系统，也不用新增任意文件上传/下载端点。

这一选择满足“持久产物 + 摘要与 ID”：SQL 是权威持久原件，StateBackend 是可恢复工作副本，工具给出确定性摘要（名称、字段/记录数、用途、来源身份）与稳定引用；不额外调用模型总结整份简历。如果后续出现不属于现有快照的新型长业务结果，再给实际类型增加产物存储。

### 3.3 模型预算字段

- 新增个人设置 `context_window_tokens`（可空；未知不能默认 200k）。继续用 `max_tokens` 作输出 reserve，并把列表标签改成“输出 Token 上限”。
- 最小首版可要求所有自定义兼容端点显式填写容量，省去不可靠的模型名识别表。官方已核实 profile 可以显示来源，但本任务没有必须自动推断的要求。
- `model_for_user` 在 Agent 执行前校验容量存在且能容纳输出 reserve/系统/工具/必保留区；失败给出 `model_context_not_configured` 或 `context_budget_exceeded`。传显式 `profile={'max_input_tokens': C, ...}`，不借用名称错误匹配的容量。
- 复用 SDK 的 5% 余量与输出 reserve，摘要阈值/保留窗口和长工具外置阈值由该预算派生，不另开一页高级参数。
- SDK 的默认 `count_tokens_approximately` 使用英文约 4 字符/Token。当前主要是中文输入，必须标注“估算”，不能把该值宣传为准确 tokenizer 或账单。可用同一个 SDK counter 的明确偏保守字符系数作规划估算，并通过 T13 live 的 provider usage 校准；不要随意对兼容模型使用 OpenAI tokenizer 冒充精确值。现有 `ChatOpenAI.get_num_tokens_from_messages(..., tools=...)` 明确忽略工具 schemas，也不能直接用它声称完整请求精确计数。
- 原有资料解析/聊天不必在 T12 全面切预算框架；本任务接实际 DeepAgents tailoring 入口。设置字段的 SQLite 增量列和现有 MySQL 手工迁移 SQL 都要按项目惯例补上，不引入迁移框架。

### 3.4 用户确认记忆

新增独立 `BusinessMemory`，最少字段：`id, user_id, kind, content, source_ref, confirmed_at, created_at, deleted_at`。`content` 是可清空的文本，`source_ref` 是可清空的 JSON；首版 `kind` 严格为 `preference | interview_feedback`。保存动作必须来自登录用户明确确认；不向 Agent 暴露自动写记忆工具。偏好/反馈只调节措辞、准备重点，不增加个人经历来源种类，不允许 `create_resume_draft` 把 memory ID 当经验依据。

API：列表、保存、删除即可，避免先搭复杂修订历史。T12 手工保存的偏好或反馈用真实 `manual` 来源；若传已有 `interview_turn` 必须校验会话归属和实际 feedback；T16 接入真实反馈确认按钮时复用同一 service，不能在 T12 伪造不存在的面试来源。

供前后端并行的具体首版 API：

- `GET /api/memories` → `{items, pendingDeletions:[{memoryId, affectedRunIds, cleanupStatus:'pending'}]}`；items 只有未删除正文，pending 列表不含正文。
- `POST /api/memories` ← `{kind, content, confirmed:true}` → `{id, kind, content, sourceRef:{kind:'manual'}, confirmedAt, createdAt}`。服务填 manual 来源，首版不收模型自动写入或用户自造 interview 来源。
- `DELETE /api/memories/{id}` → `{memoryId, cleanupStatus:'pending'|'complete', affectedRunIds, newSessionRequired:boolean}`。重复调用返回当前清理状态。正文与 source_ref 当场置空，tombstone 只保留身份/类型/时间，供归属、幂等和清理状态查询；不能保留原正文。
- `affectedRunIds` 是相关图任务 ID，完成的历史任务与需要停止的活动任务在 UI 表述中区分；不能把历史已完成版本描述为被删除。`newSessionRequired` 仅在该记忆曾进入 graph 会话时为 true。

在 Run 创建时冻结所选记忆 **ID** 到 `input_versions['memories']`，不把记忆正文写进 `contextSnapshot`。读取时按 owner 和 ID 加载有效正文；新保存记忆从下一 Run 起生效，删除则立即撤销旧 Run 的使用权。记录 ID 也提供受影响 Session 的可查询依据；当前规模可按该用户 Run 查 JSON 列后筛选，不需要先建检索索引或向量表。若提供“编辑”，等同撤销旧 ID 并保存新 ID，不能原地改正文让已恢复会话继续使用旧副本。

## 4. 删除语义：正文删除、会话失效、worker 清副本

建议明确文案：“删除已保存记忆及供任务继续使用的副本。已生成的简历、投递版本和原始面试记录仍保留。”这是业务记录与工作记忆的边界，不应写“所有历史痕迹已永久抹除”。原面试反馈或用户后来把同样句子独立确认为事实，都是独立记录，不应被文本搜索误删；也不能从原记录自动重建刚删掉的记忆。

最小可恢复流程：

1. API 在同一 SQL 事务清空 BusinessMemory 正文和 source_ref（不能照搬 ProfileFact tombstone 正文），通过该用户 `tailoring` Run 的 `input_versions['memories']=[{memoryId}]` 找出使用过该 ID 的 Run，再按 session_id 去重识别包含旧 checkpoint 的会话，持久标记这些 Session 已失效、checkpoint 待清理。记录删除事件只带 ID/数量，避免新复制正文。
2. 受影响的 queued/waiting Run 当场终止；running Run 持久取消并在下一个模型/工具安全边界停止，不再发送新主模型或摘要请求，不再保存新草稿。已经发出的 provider 请求不能回收；返回前 UI 可显示“已停止使用，旧任务副本正在清理”，而非声称清理完成。
3. 对失效 Session 的新 Run、retry、answer 和 worker claim 都拒绝旧 thread 继续运行。用稳定错误原因（例如 `memory_deleted` / `session_invalidated`）和清楚的“重新准备材料”入口；新建干净 AgentSession。不要只取消一个 Run 却允许 API 按同一 sessionId 再读旧 checkpoint。
4. 唯一 worker 在现有 `execution_lock()` 内、旧 graph 调用结束后，对受影响 session 调用 `SqliteSaver.delete_thread(session_id)`，同时清任何实际新增的记忆派生文件/摘要存储（采用纯 StateBackend 时 graph 副本随该调用清除）。用一个可查询的 SQL 待清理状态，让现有恢复扫描也能收尾；worker 未运行时显示 pending，不靠一次队列发布当完成证据。
5. 清理成功后标记完成；API 对相同删除重试可返回已完成/待清理状态。需要最少的持久完成状态来区分“已拒绝继续使用”和“副本已清除”，不额外做通用删除任务框架。可用 Session 的 `context_invalidated_at`、`checkpoint_deleted_at` 两个时间戳承担此职责。
6. 保留 T09 来源快照、ResumeVersion、已提交回答和独立面试记录供审阅，不从它们再次自动注入已删除记忆。记忆不应主动在普通 Run 事件里复制正文；历史生成材料/公开任务文字若已体现偏好，属于上面明确保留的任务记录，不能误称“全库擦除”。如产品另做删除完整任务/面试，那是不同操作。

**PDF 隔离：** 以上终止/失效检查仅作用于实际使用 graph 的 `tailoring`。`resume_export` 不读 checkpoint；即使调用者显式给导出任务复用了同一 sessionId，也不能取消它或拒绝其 retry/claim。worker 清理可等待现有全局执行锁释放，但不终止 PDF。旧 Session 禁止新的 tailoring，导出仍按现有独立业务合同运行；以后新增图 kind 时再明确接入这一检查。

关闭整个受影响 Session 是计划明确允许、且本项目可完成的保守实现；逐个清洗旧摘要/多版本 checkpoint 成本高且易漏，不值得做。删除后真正清掉 checkpoint、在清理前完全隔离旧 thread，才不会假删。已完成 Session 也要清其 graph 副本，因为旧 checkpoints 仍存有记忆。

## 5. 建议文件分工与实施顺序

| 工作包 | 文件 | 最小交付 |
|---|---|---|
| A 模型预算/存储合同 | `backend/db/models.py`, `backend/db/career_models.py`, `backend/db/agent_models.py`, `backend/db/database.py`, `backend/schemas/settings.py`, `backend/services/llm_settings.py`, `deploy/schema/003_*.sql`, schema README | 显式容量、BusinessMemory、Session 失效/清理状态；旧数据容量保持未配置 |
| B 上下文/SDK | `backend/agent_runtime/context.py`, `factory.py`, `tools.py`, `skills/resume-tailoring/SKILL.md`，必要时一个聚焦 middleware 文件 | ContextBundle、原生摘要替换、受控文件 manifest、必保留区及预算错误；T09 原快照合同保留 |
| C 记忆及清理 | 新 `backend/services/memory.py`, `backend/schemas/memory.py`, `backend/routes/memory.py`；修改 route 注册、`agent_runs.py`, `runner.py`, `worker_tasks.py` | 用户确认写入、真实删除、旧会话不可恢复、worker 清 thread、持久清理结果 |
| D UI | `frontend/src/views/SettingsView.vue`, `types/settings.ts`, `api/settings.ts`；新 `BusinessMemory.vue`、memory API/types；放入 `ProfileFieldsView.vue` | 容量/输出区分，记忆查看/确认保存/删除；pending 清理与失效任务反馈，桌面和手机可用 |
| E 验证/教学 | 新 `test_agent_context.py`, `test_agent_memory.py`；现有 runtime/tailoring/settings 测试；memory 组件测试与 e2e；`docs/learning/12-*.md`、测试记录、总计划 | 真实 SDK/磁盘 checkpoint 定向证明、截图、Token 前后估算与限制 |

A 的 schema/共享合同先由一个负责人定稿；之后 B 与 D 可并行。C 与 runner/factory/worker 有共享文件，应明确单一编辑者，避免与 T11 当前最终收尾重叠。T12 不需要改已完成的 PDF 导出/投递绑定业务。

## 6. 有实际失败意义的验证（实施后再运行）

每项均说明会发现什么以及失败后的动作。准备阶段未执行这些检查。

1. **未知模型/预算设置**：缺容量不发 provider 请求；同名不同 base_url 不盗用已知 profile；输出 reserve 与必保留区过大给具体错误。若失败，修 factory/config 合同，不能靠 live 的 context overflow 兜底冒充预算正确。
2. **长中文输入 + 真 SDK 摘要**：合成的长简历/JD/match、已确认事实、待回答动作、后续回答和既有草稿引用；低但可行容量触发 SDK 摘要。捕获最终模型请求，断言关键正文/ID仍在，全文文件可分页读，引用与 `before` 可生成有效草稿。若失败，修注入顺序/文件合同；不只断言某个配置值等于预期。
3. **摘要后关 saver 重开继续**：用真实 SqliteSaver 文件，发生摘要后 interrupt，重新构建 saver/agent 再提交答案。确保旧约束与新 actionId 都能用，业务草稿仍只有一个。若失败修持久状态/恢复，不能换假 checkpoint 模拟通过。
4. **不可缩减输入**：只让必保留区就超预算，确认可解释失败且没有草稿/外部模型重复循环。若失败修显式错误和停止条件。
5. **记忆确认与来源**：未确认内容不被保存/注入，跨用户读删失败；面试反馈不成为经历引用；删除后新 Run 无旧内容。若失败修 service 与来源合同。
6. **删除真实副本**：先让某记忆进入原消息、摘要、files，并落多版 checkpoint；在 waiting 与运行边界两种可达状态删除。API/worker 重开后 `get_tuple/list` 不应再有已清理 thread，旧 session 的 retry/answer/create 均不能复活；新 session 完成草稿且不带记忆。若失败修失效 fence 或清理，不能仅看 memory 列表为空。
7. **清理恢复**：删除提交后停止测试 worker，重新启动扫描，确认 pending 会被清掉；检查旧业务版本仍可查看来源。若失败修 SQL 待清理状态，不重写队列平台。
8. **最少回归**：T09 快照/来源/草稿审阅测试、原 runtime 同 Session 新 Run 隔离、worker 领取/取消、个人设置和 SQLite 旧库补列。若 schema 改动触及 MySQL，使用已有独立临时 MySQL 参数执行相同定向测试；没配置则明确 skip，不宣称双库通过。

Token 记录至少保存同一合成案例压缩前/实际发模前估算、计数方法、摘要次数、外置引用、保留约束断言与产物结果。Stub 可证明机制，不证明摘要语义质量或省费用；真实 Token 与额外摘要调用费用留给 T13 live 报告。不要预设节省百分比。

## 7. 前端截图验收场景

- 模型设置桌面：未知兼容模型的“上下文容量未配置”提示；编辑态明确区分上下文容量、输出 Token 上限，保存后列表可核对且密钥仍隐藏。
- 资料页桌面和 390px 手机：空记忆态；已确认偏好与面试反馈列表（含可理解来源）；长中文内容换行、删除按钮、保存成功/失败和键盘 focus。
- 有等待补问任务时删除被使用记忆：页面显示“已停止使用，正在清理旧任务副本”；任务页显示为什么已结束及干净任务入口。清理后刷新仍显示已删除，不恢复旧卡片。
- 必保留区超预算：材料准备页展示可执行的“去模型设置/减少资料”错误，不是无限 spinner 或笼统 agent_failed；手机无横向溢出。
- T12 机制测试使用已有真实 FastAPI/SQL/单独 worker E2E 基础设施和合成资料。截图本身只证明界面状态，后端断言负责证明 checkpoint 删除与不再注入。

## 8. 给 T13 的 live 准备（此轮不启动调用）

需要真实可用的个人测试账号模型配置：base_url、model、key（用户通过现有受控设置保存，无需聊天粘贴）、已核实上下文容量、输出上限/timeout。使用合成简历与回答，不用私人真实简历作默认评测数据。

费用入口必须有显式 live 模式、金额/币种上限，以及该端点实际输入/输出单价（如有 cache pricing 则记录）；不能把 Token 上限直接说成费用上限。开始下一案例/调用前预留可接受的最大调用费用，缺价格/usage 时明确停止或报告无法验证费用，不把未知消耗记 0。摘要和恢复重放也算模型调用。

`RuntimeEvents.message` 目前只记录 `langgraph_node == 'model'` 的主模型 usage，并有意隐藏内部摘要文本；保持隐藏正文是正确的。但 T12 新产生的摘要调用可能未进入现有 usage 合计，T13 telemetry 必须在模型调用层同时统计主调用/摘要/重试，仍不发布摘要文本。当前设置页 usage dashboard 的 `LlmUsageEvent` 与 Agent Run 的 `usage.updated` 也是不同记录，不可直接声称已统一。

12 个 core 案例沿用总计划比例：正常 3、补问 2、拒绝/取消 2、工具失败 2、重复 1、来源冲突 1、长上下文 1。长案例要复用 T12 的可达中文输入/外置文件/关键约束，不能只拼接无关 filler 后计数。确定性 verifier 查版本唯一性、引用合法性、缺失事实未被编造为确认事实、删除记忆不复注入；语义部分保留模型原输出、固定 rubric 和人工抽查。

Langfuse 配置需要 host/public key/secret key 与可用项目；没有配置时观测不可用不能阻塞业务。默认 trace 仅记录 request/run/model/tool 关联、版本/产物 ID、耗时、Token 和重试；完整简历、Authorization、API key、私人回答和记忆正文均不进 trace。T13 报告应分开 stub 机制通过、live 执行结果、预算耗尽未执行案例和人工质量结论。

T14 仍按四个计划崩溃点扩展，不拿 T12 记忆清理实验重复冒充 T14 已完成；解析/匹配/出题迁移等到各 kind 实际接入时再改契约及 worker 派发。

## 执行状态

- [ ] 数据与模型预算设置合同及两库/旧库验证
- [ ] 必保留区、受控文件、原生摘要与真实checkpoint恢复
- [ ] 记忆确认/删除、会话失效与worker清理
- [ ] 前端设置/记忆/状态提示与实际截图
- [ ] 整体联调、独立审查、教学证据与本地提交
