# ResuMate AI 全栈教学笔记

更新时间：2026-10-29。这里把实际开发与知识点联系起来。计划中的能力仍是计划，不能写成已完成项目成果。

## 学习路径

| 阶段 | 学习主题 | 当前状态 |
| --- | --- | --- |
| M0 / T01 | 可复现环境、测试分层、工具调用、SQLite checkpoint、暂停恢复 | 完成；后端 220、组件 2、浏览器 1 项通过 |
| M0 / T02 | SQL 数据建模、唯一约束、状态契约、增量升级 | 完成；SQLite/MySQL 与全后端 244 项通过 |
| M1 / T03 | Run API、鉴权、事务、幂等、取消与补问 | 完成；全后端 275 passed / 1 skipped |
| M1 / T04 | 独立 worker、队列投递、心跳、恢复 | 完成自动验收；真实 Compose 崩溃恢复通过 |
| M1 / T05 | Deep Agents、业务工具、补问、幂等草稿 | 实现和确定性自动验收完成；真实模型 smoke 待执行 |
| M1 / T06 | 持久事件、鉴权 SSE、断线恢复 | 完成自动验收；真实 worker 崩溃后游标回放通过 |
| M1 / T07 | 任务工作台、补问、产物展示 | 下一阶段 |
| M2 / T08–T11 | 岗位、事实版本、修改审阅、PDF、投递快照 | 待开发 |
| M3 / T12–T14 | 上下文、记忆、观测、恢复、AI 评测 | 待开发 |
| M4 / T15–T16、T20–T21 | 扩展收藏、多轮面试、Redis、WebSocket | 待开发 |
| M5 / T17–T19 | 性能、安全回归、部署、整体验收 | 待开发 |

最新结果见 [T06 测试记录](test-records/2026-10-29-t06.md)；真实 Compose 事件恢复实验单独运行，1 passed / 140.85s。规划修订见[总计划](../superpowers/plans/2026-10-29-ai-fullstack-agent-development.md)。

## 已有资料

- [第一课：开发基线与 Agent 恢复契约](01-development-baseline.md)
- [第二课：业务数据契约](02-data-contracts.md)
- [第三课：任务 API 与事务](03-run-api.md)
- [第四课：队列与故障恢复](04-worker-recovery.md)
- [第五课：Agent 业务工具](05-agent-business-tools.md)
- [第六课：持久事件、鉴权 SSE 与断线恢复](06-durable-events-and-sse.md)
- [T06 测试与审查修复记录](test-records/2026-10-29-t06.md)
- [T04/T05 测试与计划调整记录](test-records/2026-10-29-t04-t05.md)
- [T03 测试记录](test-records/2026-10-29-t03.md)
- [T02 测试记录](test-records/2026-10-29-t02.md)
- [T01 测试记录](test-records/2026-10-29-t01.md)
- [开发命令与协作约定](../development.md)

每次阅读建议按「业务问题 → 设计理由 → 源码 → 测试 → 自己改一次」进行。不要从背框架 API 开始。
