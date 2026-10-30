# ResuMate AI 全栈教学笔记

更新时间：2026-10-30。这里把实际开发与知识点联系起来。计划中的能力仍是计划，不能写成已完成项目成果。

## 学习路径

| 阶段 | 学习主题 | 当前状态 |
| --- | --- | --- |
| M0 / T01 | 可复现环境、测试分层、工具调用、SQLite checkpoint、暂停恢复 | 完成；后端 220、组件 2、浏览器 1 项通过 |
| M0 / T02 | SQL 数据建模、唯一约束、状态契约、增量升级 | 完成；SQLite/MySQL 与全后端 244 项通过 |
| M1 / T03 | Run API、鉴权、事务、幂等、取消与补问 | 完成；全后端 275 passed / 1 skipped |
| M1 / T04 | 独立 worker、队列投递、心跳、恢复 | 完成自动验收；真实 Compose 崩溃恢复通过 |
| M1 / T05 | Deep Agents、业务工具、补问、幂等草稿 | 实现和确定性自动验收完成；真实模型 smoke 已执行失败、无输出/usage |
| M1 / T06 | 持久事件、鉴权 SSE、断线恢复 | 完成自动验收；真实 worker 崩溃后游标回放通过 |
| M1 / T07 | 任务工作台、补问、产物展示 | 完成确定性联调；桌面/手机截图已实际查看 |
| M2 / T08 | 岗位中心、事实版本、来源撤回 | 完成；后端 442、前端 63、真实浏览器 11 项通过；7 张截图已查看 |
| M2 / T09 | 固定输入、有来源字段建议 | 完成确定性验收；508 后端、67 前端、真实浏览器与截图通过；语义评测待执行 |
| M2 / T10 | 修改审阅与并发确认 | 完成；552 后端、87 前端、15 浏览器通过，6 张截图实际查看 |
| M2 / T11 | PDF、投递快照 | 完成；626 后端、94 前端、17 浏览器通过；真实 Linux 中文两页 PDF 与截图已查看 |
| M3 / T12 | 上下文预算、可撤回业务记忆 | 完成；678 后端、20 浏览器，14 张真实截图已查看，3 项审查修复闭环 |
| M3 / T13 | 观测、AI 评测 | 实现与 stub 验收完成；最终 12 案、56/56 请求上下文证明通过；live 在 3 元预算内停止：2 次失败，正式案其余 11 案未执行；语义未验收 |
| M3 / T14 | 故障恢复与旧任务迁移 | 完成确定性验收；四个真实中断通过，24案全通过，最终140前端组件，20张截图已查看 |
| M4 / T15 | 扩展收藏与确认版本填表 | 完成；899 后端、30 扩展、140 前端通过，实际 ZIP 与原生侧栏已验收 |
| M4 / T20 | Redis 跨进程协作 | 完成；真实集成 7 passed、旧 SQLite PDF 1 passed、浏览器 27 passed；完整首轮失败与定向修复分别留证 |
| M4 / T16 | 持久文字面试 | 完成确定性验收；六案6/6、最终15前端定向、4浏览器与11实际截图通过，后端首轮失败及修复分别留证 |
| T21 | 实时双向面试 | 2026-10-30用户取消；不再开发或计入剩余任务 |
| M5 / T17–T19 | 性能、安全回归、部署、整体验收 | 待开发 |

最新结果见 [T20 测试记录](test-records/2026-10-30-t20.md)：保留三次 `executed:false` 环境失败与修复，最终双 API/MySQL/Redis/worker 七项通过；27 个浏览器场景、三张实际截图和旧 SQLite 中文两页 PDF 已验证。严格 lock 依赖层加当前完整源码通过，不等于生产 Dockerfile fresh 构建成功；该项留在 T19。当前按 [T16 局部计划](../superpowers/plans/2026-10-30-t16-text-interviews.md)完成文字面试，当前进入T17/T18→T19；T21已取消，最终评测保持30案。真实模型试运行与首批评测共享用户授权的 3 元预算；正式首案返回额度不足，2 次失败均无用量，预留 2.43941760 元并停止，其余 11 案未执行。预留不是实付账单。规划修订见[总计划](../superpowers/plans/2026-10-29-ai-fullstack-agent-development.md)。

## 已有资料

- [连续开发执行记录](execution-log.md)

- [第一课：开发基线与 Agent 恢复契约](01-development-baseline.md)
- [第二课：业务数据契约](02-data-contracts.md)
- [第三课：任务 API 与事务](03-run-api.md)
- [第四课：队列与故障恢复](04-worker-recovery.md)
- [第五课：Agent 业务工具](05-agent-business-tools.md)
- [第六课：持久事件、鉴权 SSE 与断线恢复](06-durable-events-and-sse.md)
- [第七课：可恢复 Agent 的任务工作台](07-agent-workspace.md)
- [第八课：岗位中心与可追溯事实](08-jobs-and-confirmed-facts.md)
- [第九课：固定输入与有来源的简历建议](09-evidence-based-tailoring.md)
- [第十课：逐项审阅、冲突与版本冻结](10-resume-review-and-conflicts.md)
- [第十一课：中文 PDF 与不可变投递快照](11-pdf-and-submission-snapshots.md)
- [第十二课：上下文预算、可恢复摘要与可删除记忆](12-context-and-business-memory.md)
- [第十三课：怎样证明 Agent 做对了事情](13-tracing-and-core-evals.md)
- [第十四课：把旧长任务接入可恢复的执行链](14-durable-long-tasks.md)
- [第十五课：扩展的采集、认证与版本边界](15-extension-capture-and-version-fill.md)
- [第十六课：可恢复的文字面试](16-text-interviews.md)
- [T16 开发、测试与截图记录](test-records/2026-10-30-t16.md)
- [第二十课：让两个 API 共享短期状态](20-redis-cross-process.md)
- [T20 Redis、真实故障恢复与 PDF 回归记录](test-records/2026-10-30-t20.md)
- [T15 扩展、下载包、实际浏览器与原生侧栏记录](test-records/2026-10-30-t15.md)
- [T14 长任务迁移、恢复、测试与截图记录](test-records/2026-10-30-t14.md)
- [真实模型 smoke/T13：额度拒绝与 3 元共享预算停止](test-records/2026-10-30-t13-live.md)
- [T13 测试、评测证据与审查修复记录](test-records/2026-10-30-t13.md)
- [T12 测试、截图与审查修复记录](test-records/2026-10-30-t12.md)
- [T11 测试、截图与 PDF 记录](test-records/2026-10-30-t11.md)
- [T10 测试、截图与修复记录](test-records/2026-10-30-t10.md)
- [T09 测试、截图与修复记录](test-records/2026-10-30-t09.md)
- [T08 测试、截图与修复记录](test-records/2026-10-30-t08.md)
- [T07 测试、截图与修复记录](test-records/2026-10-29-t07.md)
- [T06 测试与审查修复记录](test-records/2026-10-29-t06.md)
- [T04/T05 测试与计划调整记录](test-records/2026-10-29-t04-t05.md)
- [T03 测试记录](test-records/2026-10-29-t03.md)
- [T02 测试记录](test-records/2026-10-29-t02.md)
- [T01 测试记录](test-records/2026-10-29-t01.md)
- [开发命令与协作约定](../development.md)

每次阅读建议按「业务问题 → 设计理由 → 源码 → 测试 → 自己改一次」进行。不要从背框架 API 开始。
