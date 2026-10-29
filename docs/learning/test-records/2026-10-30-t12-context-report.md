# T12 上下文/SDK交付

工作区 `/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`。未commit；未改runner/worker/agent_runs/settings/DB共享文件。

## 已实现

- `context.py` 保留既有T09 capture/read/changed合同，新增ContextBundle。required含任务/Run/Session/固定版本、不可编造/不可自动提交约束、确认事实原文、待回答动作、本Run提交回答、现有草稿引用和Run冻结ID内仍有效的确认记忆。
- `model_for_user` 要求显式context_window_tokens，即使名称为已知模型且自定义端点也不猜容量；缺失报model_context_not_configured，输出reserve无空间报context_budget_exceeded。ChatOpenAI显式profile传实际capacity，max_tokens仍为输出上限。
- `BusinessContextMiddleware` 用相同name替换默认SummarizationMiddleware；每次主请求在SDK计数前注入SQL required；每次摘要尝试也重读SQL、注入required并守卫执行权。必保留+system/tools超预算时，在任何provider调用前明确停止，不截断确认事实。
- 继续复用SDK摘要分区、摘要调用、历史外置、overflow恢复和重试。SDK默认最多3次摘要尝试的RunnableRetry保持原策略；只在其bound内部加fence/注入，并排除业务RunError重试。真实SDK重试测试在第一次模拟provider失败后使Session失效，确认第二次provider请求没有发生。
- 长上下文业务工具在图执行内用StateBackend.write保存 `/inputs/{runId}/resume.json`、`resume-text.json`、`job.json`、`job-text.json`、`match.json`，返回manifest/稳定artifact ID/用途/路径/预算估算。短输入仍返回原dict合同。原SQL快照仍是before/sourceRefs权威。
- `/inputs/**` 通过SDK FilesystemPermission只读；模型尝试write_file被拒绝，SQL和checkpoint镜像仍为原文。SDK conversation_history仍正常写入checkpoint。
- 单长段落是支持输入的实际问题：SDK read_file按行分页，单行超读限可能无法续读；长字符串镜像编码为1000字符textChunks，按顺序空字符串拼接能逐字还原，JSON物理行可分页。短字段保持原结构。业务skill明确读取与还原合同。
- 统一保守规划系数：SDK count_tokens_approximately(chars_per_token=1.0,use_usage_metadata_scaling=False)，包括system/tools。SDK主请求仍扣一次5%余量和max_tokens，应用没有从已扣预算再扣一次。摘要是独立请求，按同容量/reserve单独核算。

## 稳定调用接法

`build_agent(user_id, saver, run_id=..., epoch=...)`不变，runner不需要预填files。业务工具自行写StateBackend。middleware通过`tools.context_bundle`使用`tools.SessionLocal`，现有测试fixture只patch tools与runner的SessionLocal即可。

`DraftModel`新增测试用`profile={'max_input_tokens':64000}`及`max_tokens=1024`。E2E fixture由父代理维护，可调用原model_for_user取得无网络构造的已校验模型，再取profile/max_tokens交给BrowserDraftModel。

## 真实验证与结果

最终命令：
`RESUMATE_TEST_MYSQL_SOCKET=/tmp/resumate-mysql-t02/mysql.sock .venv/bin/python -m pytest backend/tests/test_agent_context.py -q -s`

结果 **13 passed**（SQLite+临时MySQL），日志 `/tmp/resumate-t12-context-final.txt`。

长案例使用真实DeepAgents与磁盘SqliteSaver，合成长中文简历/JD/历史match、确认事实、确认记忆、补问、实际actionId、草稿引用。SDK摘要的确定性回复故意不保留事实；最终每个主请求及摘要请求仍含SQL required正文。发生摘要后暂停，run_agent关闭saver；重建agent/saver，提交回答后完成唯一合法草稿，before与sourceRefs从read_file原文取得，确认事实/回答来源合法。测试也断言只读镜像未改、原SQL快照未变、最终请求含action及version ID。

最终SQLite长案例（全部是估算，非provider usage）：
- 单独原始固定资料快照：88620（不包含工具/system；不可与主请求声称精确同口径费用节省）。
- 实际主请求完整估算（含工具定义和system）：13567,19736,16826,20140,20134,20745,16735,19620,20250,16942,20253。
- 实际摘要请求完整估算：11443,8559,11873,11867,12478,11384,11969。
- 摘要调用7次，主调用11次；容量30000，输出reserve1024，SDK输入预算27476；所有实际请求估算均在预算内。
- MySQL长案例因日期精度差异快照88599、主请求13525–20519、摘要8510–12252，同样7次摘要且合法草稿。
- Stub证明机制/恢复/来源合同，不证明摘要语言质量或真实费用节省。T13须将主模型、摘要、摘要重试每次实际provider usage和费用全部计入。

此前范围回归在SQLite上 **50 passed**（test_agent_context/runtime/tailoring_context/resume_versions/tool_idempotency）。该次误填MySQL socket `/tmp/resumate-mysql/mysql.sock` 导致49项MySQL fixture连接错误，没有产品失败；未把该运行宣称双库通过。最终仅用正确socket重跑本文件，父代理负责全套双库回归。

红测证据：`/tmp/resumate-t12-context-red-config.txt`（缺容量未拒绝、3k系统工具超限仍发模）；`/tmp/resumate-t12-context-red-bundle.txt`（ContextBundle缺失）；`/tmp/resumate-t12-context-red-pagination.txt`（长字段无法按块无损还原，随后修复）。已有基础runtime回归 `/tmp/resumate-t12-context-green-basic.txt` 10 passed,9 skipped。中间长案日志也保留在 `/tmp/resumate-t12-context-*.txt`。

## 明确SDK私有依赖与限制

锁定DeepAgents0.7.32、LangChain1.4.7、LangGraph1.2.18、sqlite saver3.1.2（core本机1.7.1）。薄middleware依赖SDK `_lc_helper`、`_lc_helper._summary_model`（RunnableRetry的bound/retry_exception_types字段）、`summary_prompt/trim_tokens_to_summarize`、`_input_budget`与`_count_tokens`。升级必须定向复跑长案例和summary_retry撤销测试。没有自写摘要循环。

当前生产runner使用同步graph.stream；middleware实现此真实入口。未扩展不使用的异步agent入口。省token的工作副本不改变T09审阅/SQL快照，记忆也不成为简历经历证据。
