# T08 局部实施合同：岗位中心与资料事实

基线：T07 `9b4ea1f`。依据总计划 T08 与真实代码审查，2026-10-30 执行。用户已授权按测试结果实时调整并自动推进；此文固定本单元跨前后端合同，不额外等待逐项批准。

## 设计决定

复用 JobDescription、Resume、ProfileFact、MatchResult。岗位中心连接已存在的匹配和材料准备页面；确认事实由用户明确操作产生。事实每次修改生成新行，原版本可追溯。T09 再固定完整简历/JD 输入快照与字段建议；T08 先固定事实版本集合。

粘贴岗位必须有单独的文本解析路径：原文件解析入口依赖 file_path，不能将原文装成虚假结构化 JobProfile。收藏只保存原文，解析复用既有 AgentHarness/JobProfile 与异步任务响应。解析成功后允许匹配；材料准备可以读取原文，但跳转后的选择仍沿用已解析文档的现有合同。

新增 JobDescription.primary_resume_id（nullable，删除简历时 SET NULL）。沿用 SQLite 追加缺列与显式 MySQL 增量 SQL，不新增迁移框架。

## HTTP 合同

所有接口使用本人身份与资源归属；公开时间含 UTC offset。前端错误保留状态码以区分 409，并保留未提交输入。

### 岗位

`POST /api/jobs` 输入 `{title,company?,text,sourceUrl?,sourceSite?,sourceJobId?,primaryResumeId?}`，响应 `{job,created}`。必填 title/text 去首尾空白后非空；sourceSite/sourceJobId 成对。来源 URL 只保存，不自动抓取。空来源存 NULL。有 site/id 按现有唯一约束去重；仅 URL 时同用户 URL+text；无来源时同用户 exact text。重复返回原记录，不覆盖人工编辑及关联。

`GET /api/jobs?query=&status=&limit=20&offset=0` 响应 `{items,hasMore}`。status 为 saved/archived；按 coalesce(captured_at,created_at) DESC、id DESC。列表 Job 含 `id,title,company,sourceUrl,sourceSite,sourceJobId,capturedAt,status,primaryResumeId,parseStatus,createdAt,updatedAt`。不返回全文/完整匹配报告。

`GET /api/jobs/{id}` 返回 Job + `text,structuredContent,primaryResume`（null 或 `{id,filename}`）。`PATCH /api/jobs/{id}` 编辑 `title,company,status,primaryResumeId`，返回详情。主简历必须本人所有；支持清除关联。正文重编辑留待真实需求，不扩展本单元。

`GET /api/jobs/{id}/matches?limit=20&offset=0` 响应 `{items,hasMore}`，每项 `runId,candidateId,resumeId,score,createdAt`；复用已有匹配详情接口，不新增评分。页面链接到 `/matching` 并带岗位/主简历参数；需要详情时可用既有报告读取能力。

`POST /api/jobs/{id}/parse` 使用已有 202 任务响应（task_id/taskId 沿用既有任务协议），真实后台解析库内文本并更新 JobDescription；失败保留收藏和原文，可重试。前端复用现有异步请求/进度工具。

### 事实

`POST /api/profile-facts` 输入 `{kind,content,sourceDocumentId?,confirmed:false}`。kind=preference/experience，content 至少包含非空 `text`，可保留实际资料来源字段。返回 Fact。

Fact 为 `{id,factKey,kind,content,sourceDocumentId,revision,confirmedAt,deletedAt}`。新 fact_key 与版本 UUID 由服务端生成。确认必须明确 true；模型解析不自动确认。

`GET /api/profile-facts?sourceDocumentId=&includeDeleted=false` 响应 `{items}`，每个 fact_key 仅最新版本；先求包括未确认和删除行的最新，再按显示范围过滤，防止旧版本复活。有 sourceDocumentId 时包含全局事实与该简历事实；来源简历本人所有。includeDeleted 是显式历史查看开关，可供页面查找已删除事实再看历史。

`PATCH /api/profile-facts/{versionId}` 输入 `{expectedRevision,content,confirmed:false}`，仅允许当前最新版本；插入同 fact_key 的 revision+1。确认状态不从旧行静默继承。返回新 Fact，旧版本/并发唯一冲突返回 409。

`DELETE /api/profile-facts/{versionId}?expectedRevision=N` 插入 revision+1 tombstone，返回该 Fact。`GET /api/profile-facts/{versionId}/history` 返回 `{items}`，按 revision 升序；保留旧内容、确认和删除记录。越权/不存在均404。

## Run 的事实输入

创建 Run 时固定经过来源筛选的最新、已确认、未删除事实，写 `input_versions.facts=[{factId,revision}]`。上下文只读取这组不可变版本；更新事实后旧 Run 仍读旧版本，新 Run 读新版。不要因为事实正常更新就把旧 Run 变成 input_changed。

save_draft 引用必须来自该 Run 固定集合。某个 fact family 最新行为删除时，后续新草稿拒绝引用，即使旧版本仍存在；已有产物保留历史来源。旧 Run 无 facts 字段按空集合处理，不推测它曾读过今天的事实。简历/JD 当前时间戳校验暂沿用 T06，完整输入快照与旧资料提示在 T09 实现。

## 前端

新增 `/jobs`，沿用暖色背景、白卡、棕色按钮和既有表单。包含收藏表单、搜索/状态过滤、分页、详情/主简历、解析进度和错误重试、历史匹配、跳转匹配/材料准备。筛选变化重置分页；使用稳定 ID key。

结构资料页增加独立事实组件：用户手填偏好/经历，明确确认、编辑、删除、历史与已删除查看。可以从当前已解析简历选择一段经历作为待确认文本并携带真实来源；不要整份静默确认，也不要改写原结构表单保存语义。标签、冲突提示、键盘和手机长内容与 T07 同标准。

MatchingView/AgentTaskView 接收 jdId/resumeId 查询参数，在本人文档加载完成后验证并预选。事实组件根据选择简历加载数据；账号/简历切换不能被旧请求覆盖。

## 分工与验收

岗位服务/API/SQL 由一个实现单元负责，事实/API/Run 引用由另一个单元负责，前端统一由第三个单元负责。路由注册由主代理整合；浏览器测试入口与教学记录由主代理负责，避免共享文件并行覆盖。

先写能暴露实际需求失败的测试，再做最小实现。SQLite/MySQL 定向验证重复、归属、分页、删除后旧事实不复活、版本冲突、新旧 Run 引用集合。前端验证实际表单、加载/错/空状态与选择跳转。真实浏览器用生产 API + 独立 worker，测试入口仅替换模型，覆盖收藏→解析→关联→材料准备以及事实确认/编辑/历史。

前端必须截图并实际打开：桌面/手机、空状态、错误和长文本；记录发现、修复、复查。最后保存第八课、测试输出、截图与局部设计修订，完成本地提交，再进入 T09。
