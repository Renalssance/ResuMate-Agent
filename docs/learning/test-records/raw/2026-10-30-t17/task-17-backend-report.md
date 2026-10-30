# T17 后端/负载报告（已完成）

## 当前范围
只新增负载fixture/脚本和明确MySQL池，未改既有run_events、jobs、worker、文档处理或模型客户端；无付费调用。

## RED→GREEN
- `/tmp/task-17-load-red.txt` 3 failed → `/tmp/task-17-load-green.txt` 3 passed：统计必须保留超时、空样本、SSE缺失和重复。
- `/tmp/task-17-load-order-red.txt` 1 failed/3 passed → `/tmp/task-17-load-order-green.txt` 4 passed：收到全部帧但乱序不能通过。
- `/tmp/task-17-pool-red.txt` 真实临时MySQL第11个checkout仍成功，1 failed/1 SQLite专用skip；设置pool_size=5/max_overflow=5/pool_timeout=5后 `/tmp/task-17-pool-green.txt` 5 passed/1 skip，5.47秒，含SQLite旧pragmas回归。

## 固定源码基线（已完成）
- 命令：`.venv/bin/python tests/load/api_sse.py --output /tmp/task-17-baseline --source-ref cdde2c5`。
- `/tmp/task-17-baseline.txt` 完整原始输出；目录 `/tmp/task-17-baseline/` 保存source、runtime-verification、SQL EXPLAIN、环境、全部API/SSE样本、metrics与docker stats。
- 独立项目resumate-t17-cc9a382585已按项目名清理容器/卷；未停止其他容器/用户4173预览。
- Docker29.9.2 VM实际10vCPU / 8319504384 bytes。所有产品和driver配置cpuset0-3，稳态产品mem_limit6.75GiB + driver0.5GiB=7.25GiB。未更改Docker全局资源。
- 严格依赖镜像resumate-t20-deps:aligned，完整cdde2c5源码+本轮负载fixture挂载，runtime-verification差异/缺失均空；不等于fresh生产Dockerfile通过。
- SQL实际数量：{'users': 1, 'job_descriptions': 10000, 'agent_runs': 10, 'agent_run_events': 50000}；每岗位原文2232字节。10Run各5000事件，源始终waiting_input，scheduler不会制造模型请求。
- API每阶段20并发，预热10秒、正式60秒；5接口（岗位首页/搜索/offset8000深页/详情/Run快照）分别存样本与P95。所有样本均200且JSON结构正确。

|阶段|样本|总体P95 ms|最慢接口P95 ms|错误|
|---|---:|---:|---:|---:|
|api_only|18097|160.870|197.395|0|
|api_with_30_sse|13679|206.242|255.130|0|

- 30条SSE：300次独立SQLcommit / 900次完整交付，P95=498.170ms，缺失/重复均0。时钟均为同LinuxVM monotonic，commit返回后时间另存ledger，未拿createdAt冒充commit。
- 6条真实TCP断开后，追加SQL事件，再跨另一API用游标重连；可见时间15.131ms，缺失/重复0。这是Python订阅网络恢复，不冒称浏览器已测。
- 1条慢客户端从0读取5000事件，另29条交付P95=491.353ms，145/145完整。API最终checkout均0，旧默认池峰值均15。
- 基线所有端点已达300ms预算，因此不改岗位list ORM投影/排序/索引，也不改正确的SSE分页；避免把可想象的优化当已证明瓶颈。

## Final待执行边界
下一轮因显式10连接池、Nginx代理与T18当前源码变化才复测。等待B文档子进程Redis生命周期最后GREEN，然后捕获完整生产backend/frontend dist/nginx；使用独立快照不会受随后T19写入影响。
通过proxy的业务GET/SSE走生产nginx；测试append/metrics仍直连API，不往生产反代添加测试路由。proxy256MiB加入后产品+driver总上限7.5GiB，全部同0-3。
原始基线通过不等于final通过，不等于真实模型/浏览器/部署性能通过。


## Final真实代理复测（已完成）

- 命令：`.venv/bin/python tests/load/api_sse.py --output /tmp/task-17-final --source-directory /tmp/task-17-final-source --proxy`。
- 原始stdout `/tmp/task-17-final.txt`；完整产物 `/tmp/task-17-final/`。产品来源 `/tmp/task-17-final-source` 为root明确freeze后捕获的完整backend/deploy/frontend/dist及lock；baseline=cdde2c5，working-tree.patch另存；后续T19改动不混入此次源码。执行时再复制到final/source，负载fixture/脚本同轮保存。
- Docker Hub nginx拉取匿名token EOF，原日志 `/tmp/task-17-nginx-pull.txt`；改用项目现有public ECR官方镜像路径成功，原日志 `/tmp/task-17-nginx-ecr-pull.txt`。没有重启Docker/清其他镜像，也未把下载失败算产品失败。实际Nginx1.30.6。
- 代理容器256MiB纳入资源预算，最终全部产品+driver相同cpuset0-3，mem_limit总和7.5GiB，VM真实10vCPU/8319504384bytes如实记录；不宣称VM本身4CPU或完整云服务器性能。
- 实测生产GET与SSE均经Nginx；append/metrics为tests-only直连API控制面，不添加到生产代理配置。两个API均实际承接流；30条稳态连接存在，重新连接瞬间峰值另记录。
- 20并发API无SSE：19,998样本，P95 151.929ms；30SSE并行：13,046样本，P95 214.569ms；两个阶段每个接口均P95<=300ms，全部200且JSON有效，0error/5xx/timeout。warmup10秒、正式60秒，实际测量时长/请求率另存report。
- 300次SQL提交/900次交付：P95 501.134ms，缺失/重复/乱序/负时间样本均0。
- 6条实际TCP中断期间写事件，经Nginx重新连接后14.159ms可见，完整补齐；这是Python客户端恢复，不是浏览器5秒结论。基线另有显式跨另一个API直连恢复证据。
- 1慢客户端读取5000历史帧时，其余29条145/145新事件完整交付，P95 492.501ms；这证明此实际输入下低速读取不阻断其他连接，不宣称已穷尽OS/socket所有背压形态。
- 最终负载exit0、report.passed=true；只重测了显式池/代理/当前源码变更相关场景，没有为好看数字重复挑最好一次。最终独立项目resumate-t17-1a63241a32已按项目名清理容器/网络/卷，user4173与其他容器不变。A/B已获可以继续浏览器/镜像构建的通知。

最终进程资源：

```json
[
  {
    "at_ns": 2824221442456,
    "api": 0,
    "checked_out": 0,
    "peak_checked_out": 10,
    "sql": 45692,
    "streams": 0,
    "peak_streams": 15,
    "hostname": "1dcb4b2eeb8a",
    "pid": 1,
    "max_rss_kib": 336532,
    "rss_kib": 336732,
    "pool": "Pool size: 5  Connections in pool: 5 Current Overflow: 0 Current Checked out connections: 0"
  },
  {
    "at_ns": 2824229536456,
    "api": 1,
    "checked_out": 0,
    "peak_checked_out": 10,
    "sql": 44169,
    "streams": 0,
    "peak_streams": 17,
    "hostname": "a0a105e21d54",
    "pid": 1,
    "max_rss_kib": 334000,
    "rss_kib": 334272,
    "pool": "Pool size: 5  Connections in pool: 5 Current Overflow: 0 Current Checked out connections: 0"
  }
]
```

各API的实际RSS与checkout样本均在metrics.jsonl。显式池峰值不超过10，末尾checkout=0、streams=0，未发现会话/流泄漏；慢消费者期间RSS仅在本次数据量下观测，不据此推断无限期运行。

## 最终交付/教学边界

- 新脚本包含样本统计/丢帧乱序门禁、受约束独立Compose、固定seed、真实commit时钟、TCP续传/慢读、完整原始证据；统计测试4passed、真实池/SQLite回归5passed1skip（总9passed1skip，分两次运行，不冒充一次suite）。
- 原有run_events的100分页、复合索引、短Session和0.5s轮询实测已足够，没有新索引/缓存。岗位深页P95仍在预算内，未改jobs以免没有证据的优化。
- 负载为合成资料且只读API/受控append，没有供应商调用、真实模型任务排队/生成/工具质量指标；后者明确未测。浏览器performance由A/root另交，不从Python网络恢复代替。
- T19 fresh生产镜像与四个实际恢复实验尚未由本报告证明；后续按root分配独立执行。
