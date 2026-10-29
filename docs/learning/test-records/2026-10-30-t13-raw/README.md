# T13 原始测试记录

保留红/绿与中间失败，不删除失败行。早期日志和 `core-first-*` 是当时结果，不代表最后修复后的执行。localhost 假供应商测试不算真实付费模型评测。完整解释见 [T13 测试记录](../2026-10-30-t13.md)。

## 最后修复与复审

- [A retry 红测](t13-cases-retry-red.log)：3 failed / 5 passed / 25 deselected；[绿测](t13-cases-retry-green.log)：33 passed。
- [B 输出/上下文红测](t13-runner-fix-red.txt)：7 failed；[绿测](t13-runner-fix-green.txt)：22 passed / 14.75s。
- [B 定向长案元数据](t13-runner-fix-long-evidence.json)：18 请求、8 摘要、8 恢复后请求、5 文件读取；其中绝对临时路径是当时证据路径，不保证后续仍存在。
- [最终 core 命令输出](resumate-t13-core-reviewed.txt)：指向最后 `20261029T182216Z-58f622f9` 运行。[完整选定证据](../2026-10-30-t13-core-reviewed/report.md)另存 manifest、calls、report 与 12 份 case JSON，未复制 SQL/checkpoint/state。
- [A 修复报告](../2026-10-30-t13-cases-retry-fix-report.md)、[B 修复报告](../2026-10-30-t13-runner-fix-report.md)、[最终限定复审](../2026-10-30-t13-eval-rereview-report.md)。报告中的 `/tmp` 路径为开发时原路径，同名日志在本目录归档。

## 历史集成与独立 SDK 验证

[完整后端日志](resumate-t13-backend-final.txt)记录 751 passed / 6 expected skipped / 103.58s，执行早于最后 A retry 与 B 修复。文件名沿用历史命名，不能据此声称最后补丁后重跑了全量测试。[第一轮报告](core-first-report.md)、[第一轮 JSON](core-first-report.json)、[第一轮 manifest](core-first-manifest.json)与 `resumate-t13-core-final.txt` 也保留为第一次集成证据。

[实际 Langfuse SDK 日志](resumate-t13-sdk-offline.txt)证明 5.0.4 SDK 在关闭 tracing 时接受生命周期调用；未验证云端接收。[依赖同步](resumate-t13-sync.txt)与 [telemetry 锁定](task-13-telemetry-lock.txt)保留依赖准备过程。

其他 fixtures/verifiers/runner/budget/telemetry 红绿日志记录早期开发和来源/工具状态修复。当前完成状态以最终测试记录为准，不把早期跳过数与完整集成跳过数相加，也不把 stub 语义 `not_applicable` 写成真实模型通过。
