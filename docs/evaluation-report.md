# 任务评测报告

当前状态：2026-10-30，本轮 T19 离线 core **30/30通过**，真实模型语义质量仍未验收。四次真实恢复与最终报告使用同一 invocation `9ce4a722-d79a-42ee-b637-cef24946d6a5`，没有借用旧轮恢复证据。T21已按用户要求取消，core保持30案，没有增加4个实时双向面试案例。

## 测试层次

| 组别 | 案例数 | 判定内容 | 当前证据边界 |
|---|---:|---|---|
| 定制材料core | 12 | 读源、补问、拒绝/取消、事务、重复草稿、来源冲突、长上下文 | 本轮T19 stub 12通过；实际SDK输入与公开输出记录随案例保留 |
| 持久旧任务durable | 8 | 原件身份、重解析、部分匹配恢复、结果回放、取消/归属、事务回滚 | 本轮T19 stub 8通过；live runner已实现，真实SDK/handler/SQL与本地模拟HTTP接线通过 |
| 真实进程恢复compose | 4 | 模型返回前、草稿提交后、checkpoint后、回答保存后四处SIGKILL | 本轮T19实际4通过/452.92s；均executed=true、SIGKILL/ExitCode137 |
| 文字面试interview | 6 | 追问、八轮上限、命令重放、迟到取消、冻结投递、确认记忆 | 本轮T19 stub 6通过；live runner与实际模型输入记录已用真实SDK/图/SQL和模拟HTTP验证 |

没有本次恢复证据时，默认stub只能执行26案、4案not_run，退出码2；这属于明确的未完整执行，不是30案全绿。四个恢复案例本身是合成模型的机械恢复实验，不会因为report选择live就变成模型质量证据。

## 本轮执行与证据

[最终报告](learning/test-records/raw/2026-10-30-t19/final-evaluation/evaluation/report.json)记录30 pass、0 fail、0 incomplete、0 not_run，executed_count为30；[manifest](learning/test-records/raw/2026-10-30-t19/final-evaluation/evaluation/manifest.json)、[恢复context](learning/test-records/raw/2026-10-30-t19/final-evaluation/recovery/context.json)和[恢复evidence](learning/test-records/raw/2026-10-30-t19/final-evaluation/recovery/evidence.json)绑定同一个本轮invocation。

两段耗时分别代表不同工作，不能混写：

- **452.92秒**：新生产依赖镜像上的四个真实进程恢复实验，4 passed，退出码0。四案均实际杀死进程并恢复，所有项目清理退出码为0。原始记录见[恢复日志](learning/test-records/raw/2026-10-30-t19/final-evaluation/recovery/pytest.txt)。
- **28.93秒**：CLI执行其余26个确定性案例，并严格核对、合并上述四个真实实验，输出30案报告，退出码0。这不是四个故障实验的执行时间。原始记录见[CLI日志](learning/test-records/raw/2026-10-30-t19/final-evaluation/evaluation/cli.txt)。

本轮使用 `resumate-t19-backend:5cd2b8fd52` 提供依赖，并挂载四案开始前一次复制的当前backend。实际源码分别保存在[恢复源码](learning/test-records/raw/2026-10-30-t19/final-evaluation/recovery/source-as-run.tar.gz)与[评测源码](learning/test-records/raw/2026-10-30-t19/final-evaluation/evaluation/source-as-run.tar.gz)。本轮结束后发现的显式HTTP client生命周期P2已修复，并分别通过26项传输/生命周期与74项关联验证；这些归档不会改成后续版本，也不证明该修复或待构建的新backend镜像已经通过本轮测试。完整执行范围见[归档说明](learning/test-records/raw/2026-10-30-t19/final-evaluation/README.md)及[评测子报告](learning/test-records/raw/2026-10-30-t19/final-evaluation/evals-report.md)。

stub模型边界次数、legacy业务attempt与live MockTransport的HTTP请求次数是不同口径。一次业务attempt可能包含格式fallback或反思的多次HTTP，不能把它们合并成供应商调用数或费用。

## 30案目录

- 定制12：normal-api、normal-confirmed-fact、normal-project、ask-technology、ask-metric、refuse-fabrication、cancel-waiting、tool-read-failure、tool-write-rollback、duplicate-draft、conflicting-sources、long-context。
- 持久任务8：parse-upload-stable-identity、parse-reparse-saved-job、match-partial-candidate-replay、question-result-replay、followup-result-replay、cancel-recovery、source-deleted-or-reassigned、business-write-rollback。
- 进程恢复4：recovery-model-before-return、recovery-draft-after-commit、recovery-checkpoint-before-terminal、recovery-answer-before-delivery。
- 文字面试6：interview-followup、interview-eight-turn-limit、interview-command-replay、interview-cancel-late-result、interview-frozen-submission、interview-feedback-memory。

完整输入及rubric见evals/cases和evals/README.md；额外tailoring用例不属于本次core30，不能把全部JSONL文件条数当core总数。

## 已发生的真实模型调用与3元预算

本阶段用户授权总额3元人民币，包含smoke、首批12案、失败和重试。已使用Qwen3.7-flash的既有配置进行两次请求：smoke失败，无输出/usage且当时诊断不足；正式normal-api返回HTTP403/insufficient_quota，无输出/usage。正式其余11案未执行。没有第三次付费请求。

账本保守预留每次1.21970880元，两次共2.43941760元，剩余0.56058240元，少于下一次最坏预留；预留不是已结算账单。不能删除未知预留或换新输出目录重置这笔授权。T19接线与本轮30案没有发起新的provider请求，也没有改动这份原账本；MockTransport/localhost测试中的合成usage和测试预算不占用、也不补充用户的3元授权。供应商额度与预算核算未解决前停止真实调用。

真实输出为空，因此没有可报告的有效生成Token、正常生成延迟、语义通过率或三次重复波动。失败延迟不代表任务生成速度。原始诊断、账本脱敏副本与调用配置见[T13 live记录](learning/test-records/2026-10-30-t13-live.md)。

## 已补齐的14案live接线

8个durable和6个interview原live分支直接返回not_implemented；这与费用阻塞是两个问题。14案live runner现已实现，补齐真实Harness/ChatOpenAI接线，复用同一预算账本，每次fallback/反思前预留，记录实际发送给模型的输入与公开输出，验证取消后迟到结果不能写入。机械接线使用MockTransport/localhost、真实SDK、真实图和SQL在本机验证并通过，没有调用供应商。持久任务的embedding仍明确使用确定性4维向量，本轮不证明真实检索质量。

不得用脚本答案的固定调用次数或强制不同问句作为真实模型oracle。数据库归属、唯一业务产物、冻结版本、人工确认和取消/回滚是机械不变量；反馈有用、回答忠于材料和不存在关键编造需要固定rubric审阅，不能由引用ID存在自动推出。

### 本地接线验证证据

- durable：八条实际HTTP/SQL轨迹通过；预算不足案例在发送前停止。来源变化与事务回滚只按真实触发点记录覆盖，HTTP403而未触发故障的案例明确失败。额外格式fallback和模型反思按实际HTTP次数预留费用，业务尝试次数单独计算。
- interview：真实模型输入中的当前System上下文、工具返回和分页材料与Run/epoch绑定；没有读取脚本模型的私有记录。9个基础live场景与原面试评测相关组27项通过；独立慢响应/预算中断2项通过（19.29s），不把两次运行相加冒充同一命令。
- 所有live模式的语义rubric保持unreviewed。模拟usage用于验证账本算法，不是实际供应商账单。

原始请求、SQL快照、成本记录、RED/GREEN日志及对应源码分别见[durable证据](learning/test-records/raw/2026-10-30-t19/task-19-task-live-evidence/manifest.json)和[interview证据](learning/test-records/raw/2026-10-30-t19/task-19-interview-live-evidence/summary.json)。

## 发布门禁

当前没有达到“live任务完成率≥90%、确认的关键编造/越权/重复业务写入为0”的通过证据，三次live重复也未执行。此报告不宣布真实模型质量已验收。API与SSE不含模型的性能见[性能报告](performance.md)，不能替代这里的Agent性能。

## 外部执行边界

GitHub Actions目前只有本地工作流定义，没有推送或远程运行结果。Langfuse已完成本地SDK生命周期兼容验证，但没有真实云端接收证据；离线日志与本地验证不代表云端观测链已经验收。
