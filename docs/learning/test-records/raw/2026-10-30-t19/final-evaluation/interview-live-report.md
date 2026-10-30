# T19 面试 live 评测接线报告

已完成并冻结本子单元；没有付费请求、真实供应商连接、Docker/浏览器服务、git 操作或面试产品 runtime 修改。

## 实现范围

- `evals/interview_runner.py`：live 使用 E 的 `make_live_model`/共享 invocation `BudgetConfig`，真实 ChatOpenAI → Deep Agents → SqliteSaver → 工具 → InterviewStep 校验 → SQL。stub 保留原模型与六种轨迹，但证据不再依赖其私有 calls/context/before_generate 字段。
- 新 `evals/interview_records.py`：统一 recorder 从实际 SDK 请求的当前 System 必保留块、get_interview_context 和 read_file 返回采集证据。Human 中旧摘要文本不算当前块；分页只在连续 offset 读齐后重建上下文，并记录来源 SDK call IDs。无数据库读取冒充模型输入。仅保留公开响应文本、工具参数；不保留隐藏推理、认证头或供应商错误正文。
- `evals/interview_verifiers.py`：新增实际必保留块与 SQL Run/session/interview/turn/attempt/epoch 对应检查；取消后调用数不得增加；删除“live 未实现”旧说明。引用存在只证明结构与来源，语义保持 unreviewed。
- 新 `backend/tests/test_interview_live.py` 与 `interview_live_fixture.py`：外部 HTTP 使用 MockTransport，图、checkpointer、工具、受理、命令、guard、结果提交和 SQL oracle 均真实。

## 结果与故障语义

每个 generation 后读取真实 Run。失败时停止场景后续回答/命令，不用未产生的问题继续驱动场景。预算 stop_reason 优先映射 `incomplete/budget_exhausted`，不包装为 worker_failed；403 为 fail，并保留一次已预留但 usage 未知的调用。没有 usage 时不会假称费用为零。

取消/finish 在真实 InterviewStep 响应返回、BudgetCallback 已结算之后阻塞，再提交真实命令；释放迟到响应后，Run cancelled，旧回答保留，业务 turn/feedback/event/operation 不新增，重试产生新 Run。保留取消时已结算数量和公开 step。

根审查发现旧固定 entered.wait(15) 会裁掉合法 live 请求。新增真实 HTTP 响应延迟 16 秒反例，旧实现失败；另测首 Run 成功、第二 Run 第三次调用后预算停止，旧实现仍空等 15 秒。修复以 `request_timeout_seconds × min(剩余全局调用数, 剩余单案调用数) + 20 秒收尾余量` 为有限响应等待（至少允许一次预检），生成线程失败/完成主动唤醒。响应未在此界限返回时先 SQL cancel fence，再按已配置请求时限 + SQL 余量收尾；若线程仍未退出，不输出案例结果。预算提前停止保留其原始 error_code。

## RED → GREEN

1. 新核心测试 6 RED：缺 SDK 记录器、live 没有成本/实际 HTTP；403 和不足预算仍假 pass。初稿语义评分断言曾使用错误键，已按现有 items 格式纠正后保存真实 RED。
2. 首轮 6 GREEN / 7.54 秒；中间一次 3 fail 是合成 HTTP fixture 的 JSONPointer 写法与超长分页样本跨摘要但 fixture 无持久分页状态，未修改产品实现；改为合法 `/self_summary` 和仍触发真实分页的约 13.5k 字符材料。不宣称本项测过超长摘要质量。
3. 加入六类 live 轨迹和篡改 required.runId 的 oracle 反例：9 pass / 1 RED；修正 oracle。
4. 新测试 + 原 interview 评测组：**27 passed / 19.75 秒**。包括原六种 stub 真实轨迹以及预检/SQL oracle 回归。
5. 根审查等待边界：**2 RED / 34.48 秒 → 2 passed / 19.29 秒**。只重跑受影响的两项，未重复已绿无关组。新增测试最终共 12 项，原组 17 项；两次最后验证合计覆盖 29 个不同测试。

原始日志：
- `/tmp/task-19-interview-live-red-corrected.txt`
- `/tmp/task-19-interview-live-green.txt`
- `/tmp/task-19-interview-verifier-red.txt`
- `/tmp/task-19-interview-final-green.txt`
- `/tmp/task-19-interview-wait-red.txt`
- `/tmp/task-19-interview-wait-green.txt`

稳定证据：`/tmp/task-19-interview-live-evidence/`（约 5 MB；独立于 pytest 清理目录）。各场景 `result.json` 含真实 SQL snapshot 与公开输入/输出、`calls.jsonl`、`http.jsonl`（仅合成请求 JSON 无头）、`budget.json`；另有 summary.json、最终本单元源码副本与上述原始日志。不复制数据库/原始 checkpoint。

六种 live 轨迹在 MockTransport 下的 HTTP 调用数：追问 6、八题上限 28、命令重放 4、取消/finish 8、冻结资料 6、记忆确认/删除 6；另分页 15。403 为 1 次未知 usage；初始预算不足 0 请求；取消阶段预算不足 3 次已结算请求。两次合法取消均无取消后追加调用。

## 限制与后续

这些是 live 入口/真实 SDK HTTP 协议/实际 SQL 行为的无付费验收，HTTP 响应确定性合成。没有声称真实供应商模型质量、完整 30 案统一评测或部署端到端已通过。共用 run.py 预检/dispatch、BudgetCallback 和 evals README 由 E 负责；最终统一验收由 root 调度。

下一工作是 5–8 分钟真实产品教学录屏，等待 root 完成 fresh build 与普通浏览器后再分配端口；当前没有启动录制、没有占用测试端口。
