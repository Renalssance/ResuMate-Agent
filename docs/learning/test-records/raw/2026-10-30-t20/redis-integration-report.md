# T20 真实 Redis 集成报告

实现与定向验证完成；未提交、未重复全量后端测试、没有付费/外部模型调用。

## 最终实际执行

- 命令：`RESUMATE_REDIS_INTEGRATION=1 RESUMATE_REDIS_BASE_IMAGE=resumate-t20-deps:aligned .venv/bin/python -m pytest backend/tests/test_redis_integration.py -q -s`
- 结果：7 passed，5 warnings，86.52s。warning 为现有 SWIG 导入弃用提示。
- 日志：`/tmp/task-20-redis-integration-nocopy.txt`。
- 独立 invocation：`723a546aee5345e294ef62a0ab12f421`。
- 完整证据：`/tmp/task-20-artifacts-723a546aee5345e294ef62a0ab12f421/`，包含 evidence.json、commands.txt、当前完整 backend/deploy/测试/lock 快照、runtime 包清单与版本对照、小型依赖对齐 Dockerfile/build 日志。
- Compose project `resumate-t20-723a546aee`；测试结束已 down --volumes --remove-orphans，仅清理该独立栈。

## 七个场景及观察

1. **拓扑**：两个独立 API hostname；同一 MySQL 8.4.13 / resumate 库与 7 个 seed 用户；Redis 7.4.12 / redis-py 6.4.0；相同环境 namespace。Redis noeviction/256MiB；两个 API 均看不到 /app/agent-state；仅 worker 能持有该目录中的执行锁。
2. **原子限流**：20 次跨双 API 并发 run 请求，恰好 10 个 200、10 个 429；拒绝 Retry-After >=1。窗口剩余 TTL 59740→58550ms，没有续期。不同 SQL 用户、chat scope 分离；跨 API 同 IP 的 auth 请求前 5 次到认证并返回401，第6次429。
3. **一次性票据**：真实 SET/GETDEL；跨两 API 并发消费一次成功，重放 None；用户/面试/原始 JWT exp 固定，TTL <=30秒；短票据到期后 None；其他 owner404、已过期/缺exp认证401。证据不保存票据值或 Bearer。
4. **缓存**：20 次双 API 交替 GET，仅 3 条聚合 SQL（一组 cold 填充）+20 条 recent SQL；含鉴权共43条。用户2数据隔离。真实 Celery 子进程执行生产 record_llm_usage，SQL提交后删除 stats key，下一 GET 得2次调用/35tokens；30秒TTL自然到期再执行一组3条聚合查询。
5. **提示与 SQL 补查**：API2先watch并初读SQL；API1提交seq1后publish，实际27.98ms收到。关闭API2 reader，SQL写seq2且不publish，1.758s补查返回（<=3s）。恢复reader后重复提示不重复输出seq3/4；异用户404。这是 tests-only consumer 的机制验证，不是真实WebSocket验收。
6. **停机/发布间隙/恢复**：真实限流通过、SQLcommit后测试barrier暂停publish；停止Redis再释放，原API仍202，Run保持queued。9类生产受理均503，SQL Run/Document数量与上传文件列表一致；票据发放/消费503。record_llm_usage 的DEL失败不撤销提交，dashboard回SQL得3calls/44tokens。GET/cancel/action与持久事件读取可用。恢复Redis及原scheduler/worker后，同一Run成功，attempt1/epoch1、1份ResumeVersion、1条ToolOperation、1个succeeded终态事件，真实checkpoint存在；未手动finish或改该Run状态。重启后双API同一新用户仍严格10/20；新票据可消费，seq6可读取。
7. **独立 OOM**：单独8MiB Redis填充到真实OOM，再将限额降到1字节固定写拒绝状态。noeviction保留已有queue-marker；生产容量helper输出redis_capacity_high；真实limiter/ticket写入转RedisUnavailable，cache写失败仍正确回SQL。没有修改主broker内存策略。

## 真实发现及修复归属

- 限流 B 实现与原路由53项定向结果另见 `/tmp/task-20-rate-report.md`。
- fresh主Compose首次同时创建api/api2/worker时，共享backend-data copy-up实际报 `mkdir .../agent: file exists`。A将共享卷改为 `volume.nocopy: true`，配置RED→GREEN；最终本次fresh并行启动证明该修复有效。未用测试串行启动遮蔽问题。

## 镜像与环境限制（仍需如实保留）

生产Dockerfile当前源码完整构建首次在export/unpack阶段遇到Docker Desktop只读文件系统，宿主剩余约158MiB。该次业务 executed:false，7个setup errors，证据 `/tmp/task-20-artifacts-241c20c7e4984135b53338a248caa55f`，日志 `/tmp/task-20-redis-integration-first.txt`。

确认没有运行容器后仅重启Docker Desktop一次；按根授权精确删除本任务旧resumate-test-*、本轮失败镜像及未共享缓存记录，保留T11底座/所有既有卷/其他镜像。清理本轮3.33GB废弃层后恢复空间；日志 `/tmp/task-20-docker-{restart,disk,task-cleanup}.txt`。旧底座uv cache实际627MiB、venv626MiB。

旧T11镜像直接复用核验发现6项锁版本不符（googleapis-common-protos及OTel组件）；第二次环境核验正确失败，未执行业务，证据 `/tmp/task-20-artifacts-647e42b191b84d43b79fa5c2f5cfa330` 与 `/tmp/task-20-redis-integration-recovery.txt`。随后构建仅测试依赖层 `FROM resumate-t11-worker:latest` + 当前pyproject/uv.lock + `uv sync --locked --no-dev --no-install-project --no-cache`，实际2.2秒成功。最终全部已安装且存在于lock的包版本差异为{}，缺失direct依赖为[]，生产源码全量挂载当前独立快照。

对齐后第三次启动遇到上述fresh-volume冲突，仍executed:false；证据 `/tmp/task-20-artifacts-21db45b0c76e472ab9d2e615f0d36520` 与 `/tmp/task-20-redis-integration-aligned.txt`。最终第四次为全部7个业务场景成功。

因此本轮证明当前完整源码+精确依赖版本的真实跨进程行为；**不声称生产Dockerfile完整新构建成功**，T19镜像交付仍需处理缓存与完整构建。未证明T16完整面试命令、T21真实WebSocket或压力性能。

## 文件

- backend/tests/test_redis_integration.py：显式集成门禁、独立project/证据、7个真实场景；Docker从PATH获取，Mac为fallback；默认build当前镜像，受限环境可显式给测试依赖镜像并严格核验版本。
- backend/tests/fixtures/redis_api.py：仅测试seed、查询计数、票据/consumer观测与commit后publish barrier；生产路由、认证、limiter和Run算法不被替换。
- backend/tests/fixtures/redis_worker.py：既有确定性DraftModel与调用生产usage写入口的真实Celery测试任务。
- backend/tests/fixtures/redis_oom.py：隔离OOM实例，使用生产Redis资源/limiter/tickets/cache/capacity helper。
- compose.redis-integration.yaml：仅测试入口、当前源码快照mount、统一image与独立OOM profile。

## 最终清理核对

末尾原始 `down` 返回0但日志显示network仍被profile中的OOM容器引用。仅测试清理语句现已改为显式 `--profile oom down --volumes --remove-orphans`；对本轮原project执行该确切命令，OOM容器与network均删除，按project label查询容器和network均为空。证据 `/tmp/task-20-redis-cleanup-green.txt`。这是测试收尾修正，未改业务源码或重跑已绿7场景；原source快照保持as-run，根归档最终测试源码时包含该一行修正。

对最终commands/API原始日志按认证header/数据库连接串/环境密码赋值检查均为0；测试只把票据放HTTP JSON内存中，不把票据值传CLI或归档响应；日志中只有票据端点路径。随机数据库/JWT秘密只作为进程环境传给Compose，不输出resolved config。归档保存claims归属/exp、配置占用和查询数，不保存Bearer、票据原值或数据库密码。
