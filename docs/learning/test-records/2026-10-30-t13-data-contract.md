# T13 eval dict contract v1

A owns `evals/fixtures.py`, `evals/verifiers.py`, `evals/cases/core.jsonl`.
B owns isolation, Run execution, SQL snapshots, faults, checkpoint coverage.

## Fixtures API
`load_cases(suite='core') -> list[dict]` reads JSONL and expands long synthetic data.
`seed_case(case) -> dict` lazily imports DB after B sets isolated env; creates schema + synthetic User/Resume/JD/facts/memory/match and AgentSession. Returns `user_id,session_id,resume_id,jd_id,baseline`.
`make_model(case,seed) -> EvalModel` BaseChatModel; exposes `summary_calls` integer, `main_calls` integer, `read_paths` list, `draft_results` list, `requests` list (only synthetic fixture). Set `model.callbacks` using B recorder and C telemetry. Model profile 64000 normally / 30000 long; max_tokens 1024. Long uses real SDK summary + read_file; no direct SQL model writes.

## Case dict
`id,category,resume:{raw_text,structured_data},job:{title,raw_text},facts:[{id,fact_key,kind,content,revision}],memories:[{id,kind,content}],match_report?:dict,question?:str,answer?:dict,cancel?:bool,fault?:'read'|'write',repeat?:bool,long?:bool,proposal:{section,after,reason,include_fact?:bool,include_answer?:bool},expected:{statuses:list[str],draft_count:int,requires_answer?:bool,requires_waiting?:bool,requires_fact?:bool}`.
All inputs synthetic. `answer` is directly ActionResponse.answers. Refusal allows succeeded with evidence-backed draft OR failed/no_draft; deterministic does not prove semantic refusal.

## output dict
`run_id,status,coverage:{waiting_observed:bool,waiting_draft_count:int,checkpoint_reopened:bool,summary_calls:int,file_reads:list[str],cancel_claim_blocked:bool,model_calls_after_cancel:int,fault_injected:bool,duplicate_result_refs:list[str],required_context_preserved:bool},error_code?`.
For long, `required_context_preserved` must be computed from actual model requests in stub or actual checkpoint/input context proof in live (not asserted by case); check baseline constraints, inputVersions, answered action ID and generated artifact ID across re-open. Missing required coverage => fail.

## db_snapshot dict
SQL serialized column names snake_case; enums -> .value; datetime -> ISO or null.
`run:{...AgentRun columns},session:{...AgentSession},resume:{...Resume},versions:[ResumeVersion],operations:[ToolOperation],events:[AgentRunEvent],actions:[AgentAction],facts:[ProfileFact],memories:[BusinessMemory],baseline:seed.baseline`.
`baseline={resume:{id,user_id,raw_text,structured_data},facts:[{id,user_id,fact_key,kind,content,source_document_id,revision,confirmed_at,deleted_at}],memories:[{id,user_id,kind,content,source_ref,confirmed_at,deleted_at}]}`. The same selected baseline columns must be compared after; do not include timestamps not under evaluation.
All rows include owners/run IDs, version refs. run.input_json.contextSnapshot is authoritative frozen base, not model text; applicant answer comes from SQL actions. B extracts snapshots with own fresh Session, never production serializers/verifiers.

## Verdict API
`verify(case,output,db_snapshot)->{passed:bool,checks:[{name,passed,reason,evidence_refs}],limitations:list[str]}` pure, no DB/models/project imports. `semantic_review(mode)->{rubric_version,items:[{id,title,status,evidence,reason}]}` stub statuses not_applicable; live unreviewed. No numeric aggregate.
