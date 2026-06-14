# 交给 Codex 的实施任务

请基于本目录完成 ResuMate Agent 的 LLM Prompt 与结构化输出可靠性改造，不改变“Python 计算 total_score 和 recommendation”的业务边界。

## 目标

1. 用 `backend_prompts/` 中的五份 Prompt 替换当前业务 Prompt，并将占位符映射到当前 `AgentHarness` 实际变量。
2. 保留 system 层完整 JSON Schema 注入和 `strict=true`。
3. 将匹配评估和面试题 evidence 改为 `evidence_chunk_ids`，由 Python 从本次允许集合回填原始 evidence。
4. 增加输入/输出集合一致性、评分状态一致性、source-ref 原文一致性和问题分布校验。
5. 将问题生成重构为 blueprint + 两批正式题 + 歧义追问，并支持局部 repair。
6. 增加 OCR/text quality gate、多职位 JD 检测和结构化 validation error 日志。
7. 增加固定自动评测集与 CI 回归指标。

## 必须遵守

- 不允许 LLM 计算 `total_score` 或 recommendation。
- 不允许 LLM 创建、修正、拼接或改写 evidence。
- 不允许匹配评估使用对应 criterion 候选 evidence 集合之外的 chunk。
- `score=0` 时 evidence 必须为空；正分必须有 evidence。
- 输出 criterion 必须与输入一一对应、顺序一致。
- 多职位 JD 不得合并为一个人工组合岗位。
- OCR 低质量文本应在 LLM 前拒绝或重新 OCR。
- 不要通过放松 Pydantic 校验来提高“成功率”。

## 建议修改位置

- `backend/prompts/*.md`
- `backend/schemas/workflow.py`
- `backend/agents/harness.py`
- `backend/graph/candidate_workflow.py`
- `backend/services/analysis.py`
- `backend/services/documents.py`
- `backend/rag/milvus.py`
- question quality/repair 相关模块
- 测试目录和日志配置

## 测试要求

- Prompt 单元测试：模板变量完整、无未替换占位符。
- Schema 测试：score/status/evidence 组合、criteria 数量、question 类型分布。
- Evidence 安全测试：未知 ID、跨 criterion ID、被篡改原文、score=0 带 evidence 均失败。
- Resume 引用测试：未知 chunk、非原文子串、section/page 不一致均失败。
- 多职位 JD 测试：检测后不进入单 profile 合并解析。
- OCR gate 测试：乱码样本被阻断。
- Question split 测试：两批合并后正好 10 道且无重复 question ID。
- 回归测试：Python 总分计算结果不受 LLM 输出字段影响。

完成后输出：

1. 修改文件清单；
2. Schema 迁移说明；
3. Prompt 变量映射；
4. 测试结果；
5. 旧数据兼容策略；
6. 尚未解决的 RAG/OCR 风险。
