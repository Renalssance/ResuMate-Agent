# T15 后端实施报告

工作树：`/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`。基线：T14 `4fd1bd6`。本报告覆盖后端独立实现；无提交、无 paid model、无浏览器或全套测试，也未改共享 E2E fixture、worker、核心模型或数据库 schema。

## 已完成行为

### 1. 显式页面收藏入口

新增 `POST /api/jobs/capture`，复用既有 `JobCreate` 与 `{job,created}` 返回。服务 `capture_page_job(db,user_id,source)`：

- 有真实 sourceSite/sourceJobId 或无 URL 时，直接用既有 capture_job 的来源键/粘贴正文规则。
- 否则先核实所选主简历归属，再按本人 + 完整 sourceUrl 找最早已有岗位。MySQL 使用既有 utf8mb4_bin 大小写精确比较；query/fragment 保留。
- 已存在时返回旧行和 created=false，不覆盖手工 title/status/primaryResumeId、正文或更新时间；没有旧行时复用原保存。
- 原 `POST /api/jobs`、原 capture_job 查询、原 source pair 和 URL+body 规则没有修改，旧同 URL 不同正文创建新行的测试仍保留且通过。

新增行为测试同时证明 owner 隔离、重复捕获仍检查外部主简历、大小写/query/fragment 不合并、无 URL 与 source pair 仍走原规则。未新增数据表、模式 flag、哈希或并发去重体系。

### 2. 已确认版本作为填表来源

既有 profiles 列表追加本人 confirmed ResumeVersion，详情接受 version:<uuid>。原 resume:<int> 功能保持。summary/detail 均增加 sourceKind、resumeVersionId、revision、jdId；原简历后三项为 null。版本 sourceResumeId 为现存来源的 resume:<id>，源删除后为 ''；updatedAt 使用版本创建时间，UI 应标记“创建”。版本字段 source 为 resume_version。

字段从 structured_content.resume 冻结内容构造，与原简历共享小型 `_profile_sections` 映射，无临时假 ORM Resume。本人 draft 详情/匹配为409，他人或不存在为404；draft/他人不列入列表。源简历重解析或源简历/岗位删除后，冻结字段保持，空外键只影响来源 metadata。

accepted/edited 的工作/项目 description 明确为空时不恢复旧 bullets；self_summary 存在但为空时不恢复旧 summary。未编辑的旧描述/bullets 和缺少 self_summary 的旧 summary 仍可作为冻结内容回退。构造过程不改 SQL 冻结内容。

在线 /match 有 profileId 时优先服务端读取，不能用随请求附带的 profile 替换确认内容，也不能用 payload 绕过本人/草稿检查。没有 profileId 的现有 profile-only 功能保留。填表读取不写 Resume、ResumeVersion 或 JobApplication。

## 修改文件

- backend/routes/jobs.py、backend/services/jobs.py：新捕获入口，原导入代码不动。
- backend/schemas/autofill.py：summary/detail 来源 metadata。
- backend/services/autofill.py：原数据映射提取、冻结版本 mapper。
- backend/routes/autofill.py：列表/详情的版本归属与状态，以及 profileId 优先匹配。
- backend/tests/test_jobs.py：追加四个捕获行为测试，原测试未改。
- backend/tests/test_autofill_routes.py：去掉 Resume-only FakeDb/FakeQuery，改为现有 career_db/career_engine 的真实 SQL 请求会话；保留六个旧 HTTP 行为检查。
- backend/tests/test_autofill_versions.py：新增确认版本、冻结/清空、源删除、所有权与匹配优先级检查。

## 红绿与命令

所有命令在工作树根目录，双库参数均显式设置 `RESUMATE_TEST_MYSQL_SOCKET=/tmp/resumate-mysql-t02/mysql.sock`。career_fixtures 为每例创建临时数据库并清理，conftest 的 DATABASE_URL 未被用来替代这些测试实例。

1. `.venv/bin/python -m pytest backend/tests/test_jobs.py -k page_capture -q`
   - `/tmp/task-15-backend-capture-red.txt`：8 failed，SQLite/MySQL 各4。均因缺少 /capture 返回405，非 fixture/import 错误；据此增加明确入口。
2. `.venv/bin/python -m pytest backend/tests/test_jobs.py -k 'capture or duplicate or dedup' -q`
   - `/tmp/task-15-backend-capture-green.txt`：26 passed，12 deselected，SQLite/MySQL 各13；5条已有 SWIG import deprecation warnings。新旧来源合同同时通过。
3. `.venv/bin/python -m pytest backend/tests/test_autofill_versions.py backend/tests/test_autofill_routes.py -q`
   - `/tmp/task-15-backend-versions-red.txt`：12 failed、14 passed。失败分别为列表遗漏版本、版本详情404/草稿不区分409、匹配采用外带正文。旧六个 HTTP 用例双库通过，另两个“他人版本404”因此前不识别任何版本也通过，不能把这两个原始绿值当新权限覆盖证明。
4. `.venv/bin/python -m pytest backend/tests/test_autofill_versions.py backend/tests/test_autofill_routes.py backend/tests/test_autofill_profile.py backend/tests/test_autofill_matching.py -q`
   - `/tmp/task-15-backend-versions-green.txt`：38 passed，无 skip/warnings。14个版本 HTTP 参数化用例 +12个旧 HTTP 参数化用例在双库运行，另12个原 profile/matching 纯测试通过。

本次没有环境或实现意外失败需要额外迭代；红测是预期缺口，最小实现后一次定向绿测。最后查看本人 diff，确认原导入函数和原字段定义未被误改，仅清理新增函数前的额外空行；未重复全套测试。

## 实际限制和集成提示

- URL 捕获保证本次串行重采集合同；不同完整 URL（含追踪参数）视作不同来源。没有清理历史重复行，也没有承诺并发 exactly-once。
- 列表一次返回当前用户原简历及确认版本，保留原简历顺序、版本按创建时间倒序；本次没有分页需求或新列表框架。
- fixture 对核心所有权/冻结行为使用实际 SQL，auth dependency 为固定测试用户；真实扩展登录、消息来源、实际 browser content 以及 ZIP 均由扩展 owner/root 验收。
- 本次新增 HTTP 路由不触发模型、后台任务或投递写入。
- 主代理可开始后端/扩展实际集成；没有等待依赖或新用户审批。

## 建议教学要点

1. 同一业务数据可以有两种真实动作：导入保留 URL+正文合同，页面收藏按来源复用。用明确入口表达差异，比悄悄改变旧语义或添加模式开关更易审阅。
2. Profile ID 是服务端资料选择，不是让客户端上传另一个“同名版本”。在线读取权威确认内容，离线缓存是另一条明确路径。
3. 空字符串是用户的编辑结果，不等同于缺失值。`value or fallback` 可能复活已删除内容，必须以字段存在性和审核记录区分。
4. 外键 SET NULL 与冻结内容分离，允许删除源文档后仍查看已确认版本；这不意味着回读最新源简历。
5. 真实双库测试能覆盖 SQL collation 与 FK 删除行为。避免把原 FakeQuery 扩建成伪 SQL 引擎。
