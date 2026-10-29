# T13 combined eval spec and quality review

Workspace: `/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`.
Reviewed against `/tmp/resumate-t13-brief.md` and `/tmp/t13-data-contract.md`, base `4f4f201`.
Scope: eval fixtures, cases, verifier, runner, budget, records, README and associated eval tests. Production telemetry diff was intentionally not reviewed.

## Open findings

### P2 — Preserve public tool-call output, including rejected proposals

Location: `evals/records.py:122-125` (absolute `/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent/evals/records.py:125`).

`on_llm_end` converts each main-model message to `public_text(message)` before saving it. A normal tool-only model response therefore becomes an empty string. Tool names, argument objects and invalid tool-call arguments are lost. A successfully persisted draft is recoverable from SQL, but a rejected `create_resume_draft` proposal is not: SQL has no artifact and the live raw checkpoint is intentionally removed. This violates the agreed preservation of original public model output and makes the important bad-before/bad-source live failures impossible to inspect from the retained report.

Focused probe: a real `AIMessage(content='', tool_calls=[...create_resume_draft...])` passed through `CallRecorder` produced `outputs == ['']`; the saved JSONL did not even contain `create_resume_draft`. This was a local callback-only probe, with no network request.

Fix: save a small explicit public message representation containing public text plus tool-call names/IDs/arguments (and the explicit invalid-tool-call representation where applicable), still excluding reasoning, arbitrary `additional_kwargs`, provider error bodies and auth metadata. Keep this local to synthetic eval records. Add a focused tool-only/rejected-proposal recording test; retain the existing reasoning exclusion test.

### P2 — Accept the supported successful retry path in deterministic verification

Location: `evals/verifiers.py:58-59` (absolute `/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent/evals/verifiers.py:58`).

Every case currently requires `run['attempt'] == 1`. The production runner retries transient provider failures, and `finish_run` increments the same Run's attempt up to three. The eval runner explicitly executes those queued retries and its budget correctly counts them. If a normal live case encounters one transient failure and then succeeds with exactly one valid draft, the verifier still reports failure solely because attempt is two. That contradicts preserving the existing Run retry state machine and recording retries rather than imposing a new single-attempt success rule.

Focused probe: the existing valid SQL snapshot with only `run.attempt = 2` was rejected solely by `run_attempt`. The supported production trigger is visible in `backend/agent_runtime/runner.py:81-85` and `backend/services/agent_runs.py:347-349`.

Fix: verify the supported attempt/epoch bounds or explicitly express a per-case attempt expectation where one is genuinely required. Do not globally require one attempt. Add a successful-retry verdict case; no need to repeat the whole harness suite for this two-line predicate change.

### P2 — Compare required context content across resumed calls, not counts and any-time presence

Location: `evals/run.py:197-205` (absolute `/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent/evals/run.py:197`).

The long-case `required_context_preserved` check treats any four constraint strings as preservation and accepts answer/artifact IDs if they appeared in any captured context at any point. It can report preservation when a constraint is replaced, or when the answer appears in one resumed call and then disappears after a later real summary. The long fixture actually exercises multiple summaries after the answer, so this is the exact lifecycle the contract asks to check, not a hypothetical input format. The current evidence proves that these values appeared somewhere, not that the baseline constraints and already available references survived the resumed execution.

Fix: compare the baseline constraint values, and associate captured contexts with the actual call/epoch so each subsequent main or summary request is checked against the answer/artifact references already available at that point. A small negative test that removes an answered action from a later post-resume context, plus one that changes a constraint without changing the count, should fail. There is no need for hashes, a second summarizer, or saving provider-private prompts.

## Finding fixed during review

The original P2 at `evals/verifiers.py:_field` used an inherited parent `source_refs` when a valid source section resolved to a whole `/work_experience/0` or `/projects/0` object. This could reject correct entry marks and accept incorrect root marks.

A's scoped fix at current lines 16-17 now takes the resolved object's marks. I inspected `/tmp/t13-cases-scoped-fix.diff` and `/tmp/task-13-cases-fix-report.md`; the two-line change and four positive/negative entry-reference tests address the finding without broadening allowed change targets. Scoped re-review is clean. A reports four red cases before and 25 verifier tests passing after; I did not duplicate those tests.

## Correct parts

- The 12 fixed cases and required category counts are present. The frontend, measured-fact, negative clarification, refusal and source-conflict inputs are specific to their scenario. Stub suggestions do not silently reuse unrelated API/database claims.
- The pure verifier independently checks persisted draft/operation/artifact counts and linkage, exact before values, frozen versions, source ownership, actual answered actions, pending review state, unchanged original resume/facts/memories, cancellation and rollback residue. Its existing negative cases reject the required duplicate versions, wrong references, wrong before values and missing answers.
- Isolation is established before project imports in the CLI parent and in fresh children. Only the explicit model environment whitelist enters live children. Stub children receive no provider credentials, and automatic dotenv loading is disabled.
- Live requests use the same synthetic inputs and production services/checkpointer. Read/write fault injection and duplicate replay stay in the harness. Cancel executes real waiting then cancellation and a blocked claim.
- The budget callback is synchronous and fail-closed at the actual model boundary, shares persisted reservations across cases, counts summary calls/retries, and retains reservation for missing usage, timeouts and lost responses. Recorded over-capacity usage stops later calls and marks the final selected case incomplete. The monetary input reserve is distinct from the smaller working context window.
- Reasoning fields, summary text, arbitrary provider errors, key/base URL and auth metadata are excluded from the explicit call/report records. Live checkpoint cleanup is restricted to the generated case checkpoint files. Raw SQL holds synthetic data; no real private resume is imported.
- Completed model failures remain in per-case reports; budget/config/harness stops retain unfinished/not-run case entries in the aggregate report. Exit 0 is correctly described as deterministic success only. Stub semantics remain not_applicable, live semantics unreviewed, with no weighted total.
- The saved long smoke evidence shows actual SDK summary and file-read activity, real waiting and checkpoint reopen. It is correctly described as stub evidence. No external paid live or Langfuse result is claimed.

## Review evidence and limits

Read A's `/tmp/task-13-cases-report.md`, B's `/tmp/task-13-runner-report.md`, the implementation/tests, and the saved long smoke case. B reports 14 scoped runner/budget tests passing; I inspected those tests rather than rerunning them. I performed only three small local probes with specific decision outcomes: whole-entry source handling, successful retry verdict, and retention of tool-only output. No credentials, external models, whole-suite runs, or production edits were used.

Root owns the final full 12-case stub execution and locked-environment regression. This review does not claim those final checks have completed. Resolve the three open findings before treating the eval implementation as fully conforming or starting the explicitly budgeted live smoke.
