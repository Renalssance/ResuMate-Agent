# T12 前端两项 P2 定向复核

工作区：`/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`。仅审查 `/tmp/t12-frontend-review-fix.diff`、更新后的前端/后端报告，以及这些改动直接依赖的当前快照和 store 路径。没有修改产品代码，没有重复运行测试或扩展全局审查。

## P2：历史已失败任务的会话失效入口缺失 — ADDRESSED

- `backend/services/agent_runs.py:221–235` 在已有快照的同一 SELECT 中读取 Session 失效时间，返回 `sessionInvalidated`。这是会话事实，未覆盖 Run 的原 status/errorCode，也未新增或改写历史事件。`resume_export` 明确返回 false。
- `frontend/src/services/agentStream.ts:8` 将该字段纳入 RunSnapshot，读取和传递快照不会丢弃它。
- `frontend/src/views/AgentTaskView.vue:65–66` 识别会话失效字段并保留现有失效错误码路径；失效提示优先于原容量错误，避免引导用户反复修复容量后重试已失效会话。
- `AgentTaskView.vue:28–32` 对失效的 failed/cancelled 隐藏重试并提供“重新准备材料”；该按钮继续通过既有不含 sessionId 的 createRun 创建干净会话。
- `frontend/src/stores/agentRun.ts:125–130` 在已打开的旧页面重试收到 `409 session_context_invalidated` 时刷新权威快照。快照接受相同 lastSeq，因此无需为历史 Run 伪造新事件也能应用 sessionInvalidated=true；账户/路由代次保护仍然有效。
- `AgentTaskView.vue:29` 只对 failed 或失效 cancelled 显示恢复面板，已成功历史任务继续展示产物与版本入口；PDF 的原失败提示、重试和下载路径保持不变。

新增测试包含原 errorCode + sessionInvalidated=true 的 failed/cancelled、原失败页在另一页删除后收到 409、成功历史产物继续可见；它们分别对应原缺口和修复的直接回归边界。

## P2：首次列表未完成时保存遗漏已有记忆及 pending — ADDRESSED

- `frontend/src/components/BusinessMemory.vue:15` 在 loading 时禁用保存按钮。
- 同文件 `:78` 在 save 入口执行同样的 loading 守卫，程序化表单提交也不能绕过。
- 输入仍可提前填写；初始 GET 完成并填充已有 items/pendingDeletions 后才允许 POST，成功保存会在已有列表前加入新条目，保留已加载的 pending。原账户切换隔离和删除前旧 GET 防复活机制没有变化。
- 新增 deferred 初始 GET 用例同时提供已有记忆和 pending 项，并验证加载期间不 POST、加载后保存保留两者，直接覆盖原触发条件。

## 新增重要回归：未发现

本轮改动范围适当，没有为了这两项问题增加状态框架或修改无关 UI。Spec compliance 与 quality 的两项原阻塞均已解决。

验证证据由实现代理提供：26 项定向组件通过，最终类型检查与 build 通过；后端快照修改的两库定向用例和 PDF 回归通过。本复核未重跑这些检查。父代理正在执行的第三个真实 E2E（历史 failed 页、另一页删除、409 刷新、重载、新按钮建立干净 Session）结果应由父代理补入最终验收，不能将本次代码复核描述为该 E2E 已通过。
