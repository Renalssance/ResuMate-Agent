# ResuMate 开发与学习入口

本项目按「总体设计 → 单元契约 → 测试 → 实现 → 单元验证 → 集成验证」推进。业务能力的完成状态以测试记录为准，不以原计划或简历示例为准。

## 从哪里开始

1. [总体范围](superpowers/specs/2026-10-29-ai-fullstack-agent-scope.md)：产品目标、四层能力、明确不做的事情。
2. [完整开发计划](superpowers/plans/2026-10-29-ai-fullstack-agent-development.md)：保留原21个编号以追溯历史；当前范围为T01–T19共19项。T20后续要求、T21及教学演示录制已取消，T20已有代码与历史记录保留。
3. [学习导航与进度](learning/README.md)：每个已开发单元的知识点、代码入口、实际验证结果。
4. [T01：开发基线与 Agent 恢复契约](learning/01-development-baseline.md)：当前第一课。

## 安装与验证

在仓库根目录运行，使用 Python 3.12、Node 24；当前本机验证版本为Python 3.12.14、Node 24.22.2，Node版本固定在 `.nvmrc`。新终端先执行 `source ~/.nvm/nvm.sh`、`nvm use` 和 `source .venv/bin/activate`。锁文件记录本项目实测版本；不要为了安装测试工具执行全量依赖升级。

```sh
uv sync --frozen --group dev --extra telemetry
npm --prefix frontend ci
npm ci
npx playwright install chromium
uv run python -m playwright install chromium

uv run pytest backend/tests -q
npm --prefix frontend test
npm --prefix frontend run test:unit
npm --prefix frontend run build
npm run test:e2e
node --test extension/tests/*.test.mjs
```

浏览器用例自动启动独立的 4173 前端、4174 API、8899 扩展示例、原生 worker 与专属 Redis 容器，使用临时 SQL/checkpoint/exports 目录和合成账户；只替换模型，真实执行任务、审阅、PDF 和投递流程。运行前需 Docker 已启动、Python/Node 依赖与 Chromium 已安装。端口占用会失败，不复用来源不明的开发服务。真实模型质量仍须单独评测。

Vitest 只收集 `src/**/*.spec.ts`；已有 `*.test.ts` / `*.test.mjs` 保留在原 `npm test` 入口，避免把 Node 自执行测试误当作 Vitest 套件。

## 每单元需要留下什么

- 要解决的用户问题，以及该单元输入、输出、依赖。
- 实际修改了什么、为什么这样分层；源码链接和一次数据流说明。
- 每个检查检测什么错误、失败后采取什么措施。
- 命令、环境、实际结果、失败原因、修复与未验证边界。
- 可复现的学习练习和自测问题。

纯文档不写形式化测试；行为变化先补失败测试。依赖契约测试可以先出现缺少依赖的收集错误，必须如实记录，不能冒充业务断言失败。已经存在的行为补回归测试时，也不声称是新功能的红绿开发。

## 工作区说明

当前直接在原项目目录 `/Users/bono/Desktop/code/ResuMate-Agent` 使用分支 `codex/resumate-fullstack-learning`；2026-10-30按用户澄清从独立工作树切换到这里，子工作树已移除。复用原main工作区的 `.env` 与 `.env.cloudbase`，文件内容未改动；Python环境位于项目根目录 `.venv`。原有六个文件的未提交修改已恢复，资料页导入冲突同时保留模板补齐和事实/记忆组件。历史测试快照中的工作区路径保留当时来源。

## 当前运行方式与历史实验

当前部署拓扑已在T20改为共享MySQL、两个API、Redis、一个worker和调度器，T19生产前端代理及备份恢复已完成。以[README](../README.md)的当前启动方式与[总计划](superpowers/plans/2026-10-29-ai-fullstack-agent-development.md)为准。MySQL/Redis不发布宿主端口；API/worker共享原文件与PDF卷，只有worker挂载checkpoint卷。

原T04的单API/SQLite Compose已迁入`backend/tests/fixtures/compose.sqlite.yaml`，仅用于特定故障实验，不应当作生产部署命令。macOS原生进程与Docker进程不可共享SQLite WAL；跨虚拟机数据用MySQL。MySQL8.4双API七场景已在T20实际执行，早期原生MySQL9.6单元测试单独留证。

MySQL双库测试支持`RESUMATE_TEST_MYSQL_SOCKET`或CI专用`RESUMATE_TEST_MYSQL_URL`。它会创建、销毁随机临时数据库，不连接应用业务库。两者未配置时明确skip，不能宣称MySQL通过。

浏览器默认使用4173/4174/8899；保留用户预览时，指定前端4273、API4274和扩展示例8999。生产浏览器独立配置使用另一个nginx端口，不复用来源不明的服务。真实模型、普通stub、进程恢复与页面截图分别记录。

## T06：事件订阅与教学

新 Run 的事件记录在 SQL 中，接口 `/api/agent/runs/{run_id}/events?after=N` 使用 Bearer 请求头。前端入口是 `frontend/src/services/agentStream.ts`；关闭订阅不取消任务。旧任务进度也必须登录，提交成功后再订阅；旧内存任务已在 T14 迁入相同持久任务链，详见[第十四课](learning/14-durable-long-tasks.md)。

```sh
uv run pytest backend/tests/test_run_events.py backend/tests/test_agent_events.py backend/tests/test_legacy_task_auth.py -q
npm --prefix frontend run test:unit
```

详见[第六课：持久事件与 SSE](learning/06-durable-events-and-sse.md)及[T06 测试记录](learning/test-records/2026-10-29-t06.md)。Compose 故障实验现在同时验证实际网络 SSE：断线、worker 崩溃、按游标补齐、唯一产物事件。新任务界面、后续补问与文字面试已分别在T07–T16验收。

## T11：中文 PDF 与投递快照

Python Playwright 固定为1.64.1，模板依赖 Jinja2 3.1.6；锁文件随项目保存。两个 Dockerfile 都安装该版本对应的 Chromium 与 Debian Bookworm `fonts-noto-cjk=1:20220127+repack1-1`，模板指定 `Noto Sans CJK SC`。本机开发也应安装同一包的 Regular/Bold 字体（macOS 放 `~/Library/Fonts`）；本次从实测镜像的 `/usr/share/fonts/opentype/noto/NotoSansCJK-{Regular,Bold}.ttc` 复制安装，未依赖默认系统字体回退做最终验收。

`RESUME_EXPORT_DIR` 默认 `data/exports`。API 与 worker 需要相同持久目录；Compose 已设 `/app/data/exports` 并共享 `backend-data` 卷。不要把该目录作为公开静态文件目录，下载通过鉴权 API。

```sh
docker build -f deploy/worker.Dockerfile -t resumate-t11-worker .
RESUMATE_PDF_COMPOSE_TEST=1 uv run pytest backend/tests/test_resume_export_compose.py -q -s
npm run test:e2e -- resume-export.spec.ts
```

Linux 测试只创建测试自己的 Compose 项目和合成确认版本，输出 PDF、逐页 PNG、提取文本与日志，结束时清理自身容器/卷。测试默认显式跳过，不把普通单元套件的通过当作 Linux PDF 已验收。浏览器成功路径实际打印并下载；进行中/一次失败由专用测试 worker 控制，不是产品开关。

详见[第十一课](learning/11-pdf-and-submission-snapshots.md)及[T11 测试记录](learning/test-records/2026-10-30-t11.md)。

当前环境配置、旧环境删除范围与验证结果见[环境整理记录](learning/test-records/2026-10-30-environment.md)。
