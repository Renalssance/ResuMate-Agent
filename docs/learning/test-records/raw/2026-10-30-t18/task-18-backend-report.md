# T18 文档边界与机械工具权限结果

基线 cdde2c5；共享工作树 /Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent。2026-10-30。生产与相邻测试已冻结；未提交，未运行全套/浏览器，未调用付费模型。

## 实现

- backend/services/documents.py:289：打开 PDF 后、逐页 get_text/图片/OCR 前检查总页数，100 页允许、101 页拒绝。沿用已配置默认 100 页常量及 finally close。原 10 MiB 分块上传和错误清理已正确，本轮未重写。
- backend/worker_tasks.py:110 与新 backend/services/document_process.py:14：document_parse 专用子进程执行原 run_document_parse，生产墙钟 120 秒包含进程启动、提取/OCR、模型和 embedding。父 worker 继续持唯一 execution_lock 与 heartbeat。截止先 kill、wait/reap，再调用现有 finish_run 按 epoch 写 failed/document_parse_timeout；不排队自动重试、不改变其余 Run 类型。
- document_process.py:44：父进程独占 stdin pipe 的写端；子进程先启动 EOF 监视再加载业务模块。父 SIGKILL 后管道关闭，子立即 os._exit，不能在旧 epoch 下继续写。原 SQL guard/finalization fence 保留。
- document_process.py:54：子进程拥有现有 sync Redis 资源，正常/异常退出 close；保留 Harness 用量 SQL commit 后 DEL 仪表盘缓存的行为。
- tests/e2e_document_process.py：仅测试入口恢复既有合成 provider；root 已负责 e2e_worker_fixture.py 子命令注入。生产无测试环境开关。

## TDD 与最终证据

1. /tmp/task-18-document-red.txt：2 failed、1 passed、7 deselected，6.43 秒。真实 101 页文字 PDF 未拒绝；旧 execute_run 进程在模型边界阻塞，超过测试 5 秒仍未退出。不是把 mock TimeoutError 当成截止证明。
2. /tmp/task-18-document-green.txt：初始 10 passed，34.93 秒。
3. /tmp/task-18-document-resources-red.txt：2 failed、10 deselected，0.58 秒。真实 child main 未初始化 Redis，get_sync_redis 拒绝；此回归由迁移进程引入并已修复。
4. /tmp/task-18-document-green-final.txt：最终 test_upload_limits.py 完整 12 passed，35.41 秒。100/101 PDF 两案；SQLite/MySQL 各提取/模型/embedding 超时与父 SIGKILL 四案；正常/异常 child Redis 关闭两案。共 12，不把前轮重跑累加成更多测试。
5. /tmp/task-18-agent-security-green.txt：6 个机械权限案加 1 个既有 OCR 上限断言，7 passed，2.41 秒。旧 OCR 断言消息从只针对 OCR 改成全 PDF 总页数合同。
6. /tmp/task-18-agent-security-fixture-failure.txt：首次 6 failed 均为测试 seed 外键顺序，补 Resume flush 后通过。不是产品漏洞 RED。

每个进程截止案使用真实 execute_run 派发、现有文件执行锁及真实 SQL；仅耗时/模型/索引边界为测试合成。先观察真正子进程进入指定阶段，再真实截止终止；检查没有结果、ToolOperation 或 artifact.created，attempt 仍为 1，文档标记 failed；释放原阻塞不会恢复旧执行。同锁下后续正常 Run 成功。父 SIGKILL 案观察真实 child PID 已退出，再把 stale Run 经原恢复流程变为 queued。

这些是双数据库上的实际 OS 进程与 worker dispatcher 测试，不声称新增 Docker/Celery broker 故障实验；最终真实栈/旧恢复集成由 root 统一。生产固定 120 秒，测试专用入口将截止缩为 2 秒以检验同一机制。没有实等 120 秒。5 条警告是既有 PyMuPDF SWIG deprecation。

## 已正确的机械权限边界

backend/tests/test_agent_security.py 使用真实 DeepAgents 图、StateBackend、业务工具、检查点与 SQL，仅替换外部模型响应。恶意 JD 明确请求删除资料、他人 fact 与宿主密钥；模型实际尝试三种调用。

- 删除、确认、execute、task 未暴露；未知 delete_document 调用没有业务效果。
- foreign profile_fact 由真实 create_resume_draft 校验拒绝，tool.failed 可见，无 ResumeVersion/ToolOperation。
- SDK read_file 只能访问 StateBackend 虚拟文件；实际宿主临时文件与账号 API Key 不出现在模型请求或持久事件。
- 本人 Resume、他人 Resume/ProfileFact 保持不变。

已有生产权限实现正确，新增六案是机械边界回归，不能宣称真实模型提示注入拒绝率或安全率。归属/人工确认/10 MiB 等已有测试复用，不重复计为新修复。

## 真实生产浏览器发现的退出回归（后续修复）

A 的 /tmp/task-17-production-browser-yxK240 实际 worker 日志发现 `_enter_buffered_busy`：daemon 父管道监视线程使用 sys.stdin.buffer.read，在正常解释器关闭时持有 BufferedReader 锁。本轮初始 12 项未检查 child 的正常退出码，只看业务结果和父 worker 完成，因此没有覆盖这一真实问题；已成功 SQL 结果不会被 finish_run 的异常收尾覆盖，这个既有 fence 正确。

新增真实子进程、保持父 stdin 写端打开、直接检查返回码/无 Fatal 的双库回归：/tmp/task-18-document-exit-red.txt 为 2 failed；watcher 改成 os.read(sys.stdin.fileno(), 1) 后 /tmp/task-18-document-exit-green.txt 为 4 passed / 4.26 秒（新正常退出 2 + 原父 SIGKILL 2）。只替换原始 FD 读取，不增加新生命周期框架。test_upload_limits.py 现共有 14 案，最新定向与先前完整 12 案分开记录；没有声称再次完整跑过 14 案。

同次浏览器上传 failed 的第二根因由 root/A 修复：e2e_legacy_fixture 的 OpenAI 包装重复传入 http_client。该问题属于测试夹具接线，由 A 留其 RED/GREEN；不是本生产退出修复的因果成果。A 受影响首案补测 /tmp/task-17-production-browser-recheck-z2XIaz 已 GREEN，上传/PDF真实通过（10.3 秒，含启动总 17.7 秒）；原离线案已绿未重复。
