# T13 C：元数据遥测交付报告

工作树：`/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`。
范围已完成；未提交 Git，不包含独立审阅。未读取真实 `.env`，未发送真实模型或 Langfuse 请求。

## 改动文件

- 新增 `backend/agent_runtime/telemetry.py`：Langfuse v5 可选初始化；显式手工 agent/generation/tool observation；失败时停用本次 trace 并记录一次无异常正文的受控 warning。运行身份为 `UUID(run.id).hex`，没有新增 hash。
- 修改 `backend/agent_runtime/factory.py`：把元数据 callback 挂到实际 model，保留所有已有预算/调用记录 callback；同一模型恢复使用时只替换旧 telemetry callback。主模型、摘要与 SDK 重试均经过真实模型开始/结束回调。
- 修改 `backend/agent_runtime/runner.py`：每次 invocation 建立本次 epoch observation，完成后读取实际 SQL Run 状态/产物引用结束；内置文件与 planning tools 使用真实 SDK 工具 callback。遥测尾部读取/更新失败不影响业务。
- 修改 `backend/agent_runtime/tools.py`：业务工具在真实执行范围创建/结束工具 observation。暂停为 `paused`，恢复产生新跨度；工具完成事件写入失败也结束失败跨度，原有业务异常/事务语义不变。
- 新增 `backend/tests/test_agent_telemetry.py`：假 Langfuse client、实际 graph/checkpoint、实际 SDK 摘要及重试、真实工具数据库边界和预算 callback 组合测试。
- 修改 `pyproject.toml`、`uv.lock`：可选 `telemetry = ["langfuse==5.0.4"]`。
- 修改 `.env.example`：只补充可选 LANGFUSE_PUBLIC_KEY / SECRET_KEY / BASE_URL / TRACING_ENABLED 设置与兼容说明。

## 输出合同与边界

白名单包括 run/session/已校验 UUID request/attempt/epoch、固定输入版本及 fact/memory 身份引用、模型名、实际 SDK 调用 UUID 与顺序、已知 input/output/total tokens、跨度耗时、受控错误码、工具注册名和草稿产物引用。只上传草稿工具的服务端定义 operation key；模型产生的 tool_call_id 可能包含任意文本，因此不上传。

没有 input/output 正文、简历/JD、私人回答、记忆正文、prompt、tool args、Authorization/API key、provider URL、异常正文或用户 ID。摘要 callback 只读取 usage。内置工具 callback 只接受当前已注册的文件/planning 名称。

特别说明：实测 SDK retry 的 `retry:attempt` tag 在 RunnableSequence 到模型步骤时不保留。没有稳定的逻辑重试父级可用，因此删除了未经证实的 retry_attempt 字段。通过共同 run/epoch/source、每次真实独立 sdk_call_id、model_call_index 和成功/失败状态展示实际调用尝试；不假造“本调用是逻辑第 N 次重试”。受控测试证明一次实际摘要失败及下一次重试产生两个结束的 generation，第二次有真实 usage。

未配置完整三项或 `LANGFUSE_TRACING_ENABLED=false` 时不 import SDK。配置后 SDK 构造、root/child start、update、end 故障均放行原业务。显式 `should_export_span=is_langfuse_span` 只导出 Langfuse 创建的 observation。没有 auth_check、每事件或每 Run flush，也没有全量 LangChain/OpenAI 自动 instrumentation。

## 验证与原始证据

每项检查都针对实际风险：缺少 span/正文泄漏则修接入与白名单；SDK 故障改变业务则修适配器；预算 callback 不再阻止模型则修组合；摘要重试漏调用则修模型层 callback；工具异常不结束跨度则修 finally；现有运行时恢复/幂等/正文过滤回归则修接点。

1. 首次 red：
   - 命令：`.venv/bin/python -m pytest backend/tests/test_agent_telemetry.py -q`
   - 结果：8 failed、3 passed、11 skipped。
   - 证据：`/tmp/task-13-telemetry-red.txt`。
   - 缺少真实 root/tool/summary observation 与故障 warning，符合新增功能缺失。
2. 首次 green，同命令：11 passed、11 skipped。
   - 证据：`/tmp/task-13-telemetry-green-first.txt`。
3. 新增 retry/budget/completion failure 边界：
   - 命令：`.venv/bin/python -m pytest backend/tests/test_agent_telemetry.py -q -k 'retry or budget or completion_failure'`
   - red：2 failed、1 passed、3 skipped、22 deselected。
   - 证据：`/tmp/task-13-telemetry-boundaries-red.txt`。
   - 实际发现：retry tag 未传递；tool.completed 写入失败遗漏 span 结束。已删除虚假 retry 序号并让工具 finish 放在 finally；费用 callback 原本保持正确。
4. 最终定向回归：
   - 命令：`.venv/bin/python -m pytest backend/tests/test_agent_telemetry.py backend/tests/test_agent_runtime.py backend/tests/test_agent_events.py backend/tests/test_tool_idempotency.py backend/tests/test_agent_context.py -q`
   - 结果：43 passed、41 skipped，6.39 秒。
   - 证据：`/tmp/task-13-telemetry-green.txt`。
   - skip 均为现有 fixture 的未配置临时 MySQL socket 分支。真实 SQLite、Deep Agents、SqliteSaver、主/摘要调用、暂停恢复、幂等、取消、正文过滤均通过。
5. `uv lock` 成功，证据 `/tmp/task-13-telemetry-lock.txt`；定向 `git diff --check` 无输出。

## 依赖与尚未验证项

官方 5.0.4 pyproject 要求 OpenTelemetry API/SDK/HTTP exporter >=1.45.0；锁选择 1.45.2，相应共享 proto/grpc exporter/semantic-conventions 与 googleapis-common-protos 必须更新。没有对正在并行使用的 `.venv` 执行 sync。上述 pytest 是当前已安装环境，根任务需在 A/B/C 完成后一次同步新锁并执行最终集成；可选真实 SDK 本地无网络 API 验证也留给根任务。

API 与参数通过官方 v5.0.4 源码核对、严格假 client 签名验证，不把假 client 中的记录称为 Langfuse 云端接收成功。真实云端投递/认证/服务端版本兼容性仍需完整 Langfuse 配置后验证；没有凭据验证，也没有网络导出确认。

官方证据：
- https://raw.githubusercontent.com/langfuse/langfuse-python/v5.0.4/pyproject.toml
- https://github.com/langfuse/langfuse-python/blob/v5.0.4/langfuse/_client/client.py
- https://raw.githubusercontent.com/langfuse/langfuse-python/v5.0.4/langfuse/_client/span.py
- https://langfuse.com/docs/observability/sdk/advanced-features#filtering-by-instrumentation-scope
- https://langfuse.com/docs/observability/sdk/upgrade-path/python-v4-to-v5
