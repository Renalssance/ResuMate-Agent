# T09：固定输入与有来源的字段建议

日期 2026-10-30；起点 `948ae8a`。沿用总计划 T09 和已确认 scope，用户已授权连续开发。T08 的完整后端 442、前端 63、浏览器 11 项通过后进入本单元。

## 设计与范围

创建 tailoring Run 时在现有 input_json.contextSnapshot 保存当时简历/JD 原文与结构、已固定事实正文和最新现有匹配意见；input_versions 保持时间戳与事实版本。固定输入防止暂停后混入新资料；匹配意见是带时间的历史参考，不计算新分数。公开 Run 输入只返回 jdId/resumeId，不在列表复制全文。去重仍由 user/requestId 和业务 ID 判断。

共享 context 模块提供 capture_context(db,user_id,jd_id,resume_id,input_versions)、read_context(db,run)、changed_inputs(db,run)。snapshot 形状：resume={id,text,structured,inputVersion}，job={id,title,text,structured,inputVersion}，facts=[{id,revision,content}]，match 为可空历史参考。read_context 返回其副本并附 inputVersions、applicantAnswers=[{actionId,question,answers}]（只取本任务已提交 input 动作）。新 Run 可以用原快照重试；原简历/岗位已删除时不再新生成。旧 Run 无快照仅在原资料时间戳不变时补全；已变化明确 input_changed，历史产物仍可读。

业务服务 resume_versions 管理所有新草稿；Agent 工具只包执行权/事件。新工具 create_resume_draft(changes) 接受字段级建议列表，不再允许模型任意传整份简历覆盖输入。save_draft(run_id,epoch,changes) 委托该服务。既有历史草稿只读保持可展示，不为旧测试保留任意新写旁路。

change 输入包含 section、before、after、reason、fact_refs、requires_input；服务生成 id。首版可编辑字段为实际存在的 /self_summary、已有旧资料 /summary、/work_experience/N/description、/projects/N/description。before 必须等于快照字段，每个字段至多一条建议。非缺信息建议必须有来源；缺信息 requires_input=true 时 after 必须为 null。不实现任意 JSON Patch、增加不存在的经历、额外评分或自动确认。

来源类型：

- profile_fact：{kind:'profile_fact',factId,revision}，必须属于该 Run 固定确认版本且该 family 目前未删除。
- resume：{kind:'resume',resumeId,inputVersion,section,sourceRefs}，section 必须存在于固定简历，sourceRefs 与该字段所属条目的原始 source_refs 相同（无来源为 []），禁止岗位作为个人来源。
- applicant_answer：{kind:'applicant_answer',actionId}，只接受本 Run 已提交的 input 动作。回答不自动成为 ProfileFact。

产物 structured_content={resume,changes,inputVersions}；resume 保持固定原文结构作为审阅基底，changes 带服务生成 ID 与 pending 状态。T10 才逐条应用接受/编辑，不提前替换原简历。fact_refs 为建议来源去重并集。沿用一个 Run 一个初始草稿及现有 ToolOperation 唯一键，同一事务写产物、操作记录、事件，重放直接返回原产物。

GET /api/resume-versions/{id} 返回原有产物字段加 basedOnOldInput、changedInputs、sources（每项 {reference,label,content}），验证本人归属。Run artifacts 使用同一序列化。事实更新/原资料改变时提示旧依据；历史来源从固定输入读取，不用现值冒充旧内容。T09 前端只在材料卡展示建议、理由、来源、缺信息和旧输入提示；审阅按钮、保存和确认留 T10。

## 实施划分

1. 输入快照与 Run 合同：context.py、agent_runs.py 和相应定向测试。
2. 建议验证/业务版本/API/工具/技能：resume_versions、tools、API 路由；四类案例与数据测试。
3. 材料卡只读显示：已有 Vue 设计语言、字段名中文、来源文本、手机长内容；组件测试。
4. 父代理整合确定性模型 fixture、真实浏览器流程、实际截图查看、教学与测试记录。

## 验证目的与边界

快照/去重测试检测暂停后混入新资料、全文在列表重复返回或重试冲突；失败修正固定读取与公开序列化。两库版本测试检测伪造来源、错 before、删除事实、重复草稿；失败修合同/事务。四类案例覆盖无依据技术、JD 当经验、删除事实、重复工具调用，分别记录确定性证据与语义评测未运行状态。前端测试与实际截图检测来源缺失、长文溢出和旧资料提示；失败修数据映射与布局。完整联调检测真实 worker 对新工具合同无法生成草稿。

来源合法并不能证明语言语义真实。真实模型 smoke 和内容质量评测继续单独标为待验收，不用确定性 fixture 冒充。
