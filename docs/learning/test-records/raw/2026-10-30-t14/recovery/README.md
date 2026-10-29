# T14 四断点证据归档

最终 invocation：f635af81-ed6d-4a40-92d9-7628d7be6d04。4 passed / 453.10秒。

来源 `/tmp/task-14-recovery-artifacts-f635af81-8w07lg1j`。原始JSON保留实验时的绝对路径，不伪造执行位置。各case同名目录保存 before-kill、after-recovery、compose配置与日志；commands.log和compose.log转为.txt以便入库。source-snapshot.tar.gz是当次挂载到Linux API/worker/scanner的固定backend源码；未归档整库、checkpoint或临时产物。

首轮已执行通过但日志目录被pytest保留策略清理，不能恢复原始文件。因此改独立临时根并完整重跑，最终评测只引用本目录这一invocation。原因与命令见report.md；不混合两次证据。
