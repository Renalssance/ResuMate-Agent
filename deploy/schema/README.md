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
