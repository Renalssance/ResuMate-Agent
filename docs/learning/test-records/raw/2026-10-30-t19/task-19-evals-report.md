# T19 确定性评测 / CI 可运行性报告（已完成本子单元）

## 已完成

- `backend/tests/test_agent_recovery.py`：Docker 命令先使用 `shutil.which('docker')`，找不到才保留原 Desktop 路径；`RESUMATE_RECOVERY_IMAGE` 覆盖实际 api/worker/scheduler 镜像，默认保留既有本地镜像；evidence.source 使用实际 git HEAD 与本轮选定镜像。完整 backend 仍在四案开始前只复制一次，四案共用该快照。
- 新 `backend/tests/test_recovery_configuration.py` 验证 PATH、Desktop fallback、真实 fixture 写出的 HEAD/image/source 快照。没有启动 Docker 或模型。
- RED：`.venv/bin/python -m pytest backend/tests/test_recovery_configuration.py -q` → 2 failed / 1 passed，明确旧绝对路径和硬编码来源不符。日志 `/tmp/task-19-recovery-config-red.txt`。
- GREEN：同一命令 → 3 passed / 0.38s。日志 `/tmp/task-19-recovery-config-green.txt`。
- 实施前只读方案 `/tmp/task-19-live-gap-analysis.md` 区分当时 14 案 live 未接入与供应商余额问题。随后已获授权补齐本地接线，具体实现和验证见下文；没有付费调用。
- 保留 root 对 `evals/run.py` 的禁止 redirect 修改，并在同文件补齐评测预检/dispatch；`career_fixtures.py` 的 MySQL URL 支持未改动。

## 最终实际执行

B 已交接 fresh 生产镜像 `resumate-t19-backend:5cd2b8fd52`（sha256:83629f6b72ea003153d037cb314228ab268dc6f04f05360d05555fa544dd9455）及实际备份恢复通过的空闲窗口。新 context `/tmp/task-19-final-recovery-context.json`，invocation `9ce4a722-d79a-42ee-b637-cef24946d6a5`。四个实际 SIGKILL 恢复案 **4 passed /452.92s，exit0**；随后 CLI 执行其余26案并严格合并这四案的同轮证据，**30 pass /0 fail /0 incomplete /0 not_run，exit0 /28.93s**。452.92秒是实际故障实验耗时；28.93秒是其余26案执行及30案汇总耗时，不能把后者称作全部故障实验耗时。旧 T14/T16 证据没有抵扣。本轮没有失败或重跑。

远程 GitHub Actions 只读结论 `/tmp/task-19-ci-review.md` 未发现已启用入口的 Linux 路径/缺依赖阻碍，不冒充远程执行。14 案 live 入口已在本地模拟 HTTP 下验证；原 12 案及新增 14 案真实供应商语义质量仍未验收，不重置旧 3 元账本。

## 获授权后补齐 durable/shared live 接线（离线已完成）

`/tmp/task-19-live-gap-analysis.md` 为实施前只读结论，随后 root 明确批准补实现、只做本地模拟 HTTP，不消费既有3元。局部计划 `/tmp/task-19-live-implementation-plan.md`。首次写计划遇 ENOSPC 已暂停，恢复2.1GiB后才继续小源码/无Docker测试；未自行清其他容器或数据。

- 新 `evals/task_live_model.py` 使用真实 AgentHarness prompt/schema/validation/reflection，以及实际 OpenAI客户端JSON请求序列化。只在评测内实现最后HTTP边界，逐次guard→预算预留→发送→usage结算→公共输出记录→故障/取消hook。配置上限固定，格式fallback/反思不能突破output cap；无SDK自动retry/redirect。实际请求体（无headers/凭据）、公共文本、Run/attempt/epoch均可审阅。
- `BudgetCallback.reserve_call/settle_call` 抽出原逻辑，原callback接口保留；`CallRecorder.start_call`复用记录。原12案预算及隔离/隐私检查通过。make_live_model仅加可选MockTransport参数，不改变默认网络策略。
- `task_runner` 八案 live 使用真实handler/SQL，仍明确 deterministic embedding；providerHTTP次数与业务attempt分开。旧Run重放和第二新Run当前结果绑定；允许模型两次文本相同，未改provider答案凑通过。
- 取消/来源变更发生在实际HTTP成功返回且已结算后、返回handler之前，后续真实guard和最终SQL fence阻止迟到写入。实际所有权mutation单独记录；HTTP失败没有执行mutation时明确fail，不假称覆盖。
- `run.py` 两类live均先完整budget/credentials预检，并继续同一invocation ledger；预算不足保存incomplete、后续not_run。A的interview实现独立记录，最终报告 `/tmp/task-19-interview-live-report.md`。未增加供应商费用。

### RED / GREEN原始记录

|范围|RED/失败及原因|GREEN|
|---|---|---|
|legacy HTTP预算/guard|`task-19-task-live-red.txt` 4 failed：入口未实现；第一次green 3 failed/8 passed，重复call_id参数和HTTP纯测试错误使用无seed用户造成usage FK；均已定位修复|`task-19-task-live-green-2.txt` 11 passed /2.94s，含原预算7项|
|八案真实HTTP服务SQL|`task-19-task-runner-red.txt` 9 failed：旧runner无HTTP；第一green 8 failed/1 passed是新增测试误读semantic.items为semantic.status，八案业务oracle均已过|`task-19-task-runner-green-2.txt` 12 passed /19.71s：新8案+预算失败1、旧stub八案回归1、两类预检2|
|共享CLI与原隔离/公开输出|两类预检先 `task-19-live-preflight-red.txt` 2 failed：旧not_implemented|`task-19-shared-live-green.txt` 5 passed /9.07s：本机HTTP返回403后下案零发送，同账本1未知预约；原隔离/公开输出/未知费用回归|
|live来源oracle|`task-19-source-oracle-red.txt` 1 failed：固定HTTP次数误判格式重试；第一次green 2 passed/1 failed暴露未触发删除却重建岗位的eval错误|`task-19-source-oracle-green-2.txt` 3 passed /2.80s：额外格式请求不冒充业务单元、真实来源变更仍通过、403未变更明确fail并保留SQL|

这些计数是不同定向命令，不能相加冒充一次全套。测试使用合成usage；不是实际供应商收费。

稳定实际产物 `/tmp/task-19-task-live-evidence/manifest.json` 指向八个pass场景+一个预算incomplete场景，每份有 request配置、实际HTTPJSON、calls、budget、完整案例/SQL oracle。另 `source-fault-final/` 保存403导致未覆盖来源变化的实际fail：3次未知预约，停止后续场景动作。最初pure HTTP fallback/guard单元的通过原始日志已留存；完整局部pytest临时目录可能被并行pytest retention清理，root已获最终全量用稳定basetemp保存其calls.jsonl的建议。

无模型供应商请求；旧本机3元账本完全未修改。真实模型语义复核仍unreviewed，live质量门禁仍未达成。新的四恢复和最终30案已完成，见本报告最终实际执行与证据路径。

### 最后一个实际假覆盖修复 / 冻结

- rollback 原场景将 fault_kinds 固定写成四类，模型仅setup成功、其余全部403时曾错误pass；新增实际HTTP反例 `/tmp/task-19-rollback-oracle-red.txt` 1 failed，准确暴露该假通过。
- 现在 fault_kinds 只在真正的 artifact INSERT 注入点追加。`/tmp/task-19-rollback-oracle-green.txt` 2 passed /2.88s：正常四事务回滚pass，13次本地HTTP（setup1成功、四业务各3次403）的反例明确fail且fault_kinds=[]。未知12次预约保留，金额为合成测试，不是用户账本。
- 该反例实际请求/公开输出/SQL/预算存 `/tmp/task-19-task-live-evidence/rollback-fault-final/`；C相关执行源码复制到 `source/`。先前 `/tmp/task-19-task-live-evidence/source-fault-final/` 记录未覆盖来源变更fail。
- C评测实现与tests现已冻结；`evals/README.md` 已同步14案实现接线和离线/付费边界（A最终interview统计由其报告补充）。未修改生产Harness/handler/worker。

root 全后端回归无需新增环境变量；可沿用 `PYTHON_DOTENV_DISABLED=1 RESUMATE_TEST_MYSQL_SOCKET=/tmp/resumate-mysql-t02/mysql.sock .venv/bin/python -m pytest backend/tests -q --basetemp=/tmp/task-19-backend-final-state`，若该路径已用请指定新路径。普通全套不要设置 RESUMATE_COMPOSE_TEST；四真实恢复单独在fresh镜像窗口运行。建议保持无 ambient模型凭据/模型名，所有新HTTP测试显式使用synthetic key与MockTransport/127.0.0.1，不加载主.env。


## Interview live 最终交接

A 已冻结 `interview_runner`、`interview_records`、`interview_verifiers` 及真实 HTTP fixture：27 项定向通过，根审查等待边界另 2 RED → 2 GREEN，合计覆盖 29 个不同测试，不冒充一次全套。实际 SDK System 必保留块、工具返回、分页上下文与公开 InterviewStep 都从真实消息记录；取消在实际响应已结算后、图写入前阻塞，SQL fence 拒绝迟到结果。有限等待按配置请求时限 × 剩余调用数加收尾余量，不再误裁合法 16 秒响应。稳定证据 `/tmp/task-19-interview-live-evidence/`，HTTP 请求均为本地合成响应，语义 unreviewed。


## 本轮四恢复与30案证据

- 精确报告：`/tmp/task-19-final-evals/20261030T034423Z-3feb4818/report.json`；同目录 `manifest.json`、`report.md`、`cases/`、`calls.jsonl`。manifest invocation 与恢复 context 完全相同。
- context `/tmp/task-19-final-recovery-context.json`，evidence `/tmp/task-19-final-recovery-evidence.json`；原始日志 `/tmp/task-19-final-recovery.txt`、`/tmp/task-19-final-evals.txt`。
- 完整原始目录 `/tmp/task-14-recovery-artifacts-9ce4a722-3paycpej`；`task-14` 仅是既有脚本目录前缀，实际内容均为本轮 T19 新执行。当前 backend 在开始前一次复制到其 `source/backend`，基于 HEAD `cdde2c53c6a80e271c2d185bef80b179d8e2fcb7` 加当前工作树修改。fresh 镜像提供依赖，实际四案运行这个固定源码挂载；没有把旧镜像改名。
- 四案均 `executed=true/status=pass`，实际 `SIGKILL/ExitCode137`。模型边界开始次数依次1→4、2→3、3→3、2→5；这是确定性模型边界，不是供应商HTTP调用数或实际费用。前三案 attempt1→2/epoch1→2；最后回答投递中断案 attempt保持1、epoch1→2。全部只有一份版本、操作及产物，最后案保留同一action回答和事实引用。
- 四个独立 Compose 项目都 `down -v --remove-orphans` 返回0。窗口已交还 root，后续全后端/31浏览器由root负责，本子单元不重复执行。
- 可公开归档目录 `/tmp/task-19-public-evidence/` 包含当轮context/evidence、源码tar、四案SQL观察/命令/容器日志、最终30案报告和原始日志；不复制运行数据库/checkpoint、`.env`、凭据或JWT。原始完整运行状态仍保留在上述独立临时目录。

### 教学边界

1. fresh 镜像、真实 SIGKILL、数据库/checkpoint恢复，与本地 HTTP 合成模型响应验证是不同层次。前者证明恢复不重复业务写，后者证明真实SDK请求/预算/guard/SQL接线；均不证明供应商模型语义质量。
2. stub 模型边界次数、legacy run_schema业务attempt、MockTransport实际HTTP次数分列；fallback/reflection会使一次业务attempt包含多个HTTP，不能混加。
3. 两个新增实际可达反例证明“模型失败”不能冒充“来源变化/事务回滚已发生”：oracle必须从真实mutation/INSERT注入点采集覆盖，固定填写fault名称会制造假通过。
4. 旧3元账本未变，实际供应商额度不足的未完成质量验收仍保留。30案stub全通过不把live语义从unreviewed升级。


## 执行版本与后续修复边界

本归档只证明 invocation `9ce4a722-d79a-42ee-b637-cef24946d6a5` 的实际执行版本：fresh 镜像 `resumate-t19-backend:5cd2b8fd52` 加四案开始前固定的 backend 源码挂载。`recovery/source-as-run.tar.gz` 与 `evaluation/source-as-run.tar.gz` 保留本轮实际源码，不随当前工作树后续修改更新。

本轮结束后正在修复的显式 HTTP client 生命周期 P2 不在这份执行源码中；后续新 backend 镜像及其验证应另行记录，不能用这次30案结果宣称后续修改已验证。root 的完整后端回归为1172 passed /19 skipped /286.60s，属于独立命令，也不能加进30案数量或混进上述两段耗时。
