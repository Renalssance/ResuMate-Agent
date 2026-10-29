# 第九课：固定输入与有来源的简历建议

本课衔接[第八课](08-jobs-and-confirmed-facts.md)。测试与页面证据见 [T09 记录](test-records/2026-10-30-t09.md)。开发合同见[T09 局部计划](../superpowers/plans/2026-10-30-t09-evidence-based-tailoring.md)。

## 从一个真实问题开始

任务读取简历后可能补问并暂停。你在另一个页面更新了简历，几个小时后才回答。如果工具每次查询当前资料，一份草稿就可能同时使用更新前的经历与更新后的简介；仅记录 updated_at 只能发现变化，不能还原旧内容。

本单元在创建 Run 的 SQL 事务中保存 contextSnapshot：简历与岗位的原文和结构、当时确认的事实版本正文、最新已有匹配意见。输入版本继续提供时间与事实身份，快照保存实际内容。两者用途不同，不必引入 hash、复制整套资料表或另写版本框架。

## 固定与动态各保存什么

固定的是开始时的资料。补问答案属于这个任务后来收到的输入，保存在既有 AgentAction，读取上下文时附上本任务已提交的回答与 actionId。回答可以成为当前建议的来源，但不会因此自动成为跨任务的已确认事实。

新 Run 使用新的资料；旧 Run 继续使用自己的快照。资料变化会在产物上显示“依据旧资料生成”，让你决定是否新建任务。原始资源已经删除时，后续生成停止；已经生成的历史产物仍能根据保存的来源显示当时依据。

旧 Run 没有存快照，不能假装拥有历史。只有简历和岗位时间未改变时才可补全原内容；已改变就要求新任务。过去未固定的匹配报告留空，不拿后来产生的报告冒充旧建议。

## 为什么让模型提交 changes，而不是整份简历

T05 的最小草稿工具可以保存任意结构化内容，适合验证任务链路，却无法约束哪些字段发生了变化。T09 改为明确的业务请求：

```json
{
  "section": "/work_experience/0/description",
  "before": "负责 API 和数据库设计。",
  "after": "负责业务 API 设计与数据库结构维护。",
  "reason": "突出与目标岗位相关的已有职责。",
  "fact_refs": [{"kind": "profile_fact", "factId": "固定事实版本的 ID", "revision": 1}],
  "requires_input": false
}
```

服务检查字段确实存在、before 与固定原文相同、同一个字段没有重复建议、来源来自本任务。建议 ID 由服务生成。首版只编辑已有简介、工作经历描述和项目描述；其他结构继续保留，模型不能借修改描述顺手增加不存在的公司、学历或经历。

缺少规模、指标或职责时，after=null、requires_input=true，说明缺什么并补问。未知的数据不会先成为“可接受”的建议。没有必要修改时可以保存空建议列表，保留原简历供审阅。

## 三类来源与各自含义

| 来源 | 固定内容 | 验证方式 |
| --- | --- | --- |
| 原简历 | 字段正文、输入版本、原 SourceRef | ID、版本、字段与原文位置均属于本任务快照 |
| 已确认事实 | factId 对应的不可变 revision 与正文 | 版本在本任务固定集合中，且该事实族当前未删除 |
| 本次补充回答 | 本任务 input 动作的答案 | actionId 属于本 Run，已提交，决策为 submit |

岗位要求不能作为个人经历来源。事实编辑后，旧 Run 仍可使用当时确认的旧版；事实明确删除后，旧 Run 也不能再新写引用它的草稿。已保存的产物保留历史引用，便于理解当时为什么作出建议。

这些校验只能证明来源身份与版本正确。模型仍可能给真实来源附上一句来源不支持的话，例如把普通 API 开发改写成千万级系统负责人。真实模型评测、逐条审阅与人工抽查负责暴露这类语义问题；不把“引用存在”宣传成“已经证明所有内容真实”。

## 数据库事务怎样守住一份产物

业务服务把 ResumeVersion、ToolOperation 和 artifact.created 事件放在同一个事务。工具层只负责注入 Run 身份、检查执行权并提交。重复执行先找持久化操作键 draft:{jdId}:initial，返回已经保存的版本 ID，不创建第二份草稿。

结构化产物包含 resume、changes、inputVersions。此时 resume 仍是原始快照；changes 只是待审阅建议。T10 才根据你接受、拒绝或编辑的选择应用字段，不能在展示建议时偷偷改掉原简历。

## 把后端契约带到页面

材料卡显示原文与建议、修改理由和来源正文；手机改成单列，长正文与来源身份可以换行。事实来源显示版本，补充回答明确标为本次回答，避免把所有来源统称“已确认事实”。历史 T09 之前的材料继续按原内容只读显示。

完整浏览器测试会先创建真实任务，在任务等待时更新主简历，再回答并等待独立 worker 生成草稿。断言固定原文没有被新简介替换，同时实际打开桌面和手机截图，查看旧资料提示、长对照文本与缺信息状态是否可读。

## 阅读源码与动手练习

- 输入快照：[context.py](../../backend/agent_runtime/context.py)、[agent_runs.py](../../backend/services/agent_runs.py)。看公开列表为什么只返回业务 ID，而不复制完整快照。
- 建议规则：[resume_versions.py](../../backend/services/resume_versions.py)、[请求 schema](../../backend/schemas/resume_versions.py)。找出数据库校验和语言语义判断的边界。
- 工具与提示：[tools.py](../../backend/agent_runtime/tools.py)、[定制技能](../../backend/agent_runtime/skills/resume-tailoring/SKILL.md)。补问后再次读取上下文，获得可引用的回答 ID。
- 页面：[ArtifactCard.vue](../../frontend/src/components/agent/ArtifactCard.vue)、[FactReference.vue](../../frontend/src/components/resume/FactReference.vue)。前端只呈现服务返回的建议，不负责证明来源合法。
- 四个评测案例：[tailoring.jsonl](../../evals/cases/tailoring.jsonl)。区分确定性拒绝错误来源与尚未执行的模型语义评测。

练习：在独立测试里分别换掉 before、factId 和 resume inputVersion，观察错误与未写入的数据库。再把引用合法但语义夸大的句子交给人工审阅，理解为什么需要两层验证。最后修改主简历，比较同一个旧任务与新任务的输入来源。
