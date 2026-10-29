# T11 投递快照后端交付

工作区：`/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`
基线：`de744e7`。未提交 Git；只改分配的 5 个文件。

## 实现

- 新增 `backend/services/applications.py:attach_submission`，调用者持有事务。
- `PUT /api/applications/{id}/submission` 接收 `{jd_id,resume_version_id}`；验证投递/JD/版本当前用户归属、confirmed 状态和版本对应岗位。
- 一次 `UPDATE ... WHERE submitted_snapshot IS NULL` 写冻结副本、JD、版本及原简历链接。重复相同材料返回原快照和原提交时间，换版本 409。并发写失败后 locking read 读取 MySQL 当前提交值，避免 repeatable-read 快照返回旧值。
- 首次关联同步 `resume_id = version.resume_id`，解决旧投递曾选另一原简历时材料身份不一致；该合同细化经主代理确认。已删除原简历的版本可保留 null。
- Create 增加成对可选 `jd_id/resume_version_id`；flush 后复用服务、创建状态事件、单次 commit，关联失败 rollback。旧请求不带新字段继续正常创建。
- PATCH 的 `resume_id` 在已提交记录上只能回传原值；公司、职位、日期、状态、备注与日程正常编辑。PATCH 不提供 JD/版本/客户端快照写入字段。
- ApplicationRecord 增加 nullable `jd_id/resume_version_id/submitted_snapshot`。原文修改/删除不更改快照。

快照合同（已通知前端代理）：

```text
{
  resumeVersionId: string,
  revision: number,
  jdId: number,
  structuredContent: object,
  factRefs: array,
  submittedAt: ISO UTC string
}
```

错误沿现有 applications HTTPException detail 字符串；版本未确认/岗位不符/替换材料 409，跨用户或不存在 404，Create 单边关联字段 422。

## 每项检查的故障目标与行动

1. 首次/重复/换版/并发关联测试：检测快照未冻结、原提交时间重写、后到请求覆盖已提交材料；失败则修正条件更新和当前值读取。
2. 归属/版本状态/岗位匹配测试：检测跨用户读取或错误岗位/草稿被关联；失败则修正对应业务校验。
3. Create 配对与事务测试：检测请求被静默忽略、关联失败留下空投递或状态事件；失败则修正 schema 与 commit/rollback 边界。
4. PATCH、原文修改和删除测试：检测普通编辑替换提交材料或历史内容随主文档漂移；失败则收窄 PATCH 写入和快照来源。
5. 原 applications CRUD/日程测试：检测新增字段和路由改变既有投递与日程行为；失败只修受影响的投递逻辑。
6. 限定文件差异检查：检测范围外修改或格式损坏；发现后撤回无关改动/修正格式。

## TDD 原始证据

单元 1（接口、单次快照、归属、并发）：

- `/tmp/task-11-submission-unit1-red.log`：11 SQLite 失败，11 MySQL 跳过（首轮未传 socket），失败均为缺失 PUT 端点返回 405。
- 实现后 `/tmp/task-11-submission-unit1-green.log`：22 passed，真实 SQLite/MySQL，无跳过。

单元 2（原子创建、配对 schema、PATCH 保护）：

- `/tmp/task-11-submission-unit2-red.log`：20 failed、4 passed、22 deselected，两库失败为新建忽略关联字段/错误配对仍200，以及已提交记录能改变原简历。4 条已正确路径为普通字段/日程编辑和原简历变更后快照保留。
- 实现后 `/tmp/task-11-submission-unit2-green.log`：53 passed、7 warnings，含 46 两库投递用例与 7 原 CRUD/日程用例，无跳过，9.93s。

最终定向命令：

```sh
RESUMATE_TEST_MYSQL_SOCKET=/tmp/resumate-mysql-t02/mysql.sock .venv/bin/python -m pytest backend/tests/test_application_submission.py backend/tests/test_applications_routes.py -q
```

7 条警告来自既有 SWIG 类型与 FastAPI on_event 弃用。限定 `git diff --check` 通过。未运行全后端、导出/PDF、前端或 E2E，交给主代理统一整合，避免重复检查。

## 改动文件

- 新增 backend/services/applications.py
- 修改 backend/routes/applications.py
- 修改 backend/schemas/applications.py
- 新增 backend/tests/test_application_submission.py
- 修改 backend/tests/test_applications_routes.py（旧记录新增字段为 null 的断言）

无 DDL、无导出 Run/API、无配置、无前端改动。现有旧投递 CRUD、状态事件、日程和原简历删除外键行为正确，未额外改造。
