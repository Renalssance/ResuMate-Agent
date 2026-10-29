# T13 C 单轮审阅修正

范围：仅 `backend/agent_runtime/telemetry.py` 与 `backend/tests/test_agent_telemetry.py`。
依据：`/tmp/task-13-telemetry-review-report.md` 中唯一 P2 finding。

`SDKToolTelemetry.on_tool_end` 现在只通过 `isinstance(output, ToolMessage)` 与 `output.status == 'error'` 识别错误结果，结束为 `failed` 并写固定受控代码 `tool_result_error`；成功结果仍为 `succeeded`。生产逻辑不读取或上传消息正文，没有调整其他遥测、业务或依赖行为。

回归使用实际 `FilesystemMiddleware` 的 `read_file.invoke`，执行真实临时文件成功读取和不存在路径读取；两者均返回真实 ToolMessage 并经过真实 LangChain callback。文件内容/缺失路径的错误正文都包含私人内容哨兵，验证导出元数据中不存在该哨兵。

- Red 命令：`.venv/bin/python -m pytest backend/tests/test_agent_telemetry.py -q -k sdk_file_result`
- Red 结果：1 failed、1 passed、28 deselected；缺失路径被错误记为 succeeded，失败与审阅发现一致。
- Red 原始输出：`/tmp/task-13-telemetry-fix-red.txt`。
- Green 命令：`.venv/bin/python -m pytest backend/tests/test_agent_telemetry.py -q`
- Green 结果：16 passed、14 skipped，3.81 秒；skip 是未配置临时 MySQL 分支。
- Green 原始输出：`/tmp/task-13-telemetry-fix-green.txt`。

精确修改前文件保存在：
- `/tmp/t13-telemetry-pre-fix/telemetry.py`
- `/tmp/t13-telemetry-pre-fix/test_agent_telemetry.py`

仅本轮修正的 diff：`/tmp/t13-telemetry-scoped-fix.diff`。
没有 package sync、全后端运行、Git commit、真实模型/Langfuse 请求。交回根任务安排一次 scoped rereview；锁定环境集成仍由根任务负责。
