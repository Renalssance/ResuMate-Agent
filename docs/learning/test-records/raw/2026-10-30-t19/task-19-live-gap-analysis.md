# T19 durable/interview live runner 缺口与最小接入建议（只读结论）

检查基于当前工作树：`evals/run.py`、`task_runner.py/task_fixtures.py/task_verifiers.py`、`interview_runner.py/interview_verifiers.py`、`records.py/budget.py`、真实 Harness、Interview runtime/context 与共享脚本模型。没有修改这些实现，没有供应商调用；既有 3 元总账不重置、不继续消费。

## 已经正确的边界

- 原 12 案 live 通过 `make_live_model` + `BudgetCallback`，实际请求前持久预留；有 usage 才按官方配置计算 observed cost，无 usage 保留预留。主进程按同一 invocation `budget.json` 串行执行子进程，预算停止后余案 not_run。禁止重定向的新设置保留。
- 8 个 durable 和 6 个 interview 的 stub 已通过真实受理、claim、handler/SDK graph、SQL 与事务 oracle，不是把 pytest pass 当评测输出。但外部模型被脚本替换，因此它们不能证明实际模型质量。
- CLI 对这 14 案 live 明确写 `durable_live_not_implemented` / `interview_live_not_implemented`。这是实现缺口；即使换成足额 key，当前也不会执行，不能仅写为“额度阻塞”。
- 4 个 Compose 恢复案不是模型质量测试，继续按本轮 invocation/context/input 的真实 SIGKILL 证据合并，不为了 live 强行变成付费实验。

## 真实缺口与最小修改面

### 1. CLI 预检和共享账本

`run.py` 的 live 预算/凭据预检目前只覆盖非 durable/compose/interview 案；两类分支在创建隔离子进程前直接 not_run。接入时应将 durable/interview 纳入相同预检，将 `config` 和同一个 invocation 账本传给各 runner，再移除其 not_implemented 分支。不要创建每类独立预算、第二 core 入口或自动补充值。

最小无网络验证：仅选择 durable 或 interview 且缺 config/凭据时必须 preflight not_run、零 transport 调用；原 12 案保持隔离白名单与既有账本；上一案例未知预留导致下案不足时下案零调用。旧的 3 元本地账本不能通过新 invocation 重新获得额度；未来明确批准的新额度要单独注明，不混同当前余额。

### 2. Durable：替换最末端客户端，保留真实 Harness

当前 `TaskModel.harness` 整体替换 `AgentHarness.run_schema`，直接返回 Pydantic 对象，跳过真实 prompt、JSON response format、反思/格式回退与 OpenAI 请求。简单将其标成 live 是假验收。

最小接入：live 分支构造真实 `AgentHarness`，保持生产的 guard、prompt、schema 与重试路径，只在评测内给它的实际 `client.chat.completions.create` 配置带预算/记录的调用边界。每一次真正 create（包括 schema fallback、validation reflection）都先 guard，再持久预留，再发请求；响应携 usage 才结算。不要只给外层 run_schema 计一次费。无需给生产 handler 加 eval feature flag。

预算共用现有 `BudgetConfig` 和 ledger 算法；可以把 reserve/settle 的小段逻辑从 callback 提为可由两类调用使用的账本对象，再让现有 `BudgetCallback` 委托，不另写第二套计费。或以 eval 专用 recorder 将 OpenAI ChatCompletion 转为既有记录方法接受的公共消息/usage 形状；选择最少代码且可通过离线测试的做法，不能依赖伪造 LangChain callback 来掩盖实际请求数。

必须按已验证配置显式设置 model、timeout、max_tokens 与 enable_thinking；真实 Harness 现有 `_should_disable_thinking` 只处理其生产供应商策略，不能假定它等于 T13 Qwen `enable_thinking:false`。请求体检查在 MockTransport 中完成。OpenAI SDK retries=0 / follow_redirects=False 保持。

`TaskEmbedding` 当前是可重复四维 embedding，属于明确保留的非付费边界。若只评测生成，报告标注“live generation + deterministic retrieval embedding”；不要把它写成端到端真实向量模型表现，也不要偷偷增加 embedding 付费调用。

### 3. Durable：取消、故障注入和 oracle 不依赖脚本答案

当前 hook key 来自 `First/Second` candidate_name 和 task，label 强制第二次问题变成不同文本。live 不可继续依赖脚本 model.label/response，也不能为满足 oracle 改写供应商答案。

- 部分 candidate 恢复：在实际 `evaluate_match` 业务单元/固定 candidate 身份处注入一次确定性中断；计数区分业务 attempt 与实际 provider call。真实格式反思可能让同一 candidate 多次调用，不应仍硬断言固定 provider 次数 `{First:1,Second:2}`。保留已完成 candidate 重放时无额外调用/无重复报告这个真正不变量。
- 问题不可变：保存第一次真实 result 作为 oracle；第二个显式 Run 完成后，旧 Run 回放必须仍等于第一次且不调用模型。两次正常模型碰巧回答相同不代表缺陷，不应仅凭 `original_question != current_question` 判失败。可另外记录确实不同的情况；无差异时该覆盖点标为未覆盖，不能人工换答案后称真实。
- 取消/所有权变更：在真正请求已进入、响应尚未交给 handler 时设置 barrier，使用实际 SQL cancel/delete/reassign，然后释放响应；断言下一次 provider call 被 guard 阻止、迟到响应无业务写入。已发出的请求即使结果被丢弃仍记费；若本地 guard 已阻止发送，则应零请求/零新预留。
- 事务回滚：保留现有 artifact INSERT 失败注入，实际生成响应照原样进入业务事务；SQL oracle 继续核对 result/op/report/event 均回滚，不靠模型字面值。

最小无网络 RED/GREEN：真实 Harness + OpenAI MockTransport 覆盖有效响应、格式 fallback、验证反思、403无usage、预算耗尽、取消后迟到输出；记录实际请求次数、原始合成公开输出、usage/保守预留和 SQL。不能直接 patch run_schema 返回 schema 冒充这层通过。

### 4. Interview：真实 SDK 可复用，记录器与取消 barrier 仍依赖脚本模型

真实 factory 已有 `model_for_user` 注入点，所以 live 可以复用 `make_live_model(config, BudgetCallback, case)`，保持 `run_interview_generation` / `SqliteSaver` / 全部工具和 `InterviewStep` 校验。主要缺口不是再造一套 interview agent。

当前 runner 的 `model.calls/model.summaries/before_generate` 是 `ScriptedInterviewModel` 私有属性；verifier 读取 `required/context`，这些完整输入由该脚本模型自己解析。换成 ChatOpenAI 后既没有这些属性，也没有取消阻塞点。现有 `CallRecorder.required_projection` 主要为 tailoring，不足以证明 interview 的 `sourceIdentity/jobIdentity/currentAnswer/maxQuestions`。

最小接入是 eval 专用 interview 记录器：在真实 model callback 捕获当前注入的 required block、实际 get_interview_context/read_file 工具响应（包含真实分页），关联 runId/epoch 和结构化 `InterviewStep` 公共 tool args；从实际消息/工具返回证明上下文送达，不从 DB 重新读取后标成“模型看到”。可抽取共享 fixture 的分页解析纯函数供 recorder 使用，但不能让脚本模型继续生成 live 的证据。

取消用 eval transport 的响应返回 barrier；真实请求已经发出且公共响应已取得，先提交 generation.cancel 或 session.finish，再向 SDK 返回同一响应，验证 SQL fence 丢弃迟到结果。此调用正常结算（响应有 usage）；若超时中断无 usage 仍保留预留。两种取消后恢复原 answer 的实际命令合同不变，不新增生产调度。

最小无网络 RED/GREEN：真实 ChatOpenAI + MockTransport 与实际 SDK graph，覆盖工具读取→InterviewStep、两轮上下文、分页、取消迟到响应、403/预算停止；不要重新用 BaseChatModel 脚本类充当 HTTP 接入证明。

### 5. 质量判断和输出留存

- SQL 归属、冻结版本、幂等、8 轮上限、引用逐字存在、取消/回滚和人工确认记忆的 oracle 继续使用真实表与请求记录。它们可以判断业务正确性，不能自动推出反馈有用或没有误导。
- `interview-followup` 当前脚本固定两次 follow_up；live 应如实判是否真的基于已接受回答追问。若模型选择 new_topic，按预先固定的场景要求判未达标或未覆盖；不能强制注入 mode 后宣称模型通过。为每个真实公开问答保存人工语义复核结果，默认仍 unreviewed。
- 只存合成输入、公开正文/tool args、SQL oracle、调用数/usage/成本、异常类名与整数 HTTP 状态；不存 key、任意 provider 错误正文、隐藏推理。live checkpoint 按既有子进程退出清除规则清理。
- `BudgetExceeded` 与 usage超上限停止必须传播为 incomplete/error_code；后续案例 not_run。不要因 handler 吃异常后返回 failed 而丢失预算停止原因。
- 补完离线接线后仍只能声称“live 路径通过无网络契约验证”。现有 ≥90% 真实模型完成率、关键编造为0与3次真实重复仍需未来有额度时实际执行和复核；本次没有通过。

## 建议实施次序（本次只读，不实施）

1. 小步抽出共用预算结算入口，原 12 案预算与隔离回归不变。
2. durable 真实 Harness/HTTP 接入 + 请求体/多调用/取消的离线证据；先单 followup，再其余7案。
3. interview 真实 ChatOpenAI 与独立输入证据记录 + 两轮/取消离线证据；再剩余五案。
4. CLI 纳入同一预算预检；默认 stub 与原 30 案不变，live 质量状态保持明确。
5. 得到新的合法预算/供应商额度后，先一个实际 smoke，再按同一总账逐案执行；预算不够就停止，保留未知预留，不凑次数。
