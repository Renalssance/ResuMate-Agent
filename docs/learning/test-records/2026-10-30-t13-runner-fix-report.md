# T13 B scoped review fixes

Scope: two P2 findings from `/tmp/task-13-eval-review-report.md`, plus root's explicit requirement to preserve exact initial facts/preferences in the long case. No production runtime, verifier, budget policy, dependencies or unrelated files changed.

Exact scoped diff: `/tmp/t13-runner-scoped-fix.diff`, comparing a pre-fix copy with the resulting four files:

- `evals/records.py`
- `evals/run.py`
- `evals/README.md`
- `backend/tests/test_eval_runner.py`

## Public output retention

`public_output` in calls.jsonl and case output now stores explicit `{text, tool_calls, invalid_tool_calls}`. Each call keeps its ID/name/arguments; tool-only messages are no longer reduced to empty strings. Invalid tool arguments remain available, while arbitrary parser diagnostic/error metadata, reasoning and additional_kwargs are excluded. The real transactional rollback test now proves the proposed changes remain in case output even when SQL has zero draft/operation/artifact rows. A focused callback test proves wrong-before and malformed-JSON proposals are retained exactly and excluded metadata is absent.

## Per-request required context proof

The harness freezes exact initial run ID, input versions, constraints, confirmed facts and selected preferences from the initial required bundle. Before each actual main/summary model start, it independently queries SQL for the answered action IDs and persisted draft IDs available at that time.

The recorder compares that expectation to the current injected SystemMessage only. HumanMessage summary transcripts cannot contribute old contexts. Each proof is tied to sdk_call_id, attempt, execution_epoch and main/summary kind; absent/multiple/mismatched injected contexts fail. Public compact proof contains static synthetic business context and answer/artifact IDs, not private answer text or summary prompts. Calls and case reports both retain proof. Coverage is true only if every observed actual request passes.

Tests reject replacement of a constraint without changing its count, loss of confirmed facts/preferences, later loss of an answered action or artifact, and an absent current SystemMessage masked by an embedded earlier HumanMessage context. The integration positive proves real long-context requests agree with then-current SQL, including summaries after resume and requests after an artifact exists.

## Verification

Red: `/tmp/t13-runner-fix-red.txt` — **7 failing focused cases** before implementation. They exposed lost tool arguments, missing rollback proposal evidence and absent per-request context proof.

Green: `/tmp/t13-runner-fix-green.txt` — **22 passed in 14.75s**, command:

`UV_CACHE_DIR=/tmp/resumate-uv-cache uv run --no-sync pytest backend/tests/test_eval_runner.py backend/tests/test_eval_budget.py -q`

The green selection includes the new facts/preferences loss negatives requested after the first red run, existing reasoning exclusion and budget boundaries. No full12 or broad backend suite was rerun by B.

Actual long positive metadata: `/tmp/t13-runner-fix-long-evidence.json`. **18 model requests (10 main,8 summary), including8 requests in resumed epoch2**, each passed the per-call comparison. Actual five file reads, initial waiting with zero drafts, real checkpoint reopen and final artifact retained. Case path is resolved in that evidence file so later pytest symlinks do not change the reference.

No commits, real credential reads, external provider requests or paid calls. Existing localhost-only fake-provider tests ran within the targeted suite; these remain local protocol tests, not real live evaluation.
