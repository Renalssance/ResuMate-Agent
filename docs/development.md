# ResuMate 开发与学习入口

本项目按「总体设计 → 单元契约 → 测试 → 实现 → 单元验证 → 集成验证」推进。业务能力的完成状态以测试记录为准，不以原计划或简历示例为准。

## 从哪里开始

1. [总体范围](superpowers/specs/2026-10-29-ai-fullstack-agent-scope.md)：产品目标、四层能力、明确不做的事情。
2. [完整开发计划](superpowers/plans/2026-10-29-ai-fullstack-agent-development.md)：21 个任务及依赖顺序。
3. [学习导航与进度](learning/README.md)：每个已开发单元的知识点、代码入口、实际验证结果。
4. [T01：开发基线与 Agent 恢复契约](learning/01-development-baseline.md)：当前第一课。

## 安装与验证

在仓库根目录运行，使用 Python 3.12、Node 24。锁文件记录本项目实测版本；不要为了安装测试工具执行全量依赖升级。

```sh
uv sync --frozen --group dev
npm --prefix frontend ci
npm ci
npx playwright install chromium

uv run pytest backend/tests -q
npm --prefix frontend test
npm --prefix frontend run test:unit
npm --prefix frontend run build
npm run test:e2e
node --test extension/tests/*.test.mjs
```

浏览器用例自动启动独立的 4173 端口前端。当前用例验证注册页本地校验，无须启动后端，无须真实账号或模型密钥。它不代表完整登录链路已经做过端到端测试。端口占用会失败，不复用来源不明的开发服务。

Vitest 只收集 `src/**/*.spec.ts`；已有 `*.test.ts` / `*.test.mjs` 保留在原 `npm test` 入口，避免把 Node 自执行测试误当作 Vitest 套件。

## 每单元需要留下什么

- 要解决的用户问题，以及该单元输入、输出、依赖。
- 实际修改了什么、为什么这样分层；源码链接和一次数据流说明。
- 每个检查检测什么错误、失败后采取什么措施。
- 命令、环境、实际结果、失败原因、修复与未验证边界。
- 可复现的学习练习和自测问题。

纯文档不写形式化测试；行为变化先补失败测试。依赖契约测试可以先出现缺少依赖的收集错误，必须如实记录，不能冒充业务断言失败。已经存在的行为补回归测试时，也不声称是新功能的红绿开发。

## 工作区说明

本次开发使用独立工作区 `resumate-fullstack-learning/ResuMate-Agent`，从提交 `e993b27` 建立。原工作区已有的资料模板复制等未提交修改未带入；集成回原目录时需要保留并合并这些改动。测试日志会明确属于哪个工作区。
