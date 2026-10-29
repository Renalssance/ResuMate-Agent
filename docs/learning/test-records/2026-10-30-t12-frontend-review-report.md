# T12 前端独立审查

工作区：`/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`。审查依据为已定 T12 合同（含第 7 节）、`/tmp/t12-frontend-review-package.diff`、`/tmp/task-12-frontend-report.md`，并核对当前前端与相应后端协议。只读审查，未修改产品文件，未重复运行已通过测试。最终截图由父代理验收，本报告不代替截图结论。

## Spec compliance 结论：需要修复一处会话失效入口缺口

主要合同已正确实现：

- 保存需要明确勾选确认，POST 只发 `kind/content/confirmed:true`，类型和服务返回的 manual 来源一致；不会自动保存或把记忆当经历证据。
- 删除成功后移除正文，按 `cleanupStatus` 分开呈现 pending 和 complete；刷新 GET 能恢复待清理状态。文案明确保留已生成简历、投递版本与原面试记录，没有宣称清除全部历史。
- 记忆账户变化会同步清空私人输入、列表和提示；旧账户响应、卸载后的响应、删除前的旧列表响应不会覆盖现状态。
- 上下文容量单独显示，未知不从模型名猜测；空值显式保存为 null。API 层透传部分更新；服务按合并后 capacity/output 校验，未指定字段不被清空。422 保留编辑值。
- 被删除记忆终止的 waiting/running → cancelled 路径正确显示解释、隐藏重试，并调用不带 sessionId 的 createRun 创建干净会话。
- 缺容量与预算超限有明确解释和设置入口；PDF 通过 kind 分支保留原导出失败、重试与下载行为。

**[P2] 已经失败的旧任务未获得会话失效提示与干净任务入口**

位置：`frontend/src/views/AgentTaskView.vue:65`（相关展示在 28–32 行；后端依据 `backend/services/memory.py:96–99`，错误处理 `frontend/src/stores/agentRun.ts:121–126`）。

触发：一项使用过记忆的 tailoring 任务先因模型/工具错误进入 failed，之后用户删除该记忆。后端正确标记 Session 失效，但删除循环跳过所有 terminal Run，因此历史失败任务仍保留原 errorCode。当前 `sessionInvalidated` 只查看 Run 的 `session_context_invalidated` 错误码，页面继续显示“重试任务”，也不显示“重新准备材料”。点击重试后后端返回 `409 session_context_invalidated`，store 仅把 message 放入普通 error，快照与按钮仍不改变。该任务实际无法重试，用户却得不到合同指定的干净入口。

最小修复：让 UI 能依据真实 Session 失效状态识别这一类历史失败任务，或至少在收到该稳定 409 后把所选任务切换到失效说明和干净入口。保留历史失败原因/完成产物以及 PDF 行为，不必改变历史成功任务状态或引入通用恢复框架。应覆盖“先 failed，再删除记忆”这一不同于现有直接构造 errorCode 的用例。

## Quality 结论：总体实现克制，有一处列表加载与保存交错问题

新增样式限定在组件或视图内，沿用已有主题变量，没有改全局视觉；长文本使用换行与 minmax(0, 1fr)，窄屏改为单列。新增输入都有原生 label/可访问名称，确认复选框可以通过标签操作；容量说明通过 aria-describedby 关联，状态/错误有 status/alert。实现规模与合同相称，无不必要框架。

**[P2] 首次列表未完成时保存会遗漏已有记忆及 pending 状态**

位置：`frontend/src/components/BusinessMemory.vue:78–85`（按钮在 15 行，旧 GET 丢弃判断在 68 行）。

触发：用户已有记忆或待清理项，进入资料页后首个 GET 尚未返回，在可操作的表单中输入并保存。保存按钮及 save 入口均未检查 loading；第 81 行增加 listRequest，使正在进行的初始列表响应失效，并把 loading 置 false。POST 成功只把新条目拼入仍为空的 items，旧 GET 到达后被第 68 行忽略。因此界面错误显示只有新记忆的数量，并隐藏原有待清理状态，直到用户手动刷新。这是正常网络等待下可通过当前表单触发的状态交错，不依赖极短竞态。

最小修复：列表加载期间禁用保存，并在 save 入口执行相同守卫；或成功保存后重新加载权威列表。保留当前避免旧 GET 复活已删内容的设计，不需要新请求框架。现有“删除后旧 GET 晚到”测试不能覆盖该初始加载/保存路径。

## 验证范围

本次通过代码路径核对上述触发条件和结果，未重复运行已通过的组件/E2E。父代理提供的最新记录为定向组件 17 pass、网络错误增项后记忆组件 6 pass、真实 E2E 2 pass；这些已有记录支持已测路径，但不覆盖本报告两条触发条件。两条修复各需一次针对性验证即可，无需扩大成全局重新审计。
