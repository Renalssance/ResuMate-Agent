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

本次开发使用独立工作区 `resumate-fullstack-learning/ResuMate-Agent`，从提交 `e993b27` 建立。原工作区已有的资料模板复制等未提交修改未带入；集成回原目录时需要保留并合并这些改动。测试日志会明确属于哪个工作区。

## T04/T05：本地 API 与 worker

Docker Desktop 已在本机安装。当前终端若找不到命令，macOS 可先执行：

```sh
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
```

本机 Compose 提供 API、一个 worker、一个调度器与 Redis，API 和 worker 共享 Docker 内的 `backend-data` 持久卷。它是独立数据环境，不会自动载入原开发目录的账号或简历。前端继续使用现有 Vite 开发方式；本镜像未包含前端打包页面、可选 OCR 或完整发布代理。

准备自己的 `.env`（不提交），设置现有认证所需的 JWT_SECRET_KEY；可以用 `python -c 'import secrets; print(secrets.token_urlsafe(32))'` 生成。需要注册管理员时还需设置 ADMIN_INVITE_CODE。然后在仓库根目录运行：

```sh
docker compose --env-file .env -f deploy/compose.yaml up -d --build
# 停止容器并保留业务数据库、checkpoint 和 Redis 持久卷：
docker compose --env-file .env -f deploy/compose.yaml down
```

API 默认 `http://127.0.0.1:8000`，Redis 只发布到本机 6379。可通过 RESUMATE_API_PORT / RESUMATE_REDIS_PORT 避免端口冲突。不要对真实项目使用 `down -v`，它会删除命名数据卷。真实模型仍使用应用内个人模型设置，不把 API Key 放在队列中。

**SQLite 运行边界：** API 与 worker 必须都在宿主机运行，或都在 Docker Linux 内访问同一卷。已实测 macOS 原生连接与 Docker worker 共享 SQLite WAL 会观察到旧数据；不要混用。跨主机/虚拟机数据访问使用 MySQL。当前 MySQL 行为测试来自临时 9.6.0 实例，不表示完整 MySQL Compose 部署或 MySQL 8.x 已验收。

单元测试与独立故障实验分别执行：

```sh
uv run pytest backend/tests/test_worker_delivery.py backend/tests/test_agent_runtime.py backend/tests/test_tool_idempotency.py -q
RESUMATE_COMPOSE_TEST=1 uv run pytest backend/tests/test_worker_compose.py -q -s
```

未提供 RESUMATE_TEST_MYSQL_SOCKET 时，MySQL 参数会显式跳过；应在记录中说明。Compose 测试自行创建随机项目、合成资料、测试模型和端口，完成后清理该测试的容器与卷。它会终止自己的 worker，不终止已有开发服务。常规后端套件默认跳过此项耗时故障实验；启用参数仅是测试入口，不是产品功能开关。

## T06：事件订阅与教学

新 Run 的事件记录在 SQL 中，接口 `/api/agent/runs/{run_id}/events?after=N` 使用 Bearer 请求头。前端入口是 `frontend/src/services/agentStream.ts`；关闭订阅不取消任务。旧任务进度也必须登录，提交成功后再订阅；旧内存任务已在 T14 迁入相同持久任务链，详见[第十四课](learning/14-durable-long-tasks.md)。

```sh
uv run pytest backend/tests/test_run_events.py backend/tests/test_agent_events.py backend/tests/test_legacy_task_auth.py -q
npm --prefix frontend run test:unit
```

详见[第六课：持久事件与 SSE](learning/06-durable-events-and-sse.md)及[T06 测试记录](learning/test-records/2026-10-29-t06.md)。Compose 故障实验现在同时验证实际网络 SSE：断线、worker 崩溃、按游标补齐、唯一产物事件。新任务界面与实际操作闭环仍在 T07 验收。

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
