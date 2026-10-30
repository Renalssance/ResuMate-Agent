# T18 模型传输独立审查与生命周期修复

审查范围为本次模型客户端、旧 Chat/Harness/embedding、日志、CORS 及 Applications 外链。发现并已修复一项 P2：显式注入 OpenAI DefaultHttpxClient / DefaultAsyncHttpxClient 后，绕过上游负责 GC 关闭的 SDK wrapper；旧 Chat 的正常完成和断开在模型引用释放后，HTTP transport 没有随之关闭。没有把这一反例描述为已发生的连接耗尽事故。

最小修复新增 `backend/model_transport.py`，仅继承公开默认客户端并恢复上游同步 close / 活跃事件循环中的异步 aclose finalizer。已经显式关闭的客户端不会重复关闭。没有改变模型/图函数签名，没有新增连接池、缓存、重试或私有 SDK 依赖。以下七个构造点改为导入该类型，原 follow_redirects=False、timeout、max_retries 参数不变：

- backend/agent/agent.py
- backend/agent/interview_tools.py
- backend/agent_runtime/factory.py
- backend/agents/harness.py
- backend/vector/embedding.py
- evals/run.py
- evals/task_live_model.py

自动 GC 释放不代表每次请求结束立即销毁；测试在合法图回调已退出、弱引用确认对象已释放后断言关闭。异步 finalizer 与上游相同，依赖仍存活的事件循环。实际完成/断开两种生产路径均已覆盖。

## 行为证据

- `/tmp/task-18-client-lifecycle-initial-observation.txt`：初次观察时仍有合法回调引用，不作为泄漏证明。
- `/tmp/task-18-client-lifecycle-red.txt`：两项实际旧 Chat 正常完成/断开反例，2 failed；对象弱引用为空而 transport closes=0。
- `/tmp/task-18-client-lifecycle-formal-red.txt`：正式生命周期测试，4 failed / 2 passed。
- `/tmp/task-18-client-lifecycle-green.txt`：26 passed / 1.79s。6 项生命周期及 20 项真实 SDK 307/308 禁止跳转、超时、同步/异步构造路径。
- `/tmp/task-18-client-lifecycle-related-green.txt`：74 passed / 63.98s。真实 Harness、embedding、Chat keepalive/事件、错误脱敏、live 模型/runner、面试 live 接线、预算及 eval runner 关联回归；仅本地合成 HTTP，没有付费调用。

执行命令（在当前 worktree）：

```text
.venv/bin/pytest backend/tests/test_model_transport_lifecycle.py backend/tests/test_model_transport_security.py -q
.venv/bin/pytest backend/tests/test_agent_harness.py backend/tests/test_embedding.py backend/tests/test_chat_keepalive.py backend/tests/test_llm_error_privacy.py backend/tests/test_agent_events.py::test_custom_model_endpoint_requests_stream_usage backend/tests/test_task_live_model.py backend/tests/test_task_live_runner.py backend/tests/test_interview_live.py backend/tests/test_eval_budget.py backend/tests/test_eval_runner.py -q
```

其余所审路径没有确认的 P1/P2：默认错误/日志只保留安全元数据；模型与 embedding 的实际请求边界禁重定向且有限超时；显式 CORS 和外链 http(s)/noreferrer 行为符合计划。未扩大对抗假设，也未重复全后端套件。

## 交付状态

产品源码已冻结，root 已独立审查 helper 与替换点无追加问题。后端镜像已更新：

- tag：`resumate-t19-backend:7a3122655a-lifecycle`
- ID：`sha256:eda8e67eef1ab340f033ad368d00b10bcc43009fae0ff32bb32df152cc670f89`
- 证据：`/tmp/task-19-backend-revision-7a3122655a`
- 构建方式：FROM 已实际 fresh 验收的 `resumate-t19-backend:5cd2b8fd52`，COPY 完整当前 backend。pyproject、uv.lock、worker.Dockerfile 与原 fresh 源码直接比对一致。它是透明的源码修订镜像，不声称重新安装全部依赖。
- 真实新镜像内运行 `runtime-probe.py`，没有生产源码挂载；同步/异步 × 307/308 × 自动GC/显式关闭，共8项通过。timeout=7、max_retries=0，每项只发1个合成HTTP请求、关闭1次。日志与JSON均保留；无外网/供应商调用。

构建后运行窗口已交回root继续浏览器验证。未重复已通过的备份恢复、四项SIGKILL实验或全部后端。

## 浏览器测试夹具的独立修复

root完整31项浏览器结果为30 passed/1 failed，唯一失败为岗位解析重试示例。只读确认 `e2e_legacy_fixture.py` 的进程内 `_calls` 会随每次文档子进程重新归零，导致每次手动重试都再次得到前三次503。仅测试夹具改为在当前 `RESUMATE_E2E_ROOT` 用固定文件保存该已存在单输入的整数计数；没有更改产品逻辑，没有hash或通用状态框架。

新增 `backend/tests/test_e2e_retry_fixture.py` 以真正独立Python进程覆盖首进程3×503→新进程200，并确认 ALWAYS_FAIL仍503、普通输入200。

```text
.venv/bin/pytest backend/tests/test_e2e_retry_fixture.py -q
```

`/tmp/task-18-e2e-retry-fixture-red.txt`：1 failed/2.07s；`/tmp/task-18-e2e-retry-fixture-green.txt`：1 passed/3.44s。实际浏览器受影响场景由root补测；本报告不把分次结果合并成同一轮31全绿。
