# 统一求职聊天 Agent

用户已确认扩展现有 Deep Agents，参考 LibreChat，不引入 LibreChat 服务或替换 Vue。

默认工作台入口为 `/chat`。左侧会话列表，中央流式对话，消息中展示业务工具和任务卡片。保留现有文档、匹配、材料准备、简历审阅、面试、投递页面作为详情入口。沿用奶油色、可可棕视觉。

聊天每一轮成为 `AgentRun(kind=chat)`，使用现有 AgentSession 的活动任务互斥、队列、事件、取消和恢复；Deep Agents 使用会话 checkpoint 继续上下文。历史由 SQL Run 输入、事件和最终结果提供，不使用浏览器存储作为事实来源。不会为聊天新建数据库表。

工具读取当前用户资料，提交已有 document_parse / match_analysis / tailoring / question_generation / resume_export 任务，查询结果，收藏岗位，管理投递，开启和继续文字面试。长任务排队后聊天轮结束以释放单 worker，界面跟踪任务并提供继续分析入口，模型不得把排队当成完成。简历确认沿用现有人工审阅。

接口：`GET/POST /api/chat/sessions`；`GET /api/chat/sessions/{id}`；`POST /api/chat/sessions/{id}/messages` 接收 message、requestId、可选 resumeId/jdId，返回 RunAccepted。会话返回 sessionId,title,createdAt,updatedAt,activeRunId。详情另含 turns，每轮为 runId,message,status,text,lastSeq,tools,outputRefs,result,errorCode。tools 为 name,operationKey,status,resultRef，resultRef 使用 `run:UUID` / `interview:UUID` / `application:ID` / `jd:ID`。流式、取消、重试使用现有 agent run API。

验证覆盖真实 Deep Agents 图与确定性模型、业务工具的真实数据库效果和归属校验、会话恢复与忙状态、前端发送和恢复、完整类型检查与构建。真实供应商模型质量单独报告。
