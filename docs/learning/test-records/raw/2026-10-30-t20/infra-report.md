# T20 A infrastructure / lifecycle report

Implementation frozen after T15 baseline a1568bc. This report covers A's owned changes only; root/B own Redis business primitives, limiter, usage, shared integration and full regression.

## Changes

- New `backend/infrastructure/redis_client.py`: `RedisUnavailable`; process-local `AsyncRedisResources(commands,notifications,namespace)` with `aclose`; `create_async_redis_resources`; `redis_namespace()` returns the full `resumate:{env}` prefix; explicit `init_sync_redis/get_sync_redis/close_sync_redis`. Sync getter fails without lifecycle initialization or after PID change; it never creates one client per usage record.
- Command clients use 1-second connect / 2-second read, explicit zero automatic retries. Async notification client owns a separate pool with no idle socket read timeout. Creation does not PING or depend on Redis availability.
- API lifespan initializes DB/resources/limiter, starts the actual InterviewHints reader and stores `app.state.redis`, `rate_limiter`, `interview_hints`. Shutdown stops/awaits reader before closing async pools and the process sync pool, including exceptional application exit.
- Celery existing child initialization still disposes inherited SQL pool (`close=False`) and now initializes the child sync Redis client; child shutdown closes it. Existing one-worker delivery/recovery policy unchanged.
- `warn_redis_capacity()` observes INFO memory during the existing recover_runs scan. At 80% of configured memory (excluding mem_not_counted_for_evict) it emits namespace/used/max/ratio WARNING. Missing process resources or Redis failure logs only error type and does not raise into SQL recovery. No new periodic task or monitoring platform.
- Main Compose now has MySQL 8.4, schema one-shot, api/api2, Redis, one worker and scheduler. Same MySQL for all business processes, no Redis/MySQL host ports, Redis AOF/maxmemory=256mb/noeviction with 512MiB container limit. Only worker mounts agent-state at `/app/agent-state`, outside shared uploads/exports data.
- Current SQLite topology preserved as test fixture `backend/tests/fixtures/compose.sqlite.yaml`, build context fixed to repository root. Only base-config paths changed in test_worker_compose.py, test_resume_export_compose.py, test_agent_recovery.py.
- `.env.example` documents native versus shared-MySQL Compose variables, namespace, two API ports, required worker and URL-safe Compose password inputs. Removed RATE_LIMIT_ENABLED from both env examples per root/B decision. No production bypass added.

## Verification purposes and raw results

1. Detect missing Redis resource API / wrong retry, timeout or pool separation / reuse after close or fork. Initial RED: **4 failed** (missing infrastructure module); after implementation **4 passed**.
   - `/tmp/task-20-infra-red-resources.txt`
   - `/tmp/task-20-infra-green-resources.txt`
2. Detect application/worker entrypoints failing to create/close otherwise-correct clients. RED: **3 failed, 4 passed** (no app.state.redis; uninitialized worker sync pool); GREEN: **7 passed**.
   - `/tmp/task-20-infra-red-lifecycle.txt`
   - `/tmp/task-20-infra-green-lifecycle.txt`
3. Detect reader shutdown after pools close / capacity failure escaping to caller / incorrect 80% and buffer calculation. RED: **7 failed, 7 passed** (missing hints lifecycle and capacity helper); final GREEN: **14 passed, 5 existing Swig warnings**, 1.05s.
   - `/tmp/task-20-infra-red-hints-capacity.txt`
   - `/tmp/task-20-infra-green-final.txt`
4. Detect new main topology silently using SQLite, separate DBs, exposed broker, API checkpoint mounts, wrong schema dependency, or moved fixture resolving the wrong build directory. Docker Compose config JSON assertions all passed; no container was started by this check.
   - `/tmp/task-20-infra-compose-config.txt`
   - Reproduction script `/tmp/task20_check_compose.py` uses dummy configuration-validation-only secrets and prints a nonsecret summary.

The lifecycle tests create actual redis-py clients but do not connect to a Redis server; they are not claimed as Lua/GETDEL/PubSub cross-process integration. Root/B run actual shared-MySQL dual-API integration. A did not run the backend full suite or paid models and did not commit.

## Independent C/D read-only review

Inspected dashboard_cache, llm_settings, settings route/schema, auth/security, ws_tickets, realtime_bus and interview_events. One real issue found: the `/settings/usage` auth SQL Session remained open over Redis awaits despite the service's own short Sessions. Root added a targeted two-dialect RED, fixed the route to capture user_id/factory then close the request Session before await, and reported 22 relevant GREEN. A read the final route and confirmed the fix, without rerunning those checks.

Other reviewed contracts are correct for current supported use: record_llm_usage SQL commit precedes best-effort DEL; cached payload excludes recent calls and credentials; original JWT expiry is read from verified claims; GETDEL is single-use and consumption checks that original expiry; hints only wake local watchers, SQL event reads enforce ownership and use fresh short Sessions. No speculative malformed operator input finding was added.

## Additional authorized legacy representative

Root requested exactly one current-image execution of test_resume_export_compose.py after the shared current T20 image is built, to prove the moved SQLite fixture and worker lifecycle still produce a real Linux Chinese PDF. This test is gated by RESUMATE_PDF_COMPOSE_TEST=1 and hardcodes the resumate-t11-worker image alias. A coordinated with B to reuse its new image via that alias rather than test stale T11 code or build a second image. Result will be appended after the actual run; no pass is claimed here yet.

### Legacy representative status update

B reported the shared current-image build failed while exporting/unpacking because Docker Desktop containerd snapshot storage was read-only. Its integration cases were setup errors with executed=false. Root directed A to wait, with no parallel image build/restart/tagging. Therefore the old SQLite PDF representative has **not run**; there is no current-image legacy PDF pass/fail result yet. A's 14 unit results and Compose config assertions remain the completed evidence. This environment problem is not reported as a product failure.

## Fresh shared-volume integration finding

B 的真实双 API fresh-project 启动复现 Docker 并发 copy-up 冲突（`backend-data/_data/agent: file exists`）。已将主 Compose x-backend 与 worker 的 backend-data 挂载改为显式 `volume.nocopy: true`；业务按原实现创建所需目录，旧 SQLite bind 夹具不变。配置断言先 RED（api 未禁用 copy-up）后 GREEN（api/api2/worker 均为 nocopy）。原始日志：`/tmp/task-20-infra-red-nocopy.txt`、`/tmp/task-20-infra-green-nocopy.txt`；B 已获通知使用新的 fresh project 复验真实启动。

## Legacy SQLite PDF representative: completed

Docker 恢复后，复用 B 已完成的依赖对齐镜像 `resumate-t20-deps:aligned`。其运行时依赖核验为 `missing_direct_dependencies=[]`、`lock_version_differences={}`。本实验不构建或改 tag；tests-only PDF 夹具新增 `RESUMATE_PDF_BASE_IMAGE`，始终复制当前完整 backend 与 pyproject/uv.lock 到证据目录并只读挂载 `/app/backend`，所以未运行旧镜像内的旧生产源码。

目的：检出旧 Compose 夹具搬迁后的路径错误、当前 API/worker Redis 生命周期回归、实际 Linux 字体/PDF 导出或认证回归；若失败则据本次容器日志定位该项，不重跑四个崩溃实验。原环境阻塞已解除，本次是恢复后唯一 PDF 运行。

执行：`RESUMATE_PDF_COMPOSE_TEST=1 RESUMATE_PDF_BASE_IMAGE=resumate-t20-deps:aligned .venv/bin/python -m pytest -q -s backend/tests/test_resume_export_compose.py --basetemp=/tmp/task-20-legacy-pdf-20261030-741bc9`（PATH 包含 Docker.app CLI）。

结果：**1 passed, 5 existing Swig warnings in 14.17s**。真实 Linux Celery worker；Noto Sans CJK SC；PDF 2 页、提取文本 1218 字符；重复 requestId 复用 Run、正确 outputRefs、认证下载、匿名 401、artifact 列表均通过。容器/网络/专用 Redis 卷已按 fixture 清理，无付费模型。

原始输出：`/tmp/task-20-legacy-compose.txt`。
持久目录：`/tmp/task-20-legacy-pdf-20261030-741bc9/test_linux_worker_exports_extr0/pdf-evidence/`，包含 resume.pdf、page-1.png/page-2.png、extracted-text.txt、compose.log、pytest.txt、完整 source/backend + pyproject.toml/uv.lock，并复制依赖核验与对齐镜像构建原始证据。目录独立于 pytest 自动保留/清理的默认根。
