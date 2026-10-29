# T13 实施合同：可追踪调用与首批 12 案评测

日期：2026-10-30。依赖 T12 最终闭环。依据总计划 T13 与已完成只读准备；本文件为执行细化，不代表评测已通过。沿用已授权独立工作区，完成后保存教学、测试原始结果和人工审阅记录。

## 目标与边界

同一业务 Run 关联模型调用、工具、输入版本、耗时、用量、尝试与产物。Langfuse 只接白名单元数据，观测失败不影响业务。评测使用独立 SQL/checkpoint 数据；默认 stub，显式 live 才访问真实模型。真实费用限制与可忽略的观测错误分开实现。

保留 Run/工具/SDK 既有状态机，不为评测新增生产接口或故障开关。沿用固定快照、人工审阅、来源校验与单 worker 边界。不得将 stub 内容质量或时延记成真实模型结果。

## 调用及输出

入口：`python -m evals.run --suite core --mode stub|live --output <dir>`。另支持 `--cases` 选择 smoke、`--config` 显式预算与能力、`--env-file` 明确读取已授权凭据文件。只读取模型配置白名单，不导入该文件的数据库/存储环境，不输出秘密。

先设置临时 DATABASE_URL/AGENT_STATE_DIR，再导入项目；每案独立子进程/数据库。复用 create_run、claim_run、runner.run_agent、answer_action 和真实 SqliteSaver。stub 只替换模型及约定故障，live 使用同样合成输入与真实 ChatOpenAI，不发布到现有队列。

每次 invocation 保存 manifest、逐调用 calls.jsonl、每案 JSON、report.json/report.md。记录 Git/依赖版本、模型标识、非秘密配置、合成输入、公开主模型原输出、实际版本/来源、逐项确定性 verdict、语义审阅状态、费用、错误和未执行项。不得保存 reasoning 正文、provider 完整错误体、认证信息或真实私人简历。退出码区分通过、失败、预算/配置未完成；退出码 0 不代表人工语义评价通过。

## 十二案与确定性验证

类别固定：正常 3、补问 2、拒绝/取消 2、工具失败 2、重复 1、来源冲突 1、长上下文 1。合成事实必须适配案例，不能把原测试模型固定追加的 API/数据库职责当通用答案。

案例 ID：normal-api、normal-confirmed-fact、normal-project、ask-technology、ask-metric、refuse-fabrication、cancel-waiting、tool-read-failure、tool-write-rollback、duplicate-draft、conflicting-sources、long-context。

正常前端案例只含 React/TypeScript 表单职责；已确认指标案例明确测试环境和测量范围。补问答案包括“无 Kubernetes 生产经历”和“没有可靠性能测量”。拒绝案包含要求编造管理经历的岗位文本。来源冲突必须澄清，不能任选已确认来源。失败案分别注入读工具受控失败和保存事务提交前失败。重复案必须实际重复执行保存工具（live 明示 harness 重放）。取消案先真实 waiting，再取消并验证不再领取。长案必须真实触发 SDK 摘要、文件读取及 checkpoint 重开；未触发不能记覆盖。

`verify(case, output, db_snapshot)` 为只读纯验证器，独立查状态、唯一版本/操作/事件、原简历未修改、建议待审阅、before、owner/version/action 来源、未自动确认事实、取消和回滚残留。手工注入第二版本、错引用、错 before、漏答案时必须报错。合法引用只证明身份，不证明自然语言内容真实。

人工审阅固定检查事实依据、岗位任务有效性、缺信息处理、表达与审阅；逐项 pass/fail/unreviewed/not_applicable，写输入/输出证据和理由，不加无依据权重总分。stub 语义为 not_applicable。首批 live 规模小，逐一审阅实际成功/拒绝输出，失败和未完成也保留。

## 费用控制

live 必须配置币种、总上限、每案/调用次数上限、适用输入/输出最高单价、供应商输入上限、全部计费输出上限与超时。未知能力/价格不能用付费请求探测后再假称事前限额。

同步预算 callback 挂到真实 model，每次主模型、摘要和重试的实际调用前先预留最大费用。usage 已报告时用量核销；超时、缺 usage 或响应丢失保留预留，不记为 0。剩余额不足在网络前停止，后续列 not_run。预算异常 `raise_error=True/run_inline=True`，且不得被 SDK 摘要重试。金额保证以核实过的供应商计价/输出限制为条件，不能把字符估算当账单。

已核实环境非秘密模型：qwen3.7-flash-2026-07-15，北京百炼。官方上下文 1,000,000；北京三档最高输入 1.2 元/百万、输出 4.8 元/百万。最保守预留可使用完整输入容量，不依赖未知 tokenizer。`max_completion_tokens` 含思维链与答案，官方说明最多 10 Token 误差，应计入输出预留。实际完整输出限制与工作上下文预算分开记录。用户金额上限尚待具体可运行 harness 准备好后确认，当前不发 live 请求。

官方依据（2026-10-30）：[模型能力](https://help.aliyun.com/zh/model-studio/qwen3-7-flash)、[价格](https://help.aliyun.com/zh/model-studio/model-pricing)、[OpenAI 兼容参数](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)。优惠/缓存折扣不用于降低保守预留。

## Langfuse

选用可选依赖、显式手工 observation，不挂会上传全文的通用 LangChain callback。只导出 run/session/attempt/epoch、已校验 UUID request_id、工具名、模型名、Token、耗时、受控错误、版本/产物 ID。Run UUID 可直接作为 trace 身份，不新增 hash；不传 raw input、私密答案、记忆、工具参数、Authorization、key 或带查询参数的 provider URL。

模型 callback 覆盖摘要与主模型；观测 callback 不承担限费。工具 span 在实际执行时创建/结束，暂停标 paused，不能事后补事件伪装时序。未配置无需 import SDK；初始化/更新/结束/导出故障放行原业务，避免每事件同步 flush。官方 v5 API 与可选依赖锁版一致，SDK适配通过假client故障测试，不把假client记录视为云端已收到。

## 工作包与验证

A：案例/fixture/verifier及负向验证；B：隔离runner/预算与调用记录；C：runtime白名单telemetry及可选依赖；D：实际stub、限额smoke、人工审阅、教学和证据。A/B先统一 case/snapshot/call 格式，C独占 factory/runner/tools 接点，避免并行改共享文件。

验证必须能指出失败：重复版本verifier不报错则修verifier；缺余额仍发请求则修callback；摘要重试漏计则修模型层接点；遥测失败改变业务则修适配器；长案未摘要则记未覆盖并修fixture触发条件。完成12案stub后，才按明确配置做1案live smoke，再决定同预算内完整12案。任何失败原样保留，不换stub使live变绿。

T14另做四个真实崩溃点与旧长任务迁移；本单元的重开checkpoint和工具重放不代替崩溃实验。
