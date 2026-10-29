# T11 导出后端实施记录

工作区：`/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`；基线 `de744e7`。本代理未提交。

## 已实现

- RunCreate 维持现有类，新增 resume_export 的有限字段分支；tailoring 原行为保留。
- 通用创建与 `/api/resume-versions/{id}/export` 共用 create_run，保存 confirmed ResumeVersion ID/revision，requestId 幂等与冲突校验，数据库提交后发布。
- export 重试仅验证冻结版本归属/confirmed/revision；不重读主简历、岗位或模型上下文。
- worker 按 kind 明确分派，PDF 不进入模型；未知 kind 明确 failed。复用领取、心跳、取消、扫描和执行锁。
- renderer 接口：`backend.services.resume_export.render_pdf(structured_content: dict, output_path: pathlib.Path) -> None`。同步 Python Playwright；`render_html` 与 `build_template_data` 只从冻结内容构造正文。
- Chromium 打印前提交短读取事务；写 `.{run.id}.tmp.pdf`，新事务 guard 后 replace，artifact.created/output_refs/finish 一次提交。失败保留人工 retry，取消与失权清理临时文件。
- `/api/agent/runs/{id}/artifacts` 按数组返回；版本条目新增 kind=resume_version；PDF 条目有 id/runId/resumeVersionId/revision/filename/downloadUrl/createdAt。详情版本接口形状不变。
- PDF 下载先查 Run 归属，以 SQL succeeded+对应 output_ref 为准；其他账户404、未成功409、文件缺失404 artifact_missing。附件文件名 `简历-第{revision}版.pdf`。没有静态目录公开挂载。
- 固定白纸暖棕中文模板；姓名联系、简介、完整教育、工作、项目、技能、奖项、证书、语言。用户文本自动转义；URL按文本；禁用脚本并阻断外部请求。
- T10交界：明确清空的简介不回退，accepted/edited description不复活旧bullets或metrics；未修改的独立bullets和metrics保留且去重。metrics 由 raw_text 或 `name valueunit` 构成。

配置目录读取 `RESUME_EXPORT_DIR`，缺省 `data/exports`。依赖、Docker、Compose、字体和E2E配置由主代理负责，未在本代理任务中改动。

## TDD 证据

以下命令在工作区执行；双库命令均显式设置 `RESUMATE_TEST_MYSQL_SOCKET=/tmp/resumate-mysql-t02/mysql.sock`。每项测试前已说明具体检测失败及修复行动。

1. API/冻结输入/retry 单元：`.venv/bin/pytest backend/tests/test_resume_export.py -q`
   - `/tmp/t11-export-api-red.txt`：8 failed、6 passed。导出kind不支持、便利路由缺失、重试不能创建导出Run。
   - `/tmp/t11-export-api-green.txt`：14 passed。一次中间MySQL测试失败来自测试保留旧读事务，结束测试读事务后读取API提交结果通过；产品无需为测试快照改动。
2. 模板单元：`.venv/bin/pytest backend/tests/test_resume_export.py -q -k template`
   - `/tmp/t11-export-template-red.txt`：2 failed（render_html缺失）。
   - `/tmp/t11-export-template-green.txt`：2 passed、14 deselected。
3. renderer/worker/事务/下载单元：`.venv/bin/pytest backend/tests/test_resume_export.py -q -k 'real_renderer or worker or incomplete'`
   - `/tmp/t11-export-worker-red.txt`：11 failed、16 deselected。真实renderer缺失；export与未知kind进入模型替身立即失败；runner缺失。
   - `/tmp/t11-export-worker-green.txt`：完整新导出文件27 passed。
   - 真实Chromium打印英文文本PDF并由PyMuPDF读取。数据库生命周期测试仅替换慢打印函数，其余Run/SQL/路由/worker分派使用真实实现；打印替身写的是测试bytes，不作为真实PDF验收证据。
   - 打印替身期间以独立SQL连接执行heartbeat，验证浏览器打印不占数据库写锁；取消、异常、失权分别检查没有成功ref、artifact事件和可下载文件。
4. 受影响回归：`.venv/bin/pytest backend/tests/test_resume_export.py backend/tests/test_agent_run_routes.py backend/tests/test_agent_workspace.py backend/tests/test_worker_delivery.py backend/tests/test_resume_review.py backend/tests/test_resume_versions.py -q`
   - `/tmp/t11-export-regression.txt`：175 passed、4 failed、1 skipped。4失败仅是两条版本artifact数组精确断言缺新增kind（每个在两库执行）；已按已批准合同对齐。其余共享Run/worker/审阅检查通过。未重跑已通过且不受后续模板改动影响的整个集合。
5. 独立审查发现真实支持的metrics遗漏，复现参考 `test_resume_parsing_pipeline.py` 中独立吞吐指标：
   - `.venv/bin/pytest backend/tests/test_resume_export.py -q -k independent_metrics`
   - `/tmp/t11-export-metrics-red.txt`：1 failed、27 deselected（缺少“吞吐”）。
   - `/tmp/t11-export-metrics-green.txt`：全部模板检查3 passed、25 deselected；清空/接受正文后不恢复旧指标。
6. 最终针对新增导出与刚修正的版本artifact合同回归：`.venv/bin/pytest backend/tests/test_resume_export.py backend/tests/test_resume_versions.py -q`
   - `/tmp/t11-export-final-focused.txt`：72 passed，13.33秒。当前新导出文件28项 + 版本文件44项。

既有7条warnings来自PyMuPDF SWIG与FastAPI on_event弃用，不是本次新增运行失败。

## 交接与限制

- 主代理已收到稳定renderer/API接口，可进行真实API+Celery+浏览器下载与投递关联E2E。
- 中文两页样例、每页PNG实际查看、实际deploy/worker.Dockerfile的Linux打印与字体，以及完整后端整合由主代理完成；本报告不以本机英文PDF或测试bytes替代该证据。
- 本代理不改前端、applications、依赖和配置；唯一既有测试合同更新是test_agent_workspace.py与test_resume_versions.py的产物kind。
- 所有新增产品/测试代码在共享隔离工作树，无需cherry-pick。
