# T02 增量数据库变更

`001_agent_and_versions.sql` 用于已经有 ResuMate 基础表的 MySQL 数据库，新增 Run、事实、简历版本、面试数据表，并给岗位和投递表加列。它不是新数据库的完整初始化脚本。空库先使用 `deploy/cloudbase/mysql-schema.sql` 建立原有表。

执行前备份目标数据库，确认尚未执行本脚本，再使用 MySQL 客户端读取脚本。不要加 `--force` 忽略错误。DDL 会隐式提交，失败时已有建表可能保留，不能假设事务自动回滚全部结构变更；检查已执行语句后从未执行处继续。脚本不删除旧表、旧列或业务行，不自动重试，也不新增通用迁移框架。

SQLite 由 `init_db()` 注册所有模型，先创建缺失表，再由 `ensure_sqlite_schema()` 补旧表缺列及索引；可重复启动。旧投递的 jd_id、resume_version_id、submitted_snapshot 保持 NULL。

本次实测 MySQL 9.6.0 和 Python 自带 SQLite，未在 CloudBase 远程数据库执行。CHECK 约束要求数据库实际支持并执行检查；不能拿本地测试替代目标数据库验收。

模型默认值（如 Run queued、attempt=1）由 SQLAlchemy 应用层填写；显式 SQL 写入新表时须填写 NOT NULL 字段。未来 worker 和 API 均通过同一业务服务写入。

本地 MySQL 验证使用独立临时实例，设置 `RESUMATE_TEST_MYSQL_SOCKET` 后运行：

```sh
uv run pytest backend/tests/test_agent_models.py backend/tests/test_resume_version_models.py -q
```

测试会在该 socket 指向的实例上创建随机 `resumate_test_*` 数据库并在结束后删除该测试库，不连接现有业务库。只将此变量指向测试实例。未设置变量时 MySQL 用例明确 skip，不能把这次结果写成双数据库通过。

## T08：岗位主简历

在已执行 `001_agent_and_versions.sql` 的 MySQL 库中，再执行 `002_jobs_primary_resume.sql`。它只给 `job_descriptions` 增加可空 `primary_resume_id`、索引及 `ON DELETE SET NULL` 外键；现有岗位、原文和人工标题保持不变，旧岗位关联为 NULL。沿用上面的备份、逐次执行和 DDL 失败恢复方式。SQLite 由 `ensure_sqlite_schema()` 追加该列与索引，可重复启动。

岗位定向双库验证：

```sh
RESUMATE_TEST_MYSQL_SOCKET=/tmp/resumate-mysql-t02/mysql.sock uv run pytest backend/tests/test_jobs.py -q
```

用例创建并删除独立测试库，验证去重、资源归属、分页、已有匹配、粘贴文本异步解析/失败重试以及主简历删除后关联置空。粘贴岗位复用既有 `JobProfile` 解析；匹配检索的是简历证据，因此不为粘贴 JD 额外调用 embedding。

## T12：模型容量与业务记忆

在已执行 001、002 的 MySQL 库中，一次执行 `003_context_and_memory.sql`。它增加可空模型上下文容量、Session 失效/清理时间和独立业务记忆表。旧模型容量保持 NULL，不根据模型名称猜测；旧会话状态保持 NULL。SQLite 沿用启动补表/补列，可重复启动。

记忆正文及来源在用户删除时清空；Session 两个时间戳区分“已停止使用”和“工作副本已清除”。它们不替代业务版本历史。沿用上述备份与 DDL 部分执行恢复要求。

定向验证 `backend/tests/test_memory_settings_models.py` 会先模拟 T11 结构，再执行 SQLite 启动升级或实际 MySQL SQL，验证旧行保留及新列空值；测试使用独立临时数据库。

## T14：持久长任务响应

在已执行 001、002、003 的 MySQL 库中，一次执行 `004_long_task_results.sql`，只给 `agent_runs` 增加可空 JSON `result_json`。空库完整顺序为 `deploy/cloudbase/mysql-schema.sql` → 001 → 002 → 003 → 004；不要重复执行基础建表脚本。旧 Run、事件和关联保持原值，旧结果为 NULL；本次迁移不从后来改写的业务表猜测历史响应。SQLite 由 `ensure_sqlite_schema()` 补列，可重复启动。

解析、匹配、问题生成、追问的原成功 HTTP 响应在业务写入、操作记录、事件与终态的同一事务保存。成功 Run 重放读取自己的响应，后来的显式问题生成不会替换旧 Run 的结果。仍沿用上述备份、检查目标结构及 DDL 部分执行恢复方式，无自动 MySQL DDL。

定向验证 `backend/tests/test_long_task_core.py::test_old_database_upgrade_preserves_existing_run` 会模拟立即前一版结构，在临时 SQLite/MySQL 库运行真实升级，确认旧 Run 保留且结果为 NULL。本地验证不代表已执行远程 CloudBase 升级。
