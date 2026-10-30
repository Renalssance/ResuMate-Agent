# T15 Extension Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 用户主动收藏当前岗位，在扩展中选择已确认的简历版本，逐字段预览、选择并填入，最终由用户手动提交招聘表单。

**Architecture:** 延用现有 MV3 side panel、JWT、`/api/jobs` 和 `/api/autofill`。后台负责认证与 API，按需内容脚本只读取页面；显式 `/api/jobs/capture` 处理 URL 收藏去重，原导入入口保持现有语义。已确认版本从 SQL 冻结内容生成填表档案，不产生新的 Run 或投递记录。

**Tech Stack:** 原生 JavaScript / Chrome MV3、Node test、FastAPI / Pydantic / SQLAlchemy、SQLite + MySQL、现有 Playwright Chromium。

**Spec:** [总计划 T15](2026-10-29-ai-fullstack-agent-development.md#t15浏览器扩展收藏与填表关联)，结合 [现有扩展设计](../specs/2026-08-04-chrome-autofill-extension-design.md)。以本计划的实际接口与范围说明补足总计划文件清单。

## Global Constraints

- 2026-10-30 已完成实现与确定性验收；结果、失败修复及实际截图见 [T15 测试记录](../../learning/test-records/2026-10-30-t15.md)。下方“真实缺口”保留实施前的代码观察。
- 不新增浏览器权限、远程抓取、反爬绕过、站点适配平台、兼容层、摘要指纹、数据库迁移框架或付费模型调用。单元由主代理统一本地提交。
- 保持 `#FAF7F2` 米色、`#EFE2CC` 燕麦色、`#63483E` 棕色及现有圆角卡片。中英文字串均入现有 i18n。窄侧栏按钮换行、URL 可折行。
- 只在点击“读取当前岗位”时采集；先给可编辑预览，再由用户点击收藏。扫描或选择版本不触发网页填入，填入不点击提交、不修改投递状态、不调用 application attach。
- 每个单元先以行为测试证明缺口，再实现、定向验证并保存原始日志。运行前说明本次检查能发现什么，以及失败后会修改哪里；定向通过后再由主代理安排一次受影响集成验收。

---

## 已具备与真实缺口

| 代码位置 | 已具备 | 本单元需要补齐 |
| --- | --- | --- |
| `extension/manifest.json` | `sidePanel/storage/activeTab/scripting`，已有主机权限；MV3 module worker | 无需新增权限，也不把岗位采集脚本注册为每页自动采集 |
| `extension/service-worker.js` | 点击工具栏打开 side panel | 目前只有这一行为；认证、固定 API 消息与来源校验尚未进入后台 |
| `extension/lib/api-client.js`、`lib/storage.js`、`sidepanel/sidepanel.js` | JWT 登录、不存密码、profile API、离线缓存 | 目前 side panel 持有 token 并 fetch；退出未清缓存，换账号/后端后离线可能回落到旧档案 |
| `extension/content/scraper.js` | 岗位标题、公司、页面 URL 的现有识别 | 只取短元信息，没有岗位正文；不能把它算作收藏已完成 |
| `extension/content/fill-engine.js`、side panel | 字段预览、勾选、手动填入；URL/tab/profile 改变会使旧扫描失效；跳过密码、验证码、上传 | 保留这些正确行为；补消息来源/形状校验和版本来源展示 |
| `backend/routes/jobs.py`、`services/jobs.py` | 已有收藏 API、所有权、来源键去重、返回 `created`、保留已有手工编辑 | 原导入 URL-only 路径按 URL **和正文**去重，保持该合同；新增显式收藏入口才按 URL 去重 |
| `backend/routes/autofill.py`、`services/autofill.py` | 原简历 profile 的列表、详情、匹配 | 只读取 `Resume`，无 `ResumeVersion`；当前正文的 `description or bullets` 回退不能直接用于明确清空的版本编辑 |
| `backend/db/career_models.py`、`services/resume_versions.py` | 版本冻结内容、逐项确认、revision、confirmed 后不可改；删除源简历只置空引用 | 直接消费已确认内容即可，不再设计版本系统或生成流程 |
| `backend/services/applications.py` | 显式关联投递版本并保存投递快照 | 扩展填入不调用它；网页填表完成不能证明实际投递 |
| `extension/fixtures/*.js` | 现有本地表单与 mock API | 两个服务器脚本仍是 CommonJS `require`，根 `package.json` 已为 ESM；修复这个现有入口后再用于验收 |

## 接口与行为合同

### 现有 HTTP 接口及必要扩展

1. `POST /auth/login` 已有 `{username,password}` → `{access_token,token_type,username,role}`。只由 worker 调用，密码仅随本次消息传递，登录响应返回 side panel 前去掉 token。
2. `POST /api/jobs` 已有 `{title,company,text,sourceUrl?,sourceSite?,sourceJobId?,primaryResumeId?}` → `{job,created}`。新增 `POST /api/jobs/capture` 复用同一个 `JobCreate` 和返回结构，扩展仅调用这个显式收藏入口。标题最长 255、URL 最长 1024；`sourceSite/sourceJobId` 必须成对。扩展通用采集传完整当前 URL，不伪造站点岗位 ID，不截断 URL 来构造身份。可选主简历关联只使用所选 profile 的有效 `sourceResumeId`；版本已无源简历时省略。
3. **原 `POST /api/jobs` 不改**：仍按来源键，或 URL + 正文，或无 URL 的正文精确去重；`test_jobs.py:72` 中“同 URL 正文变化新建”的原断言保持。新 `/api/jobs/capture` 才按当前用户 + 完整 URL 找最早已有岗位，正文变化仍返回 `created:false`，不覆盖原标题、正文、状态、主简历。具体服务 `capture_page_job(db,user_id,JobCreate)` 先验证所选主简历所有权；若有真实 source pair 或无 URL，直接复用 `capture_job`；否则用完整 URL 精确查本人旧行，找不到再复用 `capture_job` 创建。URL 比较保持 MySQL 二进制大小写规则、query 和 fragment，不做全站 URL 归一化，也不需要新字段/表。已有重复行不做历史合并；串行重采集是本次验收，不新增并发唯一索引或锁体系。该入口是产品上真实存在的“收藏页面”操作，不以 flag 改写导入行为。
4. `GET /api/autofill/profiles` 继续返回 summary 数组，增加当前用户的 confirmed 版本；`GET /api/autofill/profiles/{profileId}` 支持 `resume:<int>` 和 `version:<uuid>`。原简历行为保持。新加 metadata：`sourceKind: 'resume'|'resume_version'`、`resumeVersionId: string|null`、`revision: int|null`、`jdId: int|null`；原字段 `sourceResumeId` 保持字符串，版本源被删除时为 `''`，无需读取或补造源简历。版本 `updatedAt` 使用其 `created_at`，列表标签准确写“创建”，不宣称这是确认时间。
5. 版本 profile 的字段只来自 `ResumeVersion.structured_content['resume']`；确认状态、所属用户由服务端查 SQL。草稿不列出，直接读草稿返回 409，其他用户/不存在返回 404。版本名优先冻结候选人姓名，缺少时使用“已确认版本”；标签用 revision + 创建时间，重复同名时仍可区分 ID。已删除源简历/岗位不使冻结版本内容丢失。
6. `POST /api/autofill/match` 在线扩展发送 `{profileId,page,elements}`，由服务端读取实际原简历/confirmed 版本。若同时有 profileId 和 profile，应以服务端 profileId 为准；已有 profile-only 请求仍按当前公开功能匹配，不新增协议兼容框架。离线继续现有本地 matcher，不把缓存 profile 发给服务端假装读取了确认版本。
7. `POST /api/autofill/events` 维持已有去值日志约束。收藏不触发解析/匹配模型任务，任务架构无需变化。

版本字段映射可在现有 `services/autofill.py` 提取小型数据到 sections 的函数，原简历与版本共用字段定义，不创建假的 ORM Resume。对 `changes` 中 `accepted/edited` 的 `/work_experience/<n>/description` 和 `/projects/<n>/description`，即使描述为 `''` 也不能回退到旧 bullets；`self_summary` 以键是否存在决定是否使用旧 `summary`。`resume_export.build_template_data` 已有相同语义，可据此对齐，但不为了这次填表重构整个导出服务。

### 扩展后台消息

采用一个明确的 switch，成功 `{ok:true,data}`，失败 `{ok:false,error:{message,status?}}`。不接受任意 URL/method/headers 的网络代理请求。以下消息仅接受 `sender.id === chrome.runtime.id` 且 `sender.url === chrome.runtime.getURL('sidepanel/sidepanel.html')`；检查所需 payload 类型，未知类型返回受控错误。不要以 `!sender.tab` 判断是否为 side panel，因为真实扩展页面也可作为测试 tab 打开。[Chrome MessageSender 文档](https://developer.chrome.com/docs/extensions/reference/api/runtime#type-MessageSender)

| 消息类型 | payload | data |
| --- | --- | --- |
| `GET_SESSION` | 无 | `{apiBase,authenticated,username}`，无 token |
| `SAVE_SETTINGS` | `{apiBase}` | 同 GET_SESSION；后端实际变化时清除旧认证与档案缓存 |
| `AUTH_LOGIN` | `{username,password}` | 同 GET_SESSION；token 仅后台存储 |
| `AUTH_LOGOUT` | 无 | 同 GET_SESSION；清认证、profile 缓存、activeProfileId、lastMatches |
| `LIST_PROFILES` | 无 | HTTP summary 数组 |
| `GET_PROFILE` | `{profileId}` | HTTP profile |
| `MATCH_FIELDS` | `{profileId,page,elements}` | HTTP match result |
| `RECORD_EVENT` | 已有事件字段 | `{ok:true}` |
| `CAPTURE_JOB_PAGE` | 无 | 当前标签页的 `{title,company,text,sourceUrl}` |
| `SAVE_JOB` | 经过用户编辑的 JobCreate 字段 | `POST /api/jobs/capture` 的 `{job,created}` |

side panel 使用小型请求函数解包消息，不再持有 token 或 import fetch API；`api-client.js` 保留为 worker 的 HTTP 实现，并新增 `captureJob`。缓存继续现有存储位置；退出、登录切换、API 地址切换、401 时清缓存与选择，临时离线不清缓存，不另建多账户缓存系统。

worker 初始化把 `chrome.storage.local` 设为 `TRUSTED_CONTEXTS`，落实内容脚本只采集页面的边界，仍使用已有 storage 权限；无需新权限或旧版浏览器兼容分支。[Chrome storage 文档](https://developer.chrome.com/docs/extensions/reference/api/storage#type-AccessLevel) 规定 local 默认可被内容脚本访问，`setAccessLevel` 可以限制此行为。

`CAPTURE_JOB_PAGE` 只在点击后查询当前 tab，并按需执行现有 `scraper.js` 与新增 `job-capture.js`。新脚本返回数据，不读取 storage、不 fetch、不注入 page-world 消息桥。现有 `SCAN_FORM/FILL_SELECTED/FILL_FOCUSED` 仍由 side panel 发给 content script，补同扩展/side panel 来源检查与真实 payload 形状检查，不扩大命令集合。

### 采集与交互

- “读取当前岗位”选择页面现有可见 `main` / `article` / `[role=main]` 内容，缺少时读取 body；过滤隐藏区域、script/style、导航/页脚、表单控件内容，保留段落换行。这里“可见”是当前 DOM 已渲染并能滚动阅读的文本，不只取视口上半屏；不读网络接口、iframe 或隐藏 JSON。不复用带最小输入框尺寸的 fill-target 可见性规则来判断正文。
- 新增岗位卡片：标题、公司、来源 URL、正文可编辑；“收藏岗位”是单独动作。空标题/正文就地提示；保存中按钮禁用，成功显示“已收藏”及岗位标题，`created:false` 显示“该来源已收藏”。页面跳转或重采集后更新预览；不得把编辑中的旧正文和另一个页面 URL 拼接。
- 注入失败、受限页面或没有可用正文时，保留卡片并提示粘贴正文，可手动填写/清空 URL 后保存；不为解决受限页面加权限。对未授权网页不尝试绕过限制。
- 下拉框保留原简历，清楚标出“原简历”和“已确认版本 · 第 N 版 · 创建日期”。选择更换即清旧扫描，重新扫描后才允许勾选填入。只缓存完整已加载 profile，离线明确显示“缓存版本”。

## 最小开发单元

### T15a：后台认证与已有填表请求迁移

**修改：** `extension/service-worker.js`、`lib/api-client.js`、`lib/storage.js`、`sidepanel/sidepanel.js`、`content/fill-engine.js`、`tests/auth.test.mjs`、`tests/fill-engine-combobox.test.mjs`。新增 `extension/tests/background.test.mjs`；按实际引用同步原相关测试的真实 sender。

- [x] 先新增失败测试：实际 worker listener 收到合法 side panel 登录后保存 token，但响应无 token；未知消息、网页 content sender、错误 payload 不发 fetch。旧代码应因无消息路由失败。
- [x] 增加实际缓存序列测试：A 登录加载档案→退出→B 登录→B refresh 网络失败；不得出现 A 的 profile。后端地址变化与 401 同样清缓存，单纯断网保留当前账户缓存。
- [x] 实现上述固定后台路由；异步 response 保持消息通道直到请求完成；side panel 仅保留 authenticated 布尔状态。API 错误 status 穿透以维持现有 401 行为。
- [x] 内容脚本对合法 side panel 的原三种命令继续运行；拒绝未知类型与非本扩展发送方。测试使用真实 sender 字段，不用生产兼容开关放过空 sender。
- [x] 运行 `node --test extension/tests/auth.test.mjs extension/tests/background.test.mjs extension/tests/fill-engine-combobox.test.mjs`。本次检测消息通道/认证缓存迁移是否破坏已有填表；失败则修改该单元，不继续把旧网络分支留在 side panel。

**可交付结果：** 原简历登录、刷新、扫描、填入仍可用，后台是唯一跨域 API 调用方。

### T15b：正文预览收藏与显式捕获入口

**新增：** `extension/content/job-capture.js`、`extension/tests/job-capture.test.mjs`、`extension/fixtures/job-detail.html`。**修改：** `service-worker.js`、`lib/api-client.js`、`lib/i18n.js`、`sidepanel/{sidepanel.js,sidepanel.html,sidepanel.css}`、`backend/routes/jobs.py`、`backend/services/jobs.py`、`backend/tests/test_jobs.py`。

- [x] 先以新 fixture/真实脚本写失败测试：标题/URL/多段正文可读取，隐藏诱饵与表单已填值不进入正文，脚本不调用 fetch/storage；使用现有 Node VM 测试方式，DOM 的实际布局行为留给 T15d Chromium。
- [x] 在 `test_jobs.py` 新增 `/api/jobs/capture` 红测：同 URL 正文变化返回原 ID/`created:false`，手工标题、状态、原正文不被覆盖；无 URL 不同正文仍新建，其他用户隔离，大小写不同路径保持不同。原 `POST /api/jobs` 测试完全保留，并断言同一组输入在原导入入口仍可因正文变化新建。
- [x] 添加 `capture_page_job` 与 `POST /api/jobs/capture`，新入口复用 `JobCreate`、原创建函数和返回结构；`capture_job` 的原导入查询保持不变。扩展 `SAVE_JOB` 调用捕获入口。不增加新数据表、协议版本或模式 flag。
- [x] 实现按需采集、编辑预览、手动粘贴 fallback、单独收藏动作及双语状态。采集结果是一次完整快照，收藏从卡片取值，绝不临保存时悄悄替换 URL。
- [x] 运行 `node --test extension/tests/job-capture.test.mjs extension/tests/background.test.mjs extension/tests/i18n.test.mjs`；运行 `RESUMATE_TEST_MYSQL_SOCKET=/tmp/resumate-mysql-t02/mysql.sock .venv/bin/python -m pytest backend/tests/test_jobs.py -k 'capture or duplicate or dedup' -q`。检测采集误读、真实双库收藏去重以及原导入语义回归；缺 MySQL 时必须记为未执行，不把 skip 当双库通过。

**可交付结果：** 用户编辑后收藏当前岗位；同一完整 URL 的再次收藏不会因页面文案变化新增岗位。

### T15c：已确认版本 profile 与明确来源的手动填入

**修改：** `backend/schemas/autofill.py`、`backend/services/autofill.py`、`backend/routes/autofill.py`、`extension/sidepanel/sidepanel.js`、`extension/lib/i18n.js`、`extension/tests/background.test.mjs`；**新增：** `backend/tests/test_autofill_versions.py`、`extension/tests/version-selection.test.mjs`。若列表查询扩展影响旧 `test_autofill_routes.py` 的 Resume-only FakeDb，将该文件用已有 `career_db/career_engine` 改为真实数据库断言，不扩建模拟 SQL 查询引擎。

- [x] 先写版本契约红测：本人原简历+confirmed 可列，draft/他人不可列；本人 draft 详情 409，其他用户版本 404。在线 match 的 profileId 决定字段，提供冲突 profile 不能改变版本内容。
- [x] 写冻结语义红测：确认后修改/删除源 Resume，版本字段不变；确认工作/项目描述为 `''` 时无旧 bullets；明确空 self_summary 无旧 summary。原简历现有 profile tests 保持原行为。
- [x] 实现小型共用字段构造函数和版本构造函数；在当前 autofill service 内完成 owned confirmed 读取并转换受控 HTTP 错误，无需把新接口接入 Run。列表加 metadata，按原有原简历顺序加 confirmed 列表即可，不引入分页平台。
- [x] side panel 标签展示版本来源、revision/日期，缓存 summary 保留相同 metadata。默认沿用已选有效 ID；失效时选择已有可用 profile 并明确标签，不悄悄把版本替换成同源最新原简历。
- [x] 写选择行为测试：原简历→版本一→版本二，每次旧 matches/勾选状态失效；线上请求只含 profileId；手动选中字段后填入版本预览值，未选字段不动。
- [x] 运行 `RESUMATE_TEST_MYSQL_SOCKET=/tmp/resumate-mysql-t02/mysql.sock .venv/bin/python -m pytest backend/tests/test_autofill_versions.py backend/tests/test_autofill_routes.py backend/tests/test_autofill_profile.py backend/tests/test_autofill_matching.py -q` 与 `node --test extension/tests/version-selection.test.mjs extension/tests/background.test.mjs`。检测确认内容丢失/回退、所有权和选择错源；失败则修版本 mapper 或选择状态。

**可交付结果：** 用户能明确选择已确认版本，实际填入已审阅内容；不会创建/确认投递记录。

### T15d：真实扩展联调、截图和下载包

**新增：** `tests/e2e/extension.spec.ts`（persistent context fixture 直接保留在此 spec，不另拆文件）。**修改：** `extension/fixtures/static-server.js`、`extension/fixtures/mock-autofill-api.js`、`extension/fixtures/application-form.html`、`extension/README.md`、`frontend/src/views/extensionContent.ts`、`frontend/public/downloads/resumate-autofill-extension.zip`。E2E seed 直接由当前隔离数据库 fixture 设置，不在生产注册调试路由；必要时最小修改 `tests/e2e/support/server.py` 提供已确认版本种子。

- [x] 两个已有服务器脚本改为 ESM imports / `fileURLToPath(import.meta.url)`，修复现有 package 模式不匹配。旧 mock API 只保留原简历 demo 并在 README 明确限制；新字段/收藏以真实 FastAPI + 隔离 SQL 验收，避免扩建第二份模拟后端。
- [x] 表单 fixture 使用真实 `type=submit` 并用页面脚本记录 `submitCount` 与提交按钮 clickCount，防止旧 `type=button` fixture 掩盖误提交。字段包括工作描述、姓名、邮箱、未勾选字段和验证码；岗位 fixture 含隐藏诱饵及多段正文。
- [x] 写实际 persistent extension E2E：登录→读取/编辑岗位→收藏→正文变化后重采集→返回同 job ID；刷新 profile→选择 confirmed→扫描→取消一个字段→填入→断言版本描述、未选字段、验证码、submitCount=0；切版本后旧扫描失效；再覆盖注入受限时粘贴收藏。
- [x] 在上下文存活期间从真实 API/SQL记录一个来源岗位、所选 version ID/revision、主简历未改、JobApplication 无新增。不能用 mock API 成功回包代替 SQL 证明。
- [x] 定向运行 `npx playwright test tests/e2e/extension.spec.ts --project=chromium`。现有 webServer 提供隔离后端/账号；spec 自建临时 Chromium persistent context，结束时关闭并清理 profile。失败按真实扩展加载、消息生命周期、DOM 或后端合同分层修复。
- [x] 运行一次 `node --test extension/tests/*.test.mjs` 检查本次共享 auth/selection/content 改动对原扩展行为的回归。若改下载页说明，运行 `node --experimental-strip-types frontend/src/views/extensionContent.test.ts`；不为文案另写实现镜像测试。
- [x] 按下节方法实际查看截图；记录宽度、浏览器、账户为合成数据以及截图是原生 side panel 还是独立扩展页。
- [x] 更新中英 README/下载页的收藏、版本、缓存和手动提交说明；打包现有 manifest、service worker、content/lib/sidepanel 和 README 到原 ZIP。无需新增打包框架。解压到临时目录，以解压后的扩展做一次加载检查，确认下载产物包含新脚本，不能只验证仓库源码可加载。
- [x] 保存 T15 原始红绿日志、E2E 日志/SQL观察（本轮 trace off）和截图路径，主代理补第十五课与总计划完成标记。完成标记须对应测试记录中的已执行证据。

**可交付结果：** 真实加载的扩展完成收藏与版本填表，下载包与源码一致，有可查看的视觉与业务证据。

## 真实浏览器与截图方法

使用现有 Playwright 自带 Chromium 的临时 persistent context；当前 Chrome/Edge 移除了侧载所需启动参数，因此不要拿用户常用 Chrome profile 做自动化。这是 [Playwright 官方扩展测试方法](https://playwright.dev/docs/chrome-extensions)。核心代码如下，临时目录由测试 fixture 生成并清理：

```ts
const context = await chromium.launchPersistentContext(profileDir, {
  channel: 'chromium',
  headless: false,
  args: [
    `--disable-extensions-except=${extensionPath}`,
    `--load-extension=${extensionPath}`,
  ],
})
const worker = context.serviceWorkers()[0] ?? await context.waitForEvent('serviceworker')
const extensionId = new URL(worker.url()).host
```

业务自动化可在该真实扩展上下文打开 `chrome-extension://${extensionId}/sidepanel/sidepanel.html`，以 390px 及约 320px 宽度检查真实扩展页面：登录、预览、已收藏、版本下拉框、字段勾选和长 URL；保存 `extension-page-*.png`，明确它是扩展页面，不把它称为浏览器原生侧栏。该页面成为 active tab 时不可直接扫描自身；测试点击采集前先用 `chrome.tabs.update(targetTabId,{active:true})` 激活岗位/表单页，再通过已持有的 extension page locator 操作。原生 side panel 验收确认正常用户焦点流程。

原生侧栏截图另做一次 headed 验收：启动同一隔离 fixture 和临时加载扩展的 Chromium，打开岗位 fixture，使用浏览器工具栏点击真实扩展图标打开侧栏；从本次 Chromium 的原生 UI 读取状态并截图，保留“岗位网页 + 扩展侧栏”同屏。使用 computer-use 原生应用截图能力，不使用仅限语音的 capture_screen_context。至少保存：收藏预览、重复收藏成功、confirmed 版本选择、手动填入后的页面及未提交状态。截图后打开图像检查按钮、换行、对比度和溢出，不能只留下未查看的文件。

优先以本地 fixture 做可重复、无外部请求的完整验收。可访问的实际招聘页只作可选采集观察；受限就演示粘贴回退，不影响确定性验收，也不声称已支持所有招聘站。

## 实施顺序与收口

建议分工：后端 owner 负责 T15b 捕获入口及 T15c profile/schema/service/routes/双库测试；扩展 owner 负责 T15a、T15b/C 的扩展部分并独占 `sidepanel.js` 与 `service-worker.js`；主代理负责 T15d persistent context、真实 API/SQL seed、截图、ZIP 和文档收口。后端与扩展按上述 HTTP/消息合同并行即可，T15d 等二者定向完成再整合。本文规划不另起 agent。每个单元停止在自身定向结果，主代理统一安排集成及最终审查。无模型预算前提；所有新路径均为页面读取、SQL 和现有确定性字段匹配。
