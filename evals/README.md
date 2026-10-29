# T13：本地任务评测

默认使用合成输入和确定性模型；生产 `create_run → claim_run → run_agent → answer_action`、工具事务与 SqliteSaver 均真实执行。每案在独立子进程、SQLite 数据库与 checkpoint 目录内运行，不发布到现有队列。

```sh
uv run python -m evals.run --suite core --mode stub --output artifacts/evals/core
uv run python -m evals.run --suite core --mode stub --cases normal-api,ask-metric --output artifacts/evals/smoke
```

12 案涵盖正常定制 3、补问 2、拒绝/取消 2、工具失败 2、重复保存 1、来源冲突 1、长上下文 1。故障与重放只在评测 harness 注入。长案必须观察实际 SDK 摘要、文件读取、补问后的 checkpoint 重开与必保留上下文；缺覆盖会失败。

每次执行创建唯一 invocation 子目录：

- `manifest.json`：版本、选择的案例、模式、依赖、非秘密配置和 preflight 结果。
- `calls.jsonl`：每个 SDK 调用开始和结束事件，共用 `sdk_call_id`；包含 Run、attempt、epoch、主调用/摘要、耗时、真实已报告 Token 或 null、预留金额与受控错误。主模型公开输出保留文本、工具调用 ID/名称/参数及无效工具参数；即使建议被拒绝或事务回滚也能审阅原提案。没有 reasoning、任意 provider 元数据或完整错误体。
- `cases/<id>.json`：合成输入、公开输出、独立 SQL 快照、逐项确定性 verdict、固定语义 rubric。
- `report.json` / `report.md`：逐案 pass/fail/incomplete/not_run 与费用。live 的原始 checkpoint 数据在子进程结束后删除；真实重开覆盖和 SQL 结果仍保存在 case 报告中。逐次请求的 `required_context_checks` 对照初始约束、事实、偏好、输入版本和当时已存在的答案/产物 ID；只读取实际注入的 SystemMessage，不采信摘要输入里嵌入的旧上下文。

退出码：`0` 表示所有选择的案例确定性通过；`1` 表示确定性失败；`2` 表示配置、预算或 harness 错误导致未完成。退出码 0 不代表人工语义审阅通过。stub 的语义结果为 `not_applicable`；live 默认为 `unreviewed`，需逐项填写事实依据、岗位有效性、缺信息处理、表达与审阅的证据和理由，不计算加权总分。

## Live：先确认配置和金额，再显式执行

Live 不自动启动。先由操作者确认币种、金额上限与供应商能力，再创建 JSON 配置。下面 `APPROVAL_REQUIRED` 是有意不可执行的占位符，不能当作已授权金额：

```json
{
  "currency": "CNY",
  "max_total_cost": "APPROVAL_REQUIRED",
  "max_case_cost": "APPROVAL_REQUIRED",
  "input_price_per_million": "1.2",
  "output_price_per_million": "4.8",
  "provider_max_input_tokens": 1000000,
  "context_window_tokens": 64000,
  "max_output_tokens": 4096,
  "output_token_tolerance": 10,
  "max_model_calls": 120,
  "max_case_model_calls": 30,
  "request_timeout_seconds": 60,
  "output_limit_parameter": "max_completion_tokens",
  "output_limit_covers_all_billed_tokens": true,
  "usage": "reported",
  "model": "qwen3.7-flash-2026-07-15",
  "pricing_checked_at": "2026-10-30",
  "pricing_source": "https://help.aliyun.com/zh/model-studio/model-pricing",
  "capability_source": "https://help.aliyun.com/zh/model-studio/qwen3-7-flash",
  "fixed_request_cost": "0",
  "enable_thinking": false
}
```

上述单价是北京百炼已核实三档的最高价，不依赖优惠或缓存。`max_completion_tokens` 约束全部计费输出，含思维链与答案；预留额包含官方说明的最多 10 Token 误差。首版 harness 固定关闭 thinking，公开记录仍排除 reasoning 字段。能力与价格来源需与实际端点/合约相符；未知项导致 preflight 失败，不通过付费请求探测。

[模型能力](https://help.aliyun.com/zh/model-studio/qwen3-7-flash)、[价格](https://help.aliyun.com/zh/model-studio/model-pricing)、[兼容参数](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)的核实日期为 2026-10-30。

```sh
uv run python -m evals.run --suite core --mode live --cases normal-api \
  --config /tmp/resumate-live-budget.json \
  --env-file /path/to/explicitly-authorized.env \
  --output artifacts/evals/live-smoke
```

`--env-file` 只读取 `OPENAI_API_KEY` / `ARK_API_KEY`、`OPENAI_BASE_URL` / `BASE_URL`、`LLM_MODEL` / `MODEL`。不导入数据库、存储、队列或 Langfuse 配置，不保存 Key 或 base URL。未提供文件时，只取这些显式环境变量；stub 丢弃它们且不创建 provider client。该文件的变量插值关闭，自动 dotenv 加载关闭。模型名须与已核实配置一致。Langfuse 在评测进程中禁用；生产适配器的验证另行记录，不能从本地报告推断云端已收到。

预算 callback 同步挂在真正的模型实例，每次主模型、SDK 摘要和重试调用前持久预留：

```text
provider_max_input_tokens × 最高输入单价 / 1,000,000
+ (max_output_tokens + output_token_tolerance) × 最高输出单价 / 1,000,000
+ fixed_request_cost
```

金额使用 Decimal 并向上保留 8 位小数。上述示例单次预留为 **CNY 1.21970880**。`provider_max_input_tokens=1,000,000` 是计费输入保守上界；`context_window_tokens=64,000` 是工作上下文预算，长案使用最多 30,000 来真实触发摘要。字符估算不降低金额预留。

完整 usage 已报告才按同一最高单价核销；缺 usage、超时或响应丢失保留整笔预留，不能记为免费。预算与调用次数上限在所有案例、attempt 和摘要之间共用。余额或次数不足在网络前抛出不可重试 `BudgetExceeded`，后续案例列为 `not_run`。用量超出已核实能力立即停止后续，报告 `budget_config_mismatch`。保证以已核实的计价与全部输出上限为条件；observed cost 不是供应商已结算账单。

先完成 stub，再在明确金额内运行单案 smoke，检查真实工具协议、usage 与产物后才运行整套 live。不要把 stub 质量、速度或测试中的假 usage 写成真实模型表现。

## 聚焦验证

```sh
uv run pytest backend/tests/test_eval_budget.py backend/tests/test_eval_runner.py \
  backend/tests/test_eval_verifiers.py backend/tests/test_eval_fixtures.py -q
```

这些检查分别检测网络前限额、摘要/重试计数与未知费用、隔离/真实暂停恢复、回滚与取消、手工注入重复版本/错引用/错 before/漏回答的验证器失效。它们不代替 T14 的进程崩溃恢复实验。
