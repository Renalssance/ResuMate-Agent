# T18 root diff 独立审查

2026-10-30，基线 cdde2c5，当前未提交源码。只读审查，不修改 root 文件，不重复运行 root 已绿测试。

结论：在可信 BYOK 操作者、单机/少量受邀账号以及当前 Vue 产品入口范围内，未发现需要修复的 P1/P2。以下实现正确。

- agent_runtime/factory.py、旧 agent/agent.py 与 interview_tools.py：实际 ChatOpenAI 同步/异步 HTTP transport 显式 follow_redirects=False，账号 timeout 传入，max_retries=0；root 新真实 SDK 测试捕获首个请求 timeout 并断言 307/308 重定向没有第二请求。evals/run.py 同类真实模型构造也已覆盖。
- agents/harness.py 和 vector/embedding.py：直接 OpenAI transport 禁跳转；Harness 保留账号 timeout，embedding 有限 30 秒。Harness 原 response_format fallback 与校验反思逻辑仍在；HTTP provider 原异常只用于分支判定，不再写日志/任务进度/反思正文。
- logging_config.py：prompt/response 改字符数与有限元数据，错误保留类型/状态而不是 traceback 或 provider 正文；验证错误只记计数。旧 chat worker 和工具错误输出同样收敛。root 合成 secret 测试经过实际错误处理入口，不只是静态 grep。
- app.py/.env.example：具体本地 origin，配置 trim，拒绝 wildcard，Bearer 客户端不需要 cookie credentials；允许来源的 Authorization 预检保持。现有显式部署来源继续有效。
- ApplicationsView.vue：复用项目已有 http(s) 来源链接规则，非 http(s) 不生成导航链接，保留 noreferrer；不引入全局 URL 过滤框架。
- deploy/nginx.conf：同源 API/CSP，SSE 独立关闭 buffering/cache；当前每个 document_parse HTTP 只接受一个文件，因此 11 MiB 代理请求上限与 API 10 MiB 文件上限不冲突。默认拒绝 script/object 外部载入，无新增 WS/T21。

证据读取：backend/tests/test_model_transport_security.py、test_llm_error_privacy.py、test_cors_origins.py、ApplicationsView.spec.ts，以及实际 production diff/call chain。root 报告其 RED/GREEN；本审查不把源码阅读记作另一次执行。CSP 最终生产 nginx/浏览器可用性仍由 root 真实 build 栈验证，不能由本审查替代截图或浏览器验收。

没有为不可达旧 frontend/script.js、假定恶意 operator 设置任意内网 URL、通用 SaaS SSRF、未知编码/竞态增加发现或补丁。T19 计划已读，尚未修改其生产文件，等待 T17 快照冻结。
