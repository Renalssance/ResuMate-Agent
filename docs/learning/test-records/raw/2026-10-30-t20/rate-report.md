# T20 B：Redis 限流实现与定向验证

## 完成范围
- 用 RedisRateLimiter(commands, namespace) 完整替代进程内计数器与生产 RATE_LIMIT_ENABLED 绕过；namespace 使用完整 resumate:{env} 前缀。
- 每次检查仅一次 EVAL，Lua 原子 INCR、首次 EXPIRE、PTTL；auth IP 5/60、chat SQL user 20/60、run SQL user 10/60。拒绝 Retry-After 至少 1 秒，Redis 错误统一 RedisUnavailable → 503，无本地回落或自动重试。
- 动态读取 request.app.state.rate_limiter；认证 dependency 复用原 get_current_user 对象，不另行解码 bearer。
- 9 类受理路由在 SQL/文件副作用前执行 run 限流；auth/chat 接入对应 scope。RunRoute 503 为 dependency_unavailable，保留 requestId；429 保留 Retry-After。GET/cancel/action 不拦。
- conftest 默认 tests-only controlled service，real_redis marker 显式退出；未修改旧 HTTP 测试的 auth overrides。

## 证据
- /tmp/task-20-rate-red.txt：34 failed, 1 passed。失败为新 Redis 合同与依赖未实现。
- /tmp/task-20-rate-green.txt：35 passed，1.57s。覆盖阈值、TTL、作用域键、单次 EVAL、三种 Redis 错误、9 路径 429/503 副作用边界、原 auth override、未认证、重复接受、读取/取消/action、动态 app.state。
- /tmp/task-20-rate-legacy-green.txt：18 passed，4.19s。9 个已有文档/岗位/Run 受理与归属测试，SQLite/MySQL 双参数。

## 限制与后续
上述 mock 合同测试不证明真实 Redis 原子性；另由本代理继续实现并运行一次真实双 API/MySQL/Redis/worker 集成。未运行全量套件、未提交、未调用付费模型。
