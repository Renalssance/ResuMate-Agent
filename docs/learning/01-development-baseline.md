# 第一课：先证明开发环境与恢复机制能工作

## 这一单元解决什么问题

后续 Agent 要能等待用户补充资料，并在稍后继续。直接写任务页面而不验证底层依赖，会把 SDK 不兼容、数据丢失和 UI 问题混在一起。T01 先用一个最小、可重复实验验证技术前提，并建立前后端测试入口。

总体系统分为四层：Vue 接收用户操作；FastAPI 校验和保存业务数据；worker 执行耗时任务；Deep Agents 决定调用什么工具。现有解析、匹配和投递服务继续复用。业务数据库、队列和图 checkpoint 的职责不同：队列通知执行，业务数据库保存被接受的工作与产物，checkpoint 保存图执行状态。

当前仅新增依赖与测试设施，业务流程尚未接入新的运行时。

## 从源码看一次暂停与恢复

代码：[test_deepagents_contract.py](../../backend/tests/test_deepagents_contract.py)。

```text
用户要求准备申请材料
  → 可控模型返回 collect_project_role 工具调用
  → 工具用 interrupt 发出 project_role 补问
  → 图状态写入 SQLite，invoke 返回中断信息
  → 关闭数据库连接和当前图
  → 打开同一 SQLite 文件，重新构造图
  → 使用原 thread_id + Command(resume=回答)
  → 工具取得回答，模型读取工具结果并返回
```

`ApplicationModel` 只替代远程模型这一个不可控部分。它先发出真实 Tool Calling 消息，再读取真实工具结果；Deep Agents、工具执行和 SQLite saver 都没有被 mock。因此测试可以验证库之间的接口和数据流，又不会消耗模型额度或泄露真实简历。

测试同时检查：暂停前没有工具完成结果、重新打开 checkpoint 后仍有待执行节点、恢复后得到 `backend`、图没有剩余节点、另一个 thread_id 没有读到原任务状态。若只是使用内存 saver，同一进程中跑通不能证明关闭连接后仍能恢复。

注意：这仍不等于 kill/restart worker 故障恢复，也不证明真实模型能正确发现信息缺口。前者属于任务运行层测试，后者属于模型 smoke 和评测。

## interrupt 不是把 Python 调用栈冻住

恢复时中断所在节点可能重新执行。不要在 interrupt 前直接写一份新的简历版本，否则恢复可能重复写入。后续 T02/T05 用稳定业务操作键和数据库唯一约束解决产物重复；不能靠随机的 tool_call_id 去重。

补充输入和人工审批也是两件事：本例使用工具内 interrupt 获取事实；`interrupt_on` 则可用于执行工具前审阅。官方说明见 [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) 和 [Deep Agents customization](https://docs.langchain.com/oss/python/deepagents/customization)。

## 三类测试怎样分工

| 测试 | 本次实例 | 能发现什么 | 不能证明什么 |
| --- | --- | --- | --- |
| Python 契约测试 | 真实图 + SQLite + 可控模型 | SDK 组合无法调用工具或从磁盘恢复 | 真实模型质量、worker 故障恢复 |
| Vue 组件测试 | 挂载 TaskProgress 后更新 props | 失败状态不刷新、错误原因缺失、无任务显示旧内容 | 真实网络或浏览器布局 |
| 浏览器测试 | 注册密码不一致时阻止请求并保留用户名 | 路由、表单绑定、事件处理、错误展示断开 | 注册 API、数据库、完整求职流程 |

组件测试实际挂载 `.vue` 文件，而不是搜索源码中有没有某个字符串。浏览器测试使用可访问标签寻找输入框；如果 label 与 input 关联断裂，测试也会暴露问题。

## 可复现安装与依赖变更

`pyproject.toml` 声明依赖范围，`uv.lock` 保存完整解析结果；`package.json` 与 npm 锁文件同理。增加 Deep Agents 引起部分 LangChain/LangGraph 依赖联动，因此要跑原有后端回归，而不能只跑新测试。

Python 本次实测 3.12.14，Node 24.10.0。源码声明的 Python 下限仍为 3.11，本次没有验证 3.11。测试工具放在开发依赖，避免把“测试时需要”与“业务运行时需要”混淆。

## 动手练习

1. 给契约测试换一个新的 thread_id 再恢复，观察为什么原补问无法接续；练习后还原代码。
2. 把 SQLite saver 换成两个独立的内存 saver，解释为什么不能用这次实验宣称持久化恢复。
3. 临时去掉 TaskProgress 的错误展示，运行组件测试，查看失败是否指出用户可见后果。
4. 区分“220 个后端测试通过”和“真实模型能生成正确简历”：列出后者还需要哪些输入案例与验证器。

自测：为什么 checkpoint 不代替任务表？为什么恢复不保证模型调用只计费一次？为什么本单元不需要真实 API Key？答案分别是执行状态与业务状态分工、崩溃窗口可能重放模型请求、可控模型足以验证确定性接口契约。
