# T13 A：合成案例、模型 fixture 与纯验证器

工作树：`/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`。
基线：`4f4f201`。未提交 Git；未读取凭据；未发送真实模型请求。

## 完成内容

- `evals/cases/core.jsonl`：12 个固定 ID 案例，类别 3 正常、2 补问、2 拒绝/取消、2 工具失败、1 重复保存、1 来源冲突、1 长上下文。
- `evals/fixtures.py`：`load_cases`、隔离环境设置之后才导入 SQL 的 `seed_case`、实际 `BaseChatModel` 的 `make_model`。模型只发真实 SDK 工具调用，不直接写业务数据。
- `evals/verifiers.py`：`verify(case, output, db_snapshot)`，只处理独立 SQL 快照的普通字典，不调用生产保存/校验函数，不导入项目数据库。独立核查唯一草稿/操作/事件、owner/版本/action 来源、before、原简历、待审阅状态、未自动改变事实/记忆、真实 waiting/cancel/fault/replay/summary/checkpoint 覆盖。
- `backend/tests/test_eval_verifiers.py`：21 个用例，包含重复版本、错输出引用、错 before、错 fact revision、错简历版本、错事实 owner、错 source_refs、回答跨 Run/缺失/未提交、自动确认、主简历覆写、新事实、重复 operation/event，以及取消、回滚、长上下文、语义状态和合法 no_draft 拒绝。
- `backend/tests/test_eval_fixtures.py`：4 个用例，检查类别及前端来源独立、60 个不同项目、精确 context before/answer ID、摘要调用不会推进主步骤、从真实分页格式提取原文字段和 source_refs。

接口协作记录：`/tmp/t13-data-contract.md`。B 独占运行器/故障注入/独立 SQL snapshot；没有为 eval 增加生产故障开关。

## 测试证据与失败意义

1. `uv run pytest backend/tests/test_eval_verifiers.py -q`，先使用恒通过 verifier 占位实现：`/tmp/t13-verifiers-red.log`，**19 failed, 1 passed**。这是可观察的负向证据：如果 verifier 不核对数据库不变量，所有损坏快照会被误判通过。
2. 同命令实现校验后：`/tmp/t13-verifiers-green.log`，**20 passed**。第一次 green 尝试发现良性快照漏写 checkpoint 重开证据并失败；补齐测试输入的真实契约后通过，未放宽规则。
3. `uv run pytest backend/tests/test_eval_fixtures.py -q`：`/tmp/t13-fixtures-red.log` 为实现前不存在 fixtures 模块的收集失败；`/tmp/t13-fixtures-green.log` 为实现后 **3 passed**。最初 red 是缺模块，不冒充算法缺陷证据。
4. 最终有新增 refusal/paged-source 用例后，`uv run pytest backend/tests/test_eval_verifiers.py backend/tests/test_eval_fixtures.py -q`：`/tmp/t13-cases-final-unit.log`，**25 passed**。新增两案核对合法无草稿拒绝与分页 JSON 精确来源；未重复跑无关回归。

运行器 B 的实际长案例证据（本 A 未重复运行）：
`/tmp/t13-long-smoke/20261029T175632Z-12564175/cases/long-context.json`。
A 已读取该结果：succeeded，8 次实际 SDK summary、5 次文件读取（4 个输入文件，其中 resume 重读），waiting_input 时零草稿、checkpoint 重开、required context/answer/artifact refs 保留，24 项 deterministic 检查通过。最终完整 12 案由主控执行，A 不重复跑整套。

## 具体判断与边界

- 前端案例只有 React/TypeScript 表单、字段校验和错误提示，未复用旧 DraftModel 固定补写 API/数据库的句子。
- 确认指标包含 p95、180ms→90ms、单订单查询与测试环境限定。补问明确无 Kubernetes 生产经历/无可靠性能测量。冲突必须真实等待回答。
- 拒绝案例允许基于真实职责的草稿，也允许业务真实记录 failed/no_draft。即时拒绝不强迫再问一次；不得把 agent_failed 当合法拒绝通过。语义是否实际拒绝编造仍需独立审阅。
- 长案例生成 60 个不同项目、较长岗位与已有匹配意见，沿用 T12 真实文件分页和 SDK 摘要策略。模型的摘要故意不保留业务事实，让 SQL 必保留上下文负责保留事实/约束/回答/版本/产物引用。长案例是否真的覆盖由运行器观察证明，单有大输入不算覆盖。
- 合法来源身份不证明文字内容真实。`semantic_review('stub')` 四项均 not_applicable；live 初始均 unreviewed，不写权重总分。主控后续可明确记录 assistant review，不能声称人已审过。
- 保留原公开模型输出用于检查；本工作包未接付费模型、未承担预算器、未声称 stub 时延/质量代表真实模型。
