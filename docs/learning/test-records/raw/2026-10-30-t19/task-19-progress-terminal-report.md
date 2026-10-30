# T19 真实终态进度修复

日期：2026-10-30。源码已冻结，后续真实浏览器由 root 运行。

## 实际问题和修复

岗位失败截图总状态已是“解析失败”，但“分析岗位要求”仍显示“进行中 100%”。后端 `run_events.py` 的真实终态投影使用 `stage=failed/cancelled,status=failed,progress=100`，阶段不是步骤 key；两个共享 composable 原来仅按 key 查找，未结束已有 running 步骤。独立的结果等待流还可能先向页面报错，进度流随后回放旧 running 事件又将任务复活。文档上传/重新解析共用相同协议，具有同样的问题。

修复仅在 `useTaskSse` 与 `useDocumentParseTasks`：

- failed/cancelled 投影只将已知 running 步骤变为 failed，保留 success/pending。
- 仅收到终态而没有已知 running 步骤时，不猜测失败步骤。
- 手动/API 失败统一结束已知 running 步骤；晚到的 running/pending 回放不能覆盖已知终态。
- 重连提示不覆盖终态；已经收到 cancelled 的终态不会被随后 API catch 改成泛化 failed 阶段。
- 未改 TaskProgress 样式、品牌、后端或浏览器夹具。

## 证据

第一次准备命令遇到环境没有 `python` 别名，测试文件尚未写入，原 7 项基线仍绿；这一轮不是 RED。改用 python3 后新增 8 个回归（两个只终态、不猜步骤的既有正确行为也被覆盖）。

- `/tmp/task-19-progress-terminal-red.txt`：6 failed / 9 passed，失败精确为两种终态残留 running、两处独立流回放复活。useTaskSse 测试通过实际 SSE ReadableStream 和序号解码；文档队列使用已受理订阅回调和实际异步上传 rejection 顺序。
- `/tmp/task-19-progress-terminal-green.txt`：两共享 composable + TaskProgress，17 passed，1.01s。
- `/tmp/task-19-progress-terminal-unit.txt`：全前端 28 文件 / 177 passed，5.73s。
- `/tmp/task-19-progress-terminal-build.txt`：vue-tsc --noEmit + Vite build 通过；主包 243.49 kB / gzip 86.26 kB。

范围：两 composable 和各自 spec，共四文件。没有新增状态类型、通用状态框架或兼容层。未启动预览服务、未录制。root 后续 jobs/recovery 6 浏览器将检查失败步骤数量及无运行中步骤，并重新截图。
