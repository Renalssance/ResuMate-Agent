# T11 实施合同：中文 PDF 与投递快照

2026-10-30。依赖 T10 已确认、不可变的 ResumeVersion。用户已授权连续开发与按实测调整，沿用独立工作区；每个实现单元先固定行为、测试再实现，整合后运行真实服务、逐张查看截图/PDF，保存教学与原始证据。

## 可直接实施的决定

只导出属于当前用户的 `confirmed` ResumeVersion。PDF 输入仅是该版本最终 `structured_content.resume`，不得重新从主 Resume、当前 ProfileFact 或 tailoring 上下文合成。使用一套固定中文模板、Python Playwright/Chromium，在现有 Celery worker 执行。沿用 Run 的幂等、领取、心跳、取消、失败重试、持久事件与下载鉴权。无需新建通用任务系统或通用产物表。

最小产物身份取导出 `run.id`：该 Run 每次成功只产生一个 PDF，`artifact_id = run.id`，`output_refs = [{type:'resume_pdf', id:run.id, resumeVersionId:version.id, revision:version.revision}]`。SQL 的成功状态与 output_refs 是可下载依据，本地文件存在本身不代表导出成功。相同 requestId 重复请求返回同 Run、同产物；新 requestId 可重新导出。计划的“重复导出可以返回已有同版本产物”不是必须跨 Run 建缓存，首版不必做额外扫描或缓存框架。

## 实施前基线：复用点与现实缺口

- `backend/db/career_models.py` 已有 ResumeVersion 的归属、revision、status、最终内容、来源引用。T10 保证确认后不可原地修改；不要复制一套冻结服务。
- `backend/db/models.py:JobApplication` 已有 `jd_id`、`resume_version_id`、`submitted_snapshot`。SQLite 增量升级和 `deploy/schema/001_agent_and_versions.sql` 已包含这些列；本次投递关联不需要 DDL。
- `agent_runs.claim_run / guard_execution / finish_run / cancel_run` 和 worker 的 execution_lock、心跳、15 秒扫描均可直接复用。`finish_run` 会处理取消、清空 Session 的 active_run_id 并提交事件。
- 当前 `RunCreate.kind` 只允许 tailoring；`jdId/resumeId` 必填。`create_run/_existing_request/_public_input` 都写死这两个输入。
- **当前 `retry_run` 无条件调用 tailoring 的 `read_context`，后者要求原 Resume/JobDescription 仍存在。** PDF 重试必须按 kind 验证 frozen ResumeVersion，不能因旧主简历删除或变化阻止已确认材料导出。
- **当前 `worker_tasks.execute_run` 无条件执行 `run_agent`。** 只改请求 schema 会让导出进入模型、补问和草稿写入，必须一起改 dispatch；导出无需任何模型设置。
- `run_artifacts` 当前只查 `ResumeVersion.run_id`；PDF Run 的产物会被它漏掉。前端 RunArtifact/ArtifactCard 也只有简历草稿形状，任务状态文案固定为“材料已生成”。
- applications 的请求 schema、`_record`、前端类型/store/form 仍只有 `resume_id`，尚未暴露新关联字段，也没有 `attach_submission` 业务入口。
- `backend/services/documents.py` 管上传/解析和 CloudBase 原始文档；没有 PDF 产物下载路由。它的上传命名、内容哈希、OCR 路径不适合直接搬到已生成 PDF。可以继续保留这些既有能力，本次新增本地导出目录即可。
- Compose 实际构建的是 **`deploy/worker.Dockerfile`**，不是根 Dockerfile。只改总计划列出的根 Dockerfile，真实 worker 仍无法打印。

## HTTP / Run 合同

1. `POST /api/resume-versions/{version_id}/export`，请求 `{requestId}`，返回 `202 {runId,status}`。路由校验归属和 confirmed，调用同一个 `create_run`，数据库提交后 `publish_run`；Broker 发布失败仍返回已接受的 queued，保留既有 SQL 扫描恢复。
2. 通用 `POST /api/agent/runs` 同样接受 `{kind:'resume_export',resumeVersionId,requestId,sessionId?}`，与便利路由共享业务路径。保留当前 `RunCreate` 类，增加有限的 kind 分支和 model_validator 即可，不必改成任务注册框架：tailoring 必须有 jdId/resumeId 且不能带 resumeVersionId；resume_export 必须有 resumeVersionId 且不能带 jdId/resumeId。
3. `create_run` 的 tailoring 分支保持现状；export 分支从归属正确、已确认的 ResumeVersion 取 ID/revision，`input_json={resumeVersionId:...}`、`input_versions={resumeVersion:revision}`。不捕获 tailoring context、不重新选事实。`_public_input` 和 `_existing_request` 按两个 kind 比较对应字段，防止同 requestId 被用于另一个版本。
4. export 的 retry 同样只确认原版本存在、归属正确、confirmed 且 revision 与接受时相符。不要调用 `read_context/changed_inputs`。原简历或原岗位已删除不是 PDF 重试失败条件。
5. worker 领取后读取 kind，明确 `tailoring -> run_agent`、`resume_export -> run_resume_export`。把两个 runner 的导入置于对应分支；其他 kind 明确失败，不默认为 tailoring。现有 execution_lock/claim/heartbeat 包裹两个分支。
6. `GET /api/agent/runs/{run_id}/artifacts` 对导出返回 `{kind:'resume_pdf',id,runId,resumeVersionId,revision,filename,downloadUrl,createdAt}`；对旧简历版本保留现有字段、增加 `kind:'resume_version'` 方便前端区分。`artifact.created` 复用现有 schema，payload 为 `{artifact_id:run.id,kind:'resume_pdf'}`。
7. `GET /api/agent/runs/{run_id}/download`：先 `get_run(db,user_id,run_id)`，再确认 kind=resume_export、status=succeeded、对应 output_ref；从服务端 Run ID 构造路径，存在则返回 `FileResponse` (`application/pdf`、attachment 文件名)。其他账户一律 404；尚未成功返回 409；已成功但文件缺失明确返回 `artifact_missing`，UI 可重新发起导出。不得公开挂载 exports 静态目录，也不接收用户路径参数。

### worker 文件与事务顺序

新增 `backend/services/resume_export.py`，只保留本业务需要的几个函数：读取 confirmed 版本/构造模板数据、render_pdf、`run_resume_export(run_id,epoch)`、下载文件定位。无须把非 Agent 导出硬塞入 Deep Agents tools。

先用 guard_execution 读取固定版本，结束该短事务后启动 Chromium；**不要持 SQLite 写锁进行浏览器打印**，否则心跳/API 写入会被阻塞。先写 `exports/.{run.id}.tmp.pdf`；打印成功后在新事务中 guard_execution，再将临时文件原子替换为 `exports/{run.id}.pdf`，写 `artifact.created` 与 output_refs，通过 finish_run 标记成功并一次提交。若取消/失去执行权，删除临时文件并走现有终态处理；不能把未提交文件暴露为成功下载。文件替换后 SQL 提交前崩溃时，重新执行同 Run 可覆盖该文件；下载仍由 SQL 成功结果控制，不需要跨文件/数据库事务框架、摘要或孤儿文件巡检系统。

异常记录简短的 `pdf_export_failed` 等代码并 finish_run failed，保留人工重试。浏览器二进制/字体缺失属于配置失败，不套用模型 API 的网络重试分类。浏览器/context 必须在异常时关闭。

## 受控目录与容器依赖

新增单一目录配置 `RESUME_EXPORT_DIR`，默认项目 `data/exports`；Compose API/worker 同设 `/app/data/exports`，沿用已共享的 `backend-data:/app/data` 持久卷。不放在 checkpoint 子目录，不放临时下载目录，不把文件路径返回给浏览器。E2E server 给它设置到自身 `RESUMATE_E2E_ROOT/exports`，防止测试写产品数据目录。

读取现状：pyproject 没有 Python playwright；uv.lock 没有该包。Node 测试依赖已锁 @playwright/test/playwright 1.64.1，但 worker 镜像没有 Node 测试环境。PyMuPDF 1.27.2.3 已锁定且当前 .venv 已安装。Jinja2 3.1.6 虽出现在 uv.lock，却只是可选 torch 依赖的传递包，当前 .venv 未出现其 dist-info；若模板用 Jinja，应显式加入运行依赖。

本机 Playwright cache 有 chromium-1248 和 chromium_headless_shell-1248 的安装标记；这只证明本机已有 Node E2E 浏览器缓存，不证明 Python包匹配或容器可运行。系统有 STHeiti 等中文字体，不应把 macOS 系统字体作为 Linux worker 字体验收证据。本次未启动浏览器、未执行 font-match 或打印，不声称运行已验证。

根 Dockerfile 当前只 apt 安装 libgomp1/libgl1/libglib2.0-0；deploy/worker.Dockerfile 没有任何浏览器系统库/中文字体安装。T11 应在两个实际镜像中安装锁定的 Python playwright 后，运行该包的 `python -m playwright install --with-deps chromium`，这样 Chromium revision 随 Python 包版本固定。Python包版本实施时锁定并实测，不把本次查到的“当前最新”当兼容性结论。官方说明浏览器二进制必须与 Playwright 包版本对应。[Playwright 浏览器安装](https://playwright.dev/python/docs/browsers)

Bookworm 可明确使用 `fonts-noto-cjk=1:20220127+repack1-1`（含 SC Regular/Bold），模板指定 `Noto Sans CJK SC`。这是读取 Debian 官方包页得到的版本，不是安装结果。原生开发也要安装同字体或使用同一版本的本地字体文件；实际验收必须包含 Linux worker 的 PDF，不能只依赖 macOS 回退字体。[Debian 字体包](https://packages.debian.org/bookworm/fonts-noto-cjk)

T19 继续负责完整发布、备份/恢复、部署回归与演示；**T11 的字体/Chromium/产物共享与持久化是本任务可运行的前提，不能推迟到 T19**。本次不宣称新 worker 已适配 CloudBase，不删除旧原始文档云存储代码。

## 模板输入与分页

新增 `backend/templates/resume.html`，显式展示已存在的业务结构，不递归打印 JSON：姓名/联系、简介、教育、工作、项目、技能、奖项、证书、语言。当前真实 schema 在 `backend/schemas/workflow.py:ResumeProfile`：`candidate_name`、`contact`、`self_summary`、education/work_experience/projects、对象型 skills/achievements、certifications/languages；旧值还允许 string skills/achievements，E2E 实际使用 `summary`。这些是项目已支持的形状，应直接覆盖，不属于假想兼容层。

结构化字段不全是正文：source_refs、quality、ambiguities、structured_ambiguities、审阅 changes/reason/fact_refs 不应作为简历正文输出。真实教育项有 college/gpa/rank/lab/research_direction/advisor/papers/courses/achievements，不能模板只放 school/major 就把用户已有重要信息悄悄漏掉。实现时明确列出可打印字段。

**与 T10 的交界（审查修订）：** accepted/edited 的 description 已变，但原解析 bullets 仍可能带旧 raw_text。不要同时打印最终 description 和旧 bullets 造成重复/恢复原文；尤其 editedText 允许明确清空，不能空字符串后又 fallback 到旧 bullets。建议改过的 section 仅以最终 description 为准；未经改动的项目应保留与 description 不重复的独立 bullets；T10 实际数据中两者可以同时存在。简介也应按字段是否存在选择 self_summary/summary，不能以 truthiness 将用户清空的字段重新填回来。该行为要用一条“编辑后原 bullet 不复活”的用例固定。

使用 Jinja `Environment(autoescape=True)` 加载仓库模板；模板没有 `safe`，所有用户文本仅进入文本节点；联系中的 URL 当普通文本。静态 CSS 内置，无外部图片、CSS、字体 URL，无用户 HTML/脚本。浏览器用空白页 set_content，本身不请求应用路由，禁用页面脚本并阻断外部请求即可满足这一具体渲染边界，不扩张为网页爬虫安全系统。[Jinja autoescape](https://jinja.palletsprojects.com/en/stable/api/#autoescaping)

使用 A4、明确页边距、单列、可换行长文本；不要给整份简历固定高度或 overflow:hidden；标题避免落在页尾，普通短条目避免被拆成两页，长经历允许合理跨页。Playwright 的 page.pdf 使用 print media，`format='A4'`、`print_background=True`、`prefer_css_page_size=True` 可与固定 @page 配合；不要用截图生成图片型 PDF。[Playwright PDF API](https://playwright.dev/python/docs/api/class-page#page-pdf)

## 投递关联：一次写入的提交快照

新增 `backend/services/applications.py:attach_submission(db,user_id,application_id,jd_id,version_id)`，只承接此次提交材料关联，不搬迁全部日程/状态 CRUD。

新增 `PUT /api/applications/{id}/submission`，沿已有 applications 风格请求 `{jd_id,resume_version_id}`。服务验证 Application/JD/ResumeVersion 都属于同一用户、版本 confirmed、版本 jd_id 与目标 jd_id 一致。首次关联通过条件 UPDATE（submitted_snapshot IS NULL）同时写三个字段，并把 resume_id 同步为该版本当前原文 ID（原文已删除时为 null）；相同 JD/版本重复关联返回原结果，保留原快照；想换成另一个版本返回 409，避免把历史“提交时材料”偷偷改写。仍可编辑公司、职位、日期、状态、备注和日程。

快照直接 deepcopy 版本内容，例如 `{resumeVersionId,revision,jdId,structuredContent,factRefs,submittedAt}`，不接收客户端传入快照、不引用当前主简历。历史显示读 `submitted_snapshot`，即使主简历修改/删除也不变。关联后普通 PATCH 不能把 resume_id 改成另一个原文档，保持该提交的三个关联一致；相同 resume_id 回传可以接受，兼容现有编辑表单。

`ApplicationCreate` 可增加成对可选的 `jd_id/resume_version_id`，新建后 flush、调用同一 attach_submission、一次 commit，使“新建投递并关联已确认版本”原子完成。旧请求不带新字段仍按现状创建；旧记录三字段为 null 仍可查看。不向普通 PATCH 暴露 submitted_snapshot 任意写入。

ApplicationRecord、`_record`、前端 BackendJobApplicationRecord/JobApplicationRecord/store 映射补齐 jd_id/resume_version_id/submitted_snapshot。显示“已确认版本 · 第 N 版”和查看冻结材料入口；原 resume_filename 保留供旧记录使用。

最小 UI 路径：T10 已确认版本页提供“导出 PDF”“关联投递”按钮。后者带 resumeVersionId/jdId 进入 ApplicationsView，读取版本详情并显示固定材料，再选已有投递或新建投递。这样可完成计划主流程，不必先增加“所有版本选择器”或新的版本列表平台。所有 API 仍自行校验，不能信任 query 参数。已关联记录不显示会替换快照的普通简历选择器。

## 文件分工（T10 本地提交之后开始写）

- 后端 Run/导出：新增 services/resume_export.py、templates/resume.html、tests/test_resume_export.py；修改 schemas/agent_runs.py、services/agent_runs.py、routes/resume_versions.py、routes/agent_runs.py、worker_tasks.py。schemas/resume_versions.py 仅加 export 请求 schema，复用 T10 confirmed 合同。
- 后端投递：新增 services/applications.py；修改 routes/applications.py、schemas/applications.py、tests/test_applications_routes.py。不改 career_models/JobApplication 表结构。
- 前端：在 T10 的 ResumeEditorView/版本 API 加两个入口；修改 ApplicationsView、api/applications、types/application、stores/application；修改 api/agentRuns 的产物联合、ArtifactCard 或一个极小 PDF 卡片、AgentTaskView 状态文案。下载通过已有 Bearer header + fetch blob + object URL，不能普通链接跳到需要 Bearer 的 API 后期待自动带认证。
- 运行/验收：pyproject.toml、uv.lock、两个 Dockerfile、deploy/compose.yaml、.env.example、docs/development.md；tests/e2e/support/server.py 增加隔离 export 目录；新增 tests/e2e/resume-export.spec.ts。不要改当前 T10 文件到一半时抢写。

## 验证及失败处理

每项都对应具体失败与行动，不重复已通过且未被修改影响的全仓检查：

1. Run 请求和派发测试：非法 kind/混用字段被拒绝；export 送到真实导出 runner，替身 run_agent 若被调用立即失败；requestId 相同与不同输入冲突；失败时改 schema/dispatch，而不是放宽模型权限。
2. SQL 生命周期测试：确认版本导出、草稿409、其他用户404；原简历修改/删除后导出及 retry 仍用固定内容；取消时没有成功 output_ref/下载；失败时修正 frozen 输入或事务边界。复用 career_fixtures 的 SQLite/MySQL，不另造数据库框架。
3. 投递业务测试：同一次关联可重复，换版本409；非 confirmed/跨用户/错岗位拒绝；主简历变化、普通 PATCH 不改变 submitted_snapshot；已有旧投递 CRUD/日程仍正常。失败时修正归属、条件写或快照复制。
4. 真实 renderer 测试：用当前 ResumeProfile 形状的中文两页样例（教育/工作/项目/技能/奖项/证书/语言，长公司名与长描述，含已编辑和明确清空的字段），真实启动 Chromium 生成 PDF。PyMuPDF `page.get_text()` 检查各实际内容字段和中文可提取，page_count==2；若断字/乱码/缺字段则修正字体和模板，不做“ATS 关键词通过率”。[PyMuPDF 文本提取](https://pymupdf.readthedocs.io/en/latest/recipes-text.html)
5. 同一生成 PDF 每页用 PyMuPDF `get_pixmap()` 存 page-1.png/page-2.png，**实际打开逐张查看**：中文不是方框、页底无裁切、标题/正文分页合理、长文不重叠、第二页末项完整。保存 PDF、文本提取和两张预览到测试产物目录供一次人工审阅；这是最终 PDF 的预览，不能只拿 HTML 页面截图代替。[PyMuPDF 页面渲染](https://pymupdf.readthedocs.io/en/latest/recipes-images.html)
6. 一条真实 API + Redis + Celery worker + 浏览器下载 E2E：确认版本 -> 导出202 -> 持久事件成功 -> 带认证下载 -> PDF可读 -> 投递关联 -> 修改主简历 -> 回看原提交材料。导出部分不使用假 PDF bytes/模型替身渲染。已有 E2E 只替换模型，真实队列/数据库/worker，可复用；需额外跑实际 deploy/worker.Dockerfile 中的真实打印，检测镜像依赖缺失。
7. 前端按用户要求运行真实页保存并逐张查看桌面/手机、导出进行中/失败可重试、已成功下载、已关联快照与旧记录状态；发现溢出/遮挡只修受影响页面并复查对应截图。

以上基线观察用于确定实施边界。最终交付证据见 [T11 测试记录](../../learning/test-records/2026-10-30-t11.md)，不将最初准备阶段的只读分析作为测试。

## 执行状态

- [x] 后端确认版本导出、Run 分派、下载与有限事务边界
- [x] 投递一次性快照及旧记录兼容
- [x] 前端真实导出与关联投递流程
- [x] Chromium / 中文字体 / Linux worker 运行依赖
- [x] 两库测试、真实浏览器下载、PDF 文本及逐页视觉验收
- [x] 独立审查、教学课、测试原始记录、总计划更新与本地提交

实现细化：实际支持独立 metrics，已纳入模板与预览；手机按钮换行与本地默认投递日期在真实截图中发现并修复。
