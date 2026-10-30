# T19 live 接线局部计划与测试记录片段

本轮授权只补实现和本地 MockTransport / 真 SDK / 真图 / SQL 验证；零供应商调用，不重置既有 3 元账本。原12案预算、隔离与默认verifier保持。

- C 独占 budget.py/records.py/run.py/task_runner.py/task_verifiers.py、新legacy HTTP adapter与tests。A独占interview_runner.py/interview_verifiers.py/interview_records.py与tests。
- 保持 BudgetCallback(config, ledger_path, calls_path, case_id=...) 及现有callback接口；C抽出reserve_call/settle_call小方法供raw SDK共享账本。
- make_live_model增keyword-only transport=None，仅用于本地HTTP契约验证；默认真实客户端redirect=False不变。
- A用真实消息的System required、get_interview_context/read_file响应记录模型实际输入，不回读DB假冒输入；on_llm_end先结算再阻塞已返回的真实InterviewStep响应，以真实命令验证取消迟到结果。
- C用真实AgentHarness，仅评测内替换实际create边界；逐次记录fallback/reflection请求与usage；403无usage保留预留；guard拒绝发送则零请求/零新增预留。
- Durable故障作用于固定业务阶段；provider次数与业务attempt分开；旧结果重放相等且零调用才通过，不强制新模型生成不同文字，不改回答凑绿。
- 先RED、后最小GREEN：HTTP实际请求体/max_tokens/enable_thinking、格式fallback、反思、403、限费、前置取消与返回后取消，随后真实服务+SQL八案。
- CLI两类都纳入同一live预算预检，预算停止保留incomplete后续not_run；语义仍待人工复核。默认stub30不变。
- ENOSPC已如实暂停，空间恢复后仅小源码与无Docker单测；B fresh镜像与Docker恢复后做新同一invocation四恢复；所有新接线冻结后最终全30仅跑一次。

记录边界：MockTransport usage为合成响应，只证明计费契约，不代表真实费用；不得用mock handler/run_schema替代HTTP路径；真实模型90%/零关键错误/三次重复仍未执行。
