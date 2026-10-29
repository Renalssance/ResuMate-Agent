# T14 局部规划：崩溃恢复与旧长任务迁入

日期：2026-10-30。实现与确定性验收完成，依赖 T13 实现与 core 验证。实际基线为 T13 本地提交26d1a35；以下合同基于实际路由、事务与前端调用阅读。四断点、24案、浏览器及逐张截图结论见[T14测试记录](../../learning/test-records/2026-10-30-t14.md)。

## 从真实路径确定范围

已有解析、匹配、出题通过 FastAPI BackgroundTasks 运行；TaskProgressHub 把归属、事件历史与订阅队列保存在 API 进程内。新 Run/Redis/worker 已经持久化，两类任务不能长期各自维护一套恢复机制。

代码阅读还发现 /api/followups/analyze 使用同一个内存后台分支。将它作为现有出题/回答分析链的一部分同步迁移，防止“删除旧后台分支”后这个已支持接口失效。这是据实补齐迁移入口，不增加新产品功能。

分为 T14a 持久入口/事件、T14b 业务事务恢复、T14c 四个实际崩溃点、T14d 24 案和浏览器验收。仍对应总计划同一个 T14，不改变后续 T15/T20/T16/T21 依赖。

## 持久入口与返回合同

按实际迁移引入 document_parse、match_analysis、question_generation、answer_followup 类型及各自 RunCreate 输入验证、输入版本、worker 派发。解析类型覆盖上传、重新解析和已保存岗位文本，不预建任意 handler 注册平台。

现有浏览器均发送 Prefer: respond-async，读取 {taskId} 后订阅 /api/tasks/{taskId}/events 并从最终事件取得原 documents/document/RunSummary/CandidateReport/FollowUpAnalysisResponse。保留这些成功结果结构；taskId 使用服务端持久任务标识，不再依赖内存登记。

/api/tasks 作为已有公开协议读取同一持久 Run 事件的进度投影；不建立第二套任务存储或内存广播。归属从 SQL 核实、分页游标和断线补读复用既有持久事件机制。新客户端拿到接受响应后必须采用返回 taskId，不能继续订阅旧本地猜测值。

没有 Prefer 的现有同步成功返回结构也需保留。提交同一持久任务后等待其结果、期间释放数据库会话；执行仍在 worker。等待必须有限，超时返回明确未完成状态与任务标识，不能在 API 内再次调用原模型处理器。固定等待上限45秒，低于现有部署的60秒HTTP上限；成功返回原结果，执行失败返回400，受理前校验/归属仍返回422/404。超时返回202 {taskId,status,code:"task_pending"}及任务地址。等待期间关闭请求会话，以短会话轮询；不增加配置框架。

## 每类任务的恢复单位

上传必须在 202 前保存文件与唯一文档身份。当前 _parse_saved_upload 在执行中创建行，直接重放会产生第二行；迁移后固定 documentId，使用已存在记录继续，外部存储使用已有持久引用。原 content_hash 确实跳过重复解析，保留现有用途，不新增摘要指纹。

匹配固定一个 AnalysisJob 与其 Candidates。当前 analyze_document_ids 每次调用 repository.create_run 会新建一组，不能原样重放。按实际已完成 MatchResult 继续剩余候选；同一候选业务结果与操作记录在同一事务内关联。模型可重复调用，业务结果不可重复。

出题读取固定已保存匹配报告，最终 QuestionSet 与 ToolOperation 原子保存。重新领取同一 Run 返回原结果，不重复覆盖；用户显式发起新请求仍可生成新题。回答分析同样保存该 Run 的唯一可恢复结果。

业务写入、操作成功记录、产物事件必须同事务；不能在一个已经自行 commit 的旧服务外层补写“完成”记录后声称原子。RAG 的已有 replace 操作按文档身份可重放；明确 SQL 为业务权威，重放索引不新增 SQL 业务产物。

取消/归属检查在实际模型前、工具/写入前进行。已取消任务不得被 scanner 重新领取；资料删除或失去归属后返回受控失败，不能继续使用先前加载对象完成写入。内存进度改为持久事件后，一次 terminal 事件与 Run 终态一致。

## 四个真实崩溃点

1. 模型尚未返回：杀 worker，确认锁释放后恢复；记录重复调用与 attempt/epoch。
2. 草稿事务已提交：杀 worker，恢复重放只返回已有版本/ToolOperation/event。
3. checkpoint 已保存、Run 最终状态尚未提交：杀 worker，恢复从完成图收敛到正确 Run 终态，不再次写产物。
4. 用户回答已提交、resume 尚未投递：中断 API 投递路径后由 SQL scanner 发现 queued；回答只保留一次，恢复读取同 actionId。

暂停栅栏与杀进程标记只放测试入口/monkeypatch，不放生产特性开关。API/worker 同处 Linux 时由 Linux 内读取活跃 SQLite，避免 T04 已验证过的跨宿主 WAL 误差。可复用现有镜像/Compose，但每项新断点有独立证据；旧 T04 同一场景通过不代替另外三点。

## 验证和记录

core 12 案保留不删除。新增 12 案包含四个实际恢复案例，以及解析、匹配、出题、回答分析、取消/归属和业务重放边界；实现时明确每案对应的运行器和证据。普通 stub 不运行 Docker 时，将真实恢复案例列为未执行/另有集成报告，不能只把 JSONL 数量加到 24 就宣称都已执行。

定向验证旧异步接受、进度和结果合同；双库验证身份/操作原子性；完整已受影响浏览器验证岗位解析、匹配、出题、文档上传与离开重开。页面运行后实际截图并打开检查，尤其长文件名、错误、取消、恢复后的进度与手机按钮换行，沿用米色/棕色视觉。

每个子单元先写能复现真实缺口的测试，再实现、定向回归；最后保留一次有范围的完整联调与独立审查。保存失败、修复、最终日志、实际限制与第十四课；不把重复模型调用说成 exactly-once。

## 已冻结的协作合同

T13 的实现与最终12案确定性评测已通过，真实模型预算仍待用户答复；不妨碍本单元确定性恢复工作。T13提交后开始代码迁移，记录实际基线。

- document_parse 接受 documentId（沿用 resume:整数 / jd:整数）与 parseMode（upload / reparse / saved_job）；match_analysis 接受 jdId 与 resumeIds；question_generation 接受 analysisJobId、candidateId、questionCount；answer_followup 接受类型化 followup。拒绝混入其他类型字段。
- 新增可空 AgentRun.result_json 保存本次成功响应。同步更新SQLite加列、MySQL建表及手工升级说明。新任务仍使用原Run身份/锁/扫描，不建另一套队列或任务注册表。
- 前端或旧调用方给定的 task_id 是每用户请求去重键；返回 taskId 始终是服务器Run UUID。上传在存文件之前按键查找已受理同类请求，避免重传造出第二份文档。首次受理将文件引用、固定文档身份与Run一起提交。
- 新增非终态 task.progress；终态由 run.status 投影，成功内容读取 result_json。取消投影为 failed / cancelled / 任务已取消，Run仍为cancelled。重试后的历史failed不能使新订阅提前结束；游标需越过未投影事件与超过100行的分页。
- 匹配的AnalysisJob和候选组在受理事务创建一次。每候选report、ToolOperation及artifact事件共同提交；重新领取跳过已完成候选。出题/回答分析最终结果与操作、事件及Run成功同事务。旧模型可重复调用，已提交的业务结果不能重复。
- 解析受理前失败清理新文件；受理后失败/取消保留原件和文档记录用于重试，显式删除才清除。Cloud原件保持持久引用，仅清临时缓存；保存岗位文本不要求原件或向量化。
- 模型调用前（含每次重试/降级）、索引前、最终写入前验证执行权与资料归属。事务内不持锁等待模型。候选图不序列化ORM对象，以已提交候选结果作为恢复单位。

核心协作接口为 create_run(db,user_id,RunCreate)，background_tasks.submit_task(db,user_id,request,prefer=...)，progress.TaskProgress(run_id,epoch,session_factory=...).publish(**event)，以及 append_progress(db,run_id,epoch,**event)。worker显式派发 run_document_parse / run_match_analysis / run_question_generation / run_answer_followup(run_id,epoch)。业务处理器自行管理短会话和受控失败；没有FastAPI后台执行分支和内存进度历史。补充公开 require_task_sources(db,run) 校验这四类任务资料归属，retry及处理器写入前显式使用；find_upload_run(db,user_id,request_id,document_type) 在保存新上传之前查同类已受理请求。finish_run(...,result_json=None) 在成功事务保存不可变结果；run_snapshot.result 返回该字段，四类任务 run_artifacts 返回空数组，前端用专门结果卡展示。question input_json 捕获 reportSnapshot、resumeId、jdId；match捕获analysisJobId。源码落定时若有必要调整签名，先同步协作者，再在此记录。

分工：A维护上述共享核心、模型/升级、事件流及worker派发；B维护文档服务、document_tasks及documents/jobs路由（包括回答分析路由的受理编辑）；C维护analysis_tasks、分析服务、repository、graph、Harness及runs路由；主代理完成前端/测试入口/四断点/eval/文档联调，空闲后可分派独立子单元。不同人不编辑同一共享文件。

新增12案固定为 recovery-model-before-return、recovery-draft-after-commit、recovery-checkpoint-before-terminal、recovery-answer-before-delivery、parse-upload-stable-identity、parse-reparse-saved-job、match-partial-candidate-replay、question-result-replay、followup-result-replay、cancel-recovery、source-deleted-or-reassigned、business-write-rollback。前四案必须实际杀进程；普通stub只报20执行/4未执行，直到对应本次输入与case ID的Compose证据合并，不能用旧T04结果补齐。
