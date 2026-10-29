# T14 eval extension handoff

Workspace: `/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`.
No production files changed for this eval subunit. No commits, paid calls, provider calls, full suite or complete 24-case core invocation performed. Root owns the final full core invocation after actual crash evidence is complete.

## Files

- `evals/cases/recovery.jsonl`: exact 12 agreed IDs with explicit `runner: durable|compose` and frozen synthetic inputs.
- `evals/fixtures.py`: `load_cases('core')` returns original 12 followed by the additional 12. Original `core.jsonl` records and `evals/verifiers.py` remain unchanged.
- `evals/task_fixtures.py`: deterministic structured responses and embeddings. Fake Harness exposes the same `guard` callback and checks it before every simulated model request; no provider client.
- `evals/task_runner.py`: actual acceptance, claim, handler, retry, cancellation, execution lock/stale scanner, repository transactions and final SQL snapshots. Parse upload uses actual HTTP route/TestClient with isolated storage and unavailable broker publication. Vector replacement/search uses the real SQL RAG implementation with deterministic embedding. No pytest test outcomes are imported or relabeled as eval outcomes.
- `evals/task_verifiers.py`: independent readonly SQL and observed-response checks. Every case records actual related rows, model call records and a verdict. No semantic scoring table.
- `evals/recovery_evidence.py`: imports current invocation's exact case/input evidence and checks actual SIGKILL marker, same Run convergence, one durable unit, attempt/epoch advancement and case-specific replay facts. Older invocation/different input is not imported.
- `evals/run.py`: narrowly dispatches the extra runners; reports `executed_count`; keeps original tailoring subprocess, budget and semantic behavior. `--recovery-context` and `--recovery-evidence` are explicit. New durable live cases return `not_run / durable_live_not_implemented` without a provider call. Missing process evidence returns `not_run / requires_compose`.
- `evals/README.md`: full contract, commands, expected 20+4 default, live/SQLite/telemetry boundaries.
- `backend/tests/test_eval_long_tasks.py`: six routing, actual eight-case execution, live safety, and evidence identity tests.
- `backend/tests/test_eval_fixtures.py`: original 12-category assertion explicitly selects original records; factual and long-context fixture assertions unchanged.

## Eight actual deterministic service scenarios

1. `parse-upload-stable-identity`: duplicate HTTP upload request key reuses one accepted source and one file; replay does not call model or alter response.
2. `parse-reparse-saved-job`: uploaded file then explicit file reparse and pasted-JD parse; timestamp, response shapes, vectorization flag and original upload result checked.
3. `match-partial-candidate-replay`: first candidate commits, second fails once; manual retry preserves one job/group and calls First once / Second twice.
4. `question-result-replay`: A generates; explicit B changes current table; replay A returns A's immutable original response with no call.
5. `followup-result-replay`: same Run twice, one saved response/operation/artifact.
6. `cancel-recovery`: queued cancellation blocks claim; stale running cancellation converges under actual OS execution lock; question cancellation after blueprint prevents subsequent model and business writes.
7. `source-deleted-or-reassigned`: JD deletion and resume reassignment after model start each prevent report commits.
8. `business-write-rollback`: actual SQL artifact INSERT failure inside document/report/question/followup transactions leaves no successful operation/result/business outputs (setup match remains).

## Current Compose interface with A

Context: `/tmp/task-14-eval-context.json`.
Invocation ID: `1609db48-1bed-4e47-95ee-ff26922c4dfd`.
Evidence: `/tmp/task-14-recovery-evidence.json`.
Context exactly matches the current four Compose input objects in recovery.jsonl. A seeds real SQL from these objects and uses a frozen backend source copy across the four actual process tests. A supplies before/after SQL/checkpoint payloads plus normalized fields: `run_before`, `run_after`, `model_starts_before/after`, `version_ids`, `operation_rows`, `action_rows`, `events`, `checkpoint`, `kill_signal` and original artifact paths. All evidence is kept in the corresponding case artifact.

A's first real `recovery-model-before-return` evidence was checked against the importer and passes its invariants. At that time, remaining process cases were still running; this report does not claim all four executed or passed. Synthetic importer unit data is never saved as process eval evidence.

Root's final command, only after A confirms complete evidence:

```sh
.venv/bin/python -m evals.run --suite core --mode stub --output /tmp/task-14-evals-final \
  --recovery-context /tmp/task-14-eval-context.json \
  --recovery-evidence /tmp/task-14-recovery-evidence.json
```

Without evidence, same core command should produce 20 executed / 4 not_run, exit 2. With matching actual successful process evidence plus passing original/service cases, expected 24 passed, exit 0. This expected result is not yet reported as observed by this subagent.

## Red/green and focused validation

- `/tmp/task-14-evals-red.txt`: 2 expected failures: loader still had 12 records; crash case selection was an unknown/configuration error rather than requires_compose.
- `/tmp/task-14-evals-first-green.txt`: initial 5 new tests passed; included actual execution of all eight durable case subprocesses and stored SQL oracle/verdict.
- During the final focused check, concurrent parent change added `guard=harness.guard` at graph/RAG boundary. Production was correct; test fixture lacked the public guard attribute. Root cause was identified from zero model calls, failed match Run and the actual changed constructor call. Added the attribute only to the deterministic fixture.
- `/tmp/task-14-evals-green-focused.txt`: **10 passed** (6 new eval tests + 4 original fixture tests). Eight real service scenario subprocesses ran successfully again after that seam change. No original 12-case model runner audit was repeated.
- `/tmp/task-14-evals-live-preflight.txt`: **1 passed**, proving original live mode still refuses missing config without accessing provider credentials/calling a model after the dispatch condition changed.

## Evidence limits

Durable eval SQL is isolated SQLite. Focused C/B integration tests separately exercised MySQL; do not infer MySQL execution from the eval's SQLite artifacts. Full core defaults include 4 explicitly not-run process cases. Real process evidence may be imported only with this invocation/context/input agreement. Model outputs/embeddings are synthetic and do not measure real-model quality/latency. Legacy Harness user-level usage is not T13 Run telemetry; interrupted provider usage remains unknown, never zero or exactly-once.

## Final coordination note

After the focused green run, root explicitly requested preservation of the full default-core truthfulness check. Added seventh new test `test_full_core_without_compose_evidence_executes_twenty_and_leaves_four_unrun`: it executes ordinary full core with no evidence and requires 20 pass / 4 not_run / exit 2 plus 20 actual per-case artifacts and isolated DBs. This full-core test was intentionally **not run by C**; root will run it once in the full backend suite, then run the final explicit-evidence 24-case invocation. Root has been notified that shared eval code is ready and stable.
