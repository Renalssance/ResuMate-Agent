# T16E 六条面试评测实施与证据

## 已实现

限定改动：`evals/cases/interviews.jsonl`、`evals/interview_runner.py`、`evals/interview_verifiers.py`、`evals/run.py`、`evals/fixtures.py`、`evals/README.md`、`backend/tests/test_interview_evals.py`；另按根授权只更新 `backend/tests/test_eval_long_tasks.py` 的目录数量/名称（24→30、普通执行20→26）。未修改 A/B 生产实现、旧 task_runner、T13 原12条案例或默认判定器。

六案走真实投递关联、创建面试、类型化命令、claim、Deep Agents 图、SqliteSaver、事务与 SQL；只把外部模型边界替换为 B 的共享 ScriptedInterviewModel。模型真正调用上下文工具，材料较长时读取 StateBackend 文件。没有 HTTP/队列/浏览器冒充，运行器直接执行已持久接受的 Run。SQL oracle 独立读取保存的材料/回答/命令/Run/事件/操作/记忆事实，并检查引用、唯一性、取消迟到写入和冻结来源。

固定六 ID：interview-followup、interview-eight-turn-limit、interview-command-replay、interview-cancel-late-result、interview-frozen-submission、interview-feedback-memory。当前 core 30 案；普通无新 Compose 证据的全 core 预期为 26 executed / 4 not_run，exit2。未在本子单元重跑整套；根代理统一执行。四条真实崩溃证据门禁不变。新六案 live 明确 not_run / interview_live_not_implemented，不创建 provider、预算或数据库。

## RED / GREEN 记录

- `/tmp/task-16-evals-schema-red.txt`：9 failed；首次缺少 verifier 与新目录。随后 `/tmp/task-16-evals-schema-green.txt`：9 passed / 1 deselected。
- `/tmp/task-16-evals-runner-red.txt`：2 failed / 1 passed / 13 deselected；新 runner 尚未接入，live 错误走配置分支。修正只影响新 runner dispatch / live 门禁，`/tmp/task-16-evals-live-green.txt`：1 passed / 15 deselected。
- `/tmp/task-16-evals-reference-red.txt`：1 failed / 16 deselected；独立 oracle 尚不能解析生产实际 `/self_summary` JSON pointer 引用。补充实际路径解析后 `/tmp/task-16-evals-oracle-green.txt`：11 passed / 6 deselected。
- `/tmp/task-16-evals-first-run.txt`：6 failed / 11 passed / 3.72s。六个失败共享一次执行：followup 真正 pass，eight-turn 在第七轮失败，其余四案按 CLI 停止为 not_run。B 确认共享模型夹具的 SDK read_file 分页解析问题；不是生产面试图错误。SDK JSON 输出使用范围头而非编号 gutter，页头和截断提示不能算正文偏移。B 修复并先完成双库分页 2 passed（`/tmp/task-16-runtime-pages-green.txt`），我未修改 B 文件。
- 最终命令 `.venv/bin/python -m pytest backend/tests/test_interview_evals.py -q`，`/tmp/task-16-evals-green-attempt.txt`：**17 passed in 9.70s**。包含实际六案一次执行、篡改证据拒绝、目录原输入保持和新 live 零调用门禁。仅 stub、无付费请求。

每次检查目的分别是检测新目录/判定器缺失、实际 dispatch 与 live 副作用、生产引用路径无法判定、共享夹具分页造成真实图提前失败、以及六条轨迹产物被篡改后仍误通过。失败即修对应评测点或交回夹具 owner；未以测试次数代替实际执行证据。

## 本轮稳定证据

`/tmp/task-16-eval-evidence/20261030T021139Z-3c7b7185/` 已复制整个真实 invocation，含 manifest、calls.jsonl、六条 case JSON、每案隔离数据库和 checkpoint、report。原 pytest 路径位于 pytest-235；稳定副本避免后续清理。最终 report：6 pass、0 fail、0 incomplete、0 not_run，executed_count=6；不是把 pytest pass 数粘成 eval verdict。

| Case | turns | Runs | 实际 scripted 模型调用 | oracle checks |
| --- | ---: | ---: | ---: | ---: |
| followup | 3 | 3 | 6 | 8 |
| eight-turn-limit | 8 | 9 | 28 | 8 |
| command-replay | 2 | 2 | 4 | 8 |
| cancel-late-result | 2 | 4 | 6 | 9 |
| frozen-submission | 3 | 3 | 6 | 9 |
| feedback-memory | 3 | 3 | 6 | 9 |

合计56次实际测试模型调用，0摘要调用。八轮里的额外调用来自真实工具分页，不能表述为56次供应商请求。取消案例两个屏障都在真实模型开始后；分别取消生成/结束会话，后续迟到输出没有业务结果；重试的新 Run 保留原答案。命令案例保存同 ID 同正文三次确认和冲突响应；记忆案例保存确认前空集合、确认后内容进入后续模型上下文、删除后失效与拒绝。

## 教学与边界

- 模型 stub 不等于 handler stub：数据库、命令幂等、工具读取、图执行和最终事务都能实际验证。
- 独立 oracle 必须读取具体 SQL/输入/输出，不复用生产验证器决定自身通过。
- 目录数量与 executed_count 不同；缺四条本轮 Compose 证据仍必须报告 not_run。
- 结构化输出引用存在只证明来源可追溯，不证明真实模型问题/反馈质量。合成模型的 Token usage 不报真实费用。
- 本六案使用 SQLite；不替代 A/B 双库、进程崩溃、HTTP、浏览器及后续 T17 性能检查。没有新增 WS、T21 设计或34案。用户已取消 T21。
- 原12案预算/隔离/语义审阅合同保持；不会启动新付费调用。本子单元不提交。
