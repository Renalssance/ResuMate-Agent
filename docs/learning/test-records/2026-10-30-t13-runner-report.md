# T13 B runner/budget/records report

Completed in the authorized isolated worktree `/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`.

## Changed files (B ownership)

- `evals/__init__.py`
- `evals/run.py`
- `evals/budget.py`
- `evals/records.py`
- `evals/README.md`
- `backend/tests/test_eval_budget.py`
- `backend/tests/test_eval_runner.py`

No production factory/runner/tools edits, no commits, and no reviewer spawned by B. A/C own their independent files.

## Delivered behavior

CLI: `uv run python -m evals.run --suite core --mode stub|live --output <dir>` with `--cases`, `--config`, `--env-file`.

Each invocation has manifest, calls.jsonl, cases/*.json, report.json/report.md. Main program uses only stdlib top-level imports, sets safe parent in-memory DATABASE_URL before configuration imports; each child receives isolated DATABASE_URL/AGENT_STATE_DIR before any project import. Only model-key/base/model whitelist can enter live children; stub receives no credentials. Automatic dotenv loading and unrelated storage/broker/tracing environment are disabled. No provider keys/URLs or provider error bodies are saved.

Real services create/claim/run/pause/answer/cancel through real SqliteSaver. Harness-only injection runs inside actual read tool execution, after save transaction artifact flush but before commit, and live duplicate save replays actual first tool arguments. SQL snapshot is independently read with ordinary model column serialization and input baselines. Summary/file/checkpoint/context-preservation coverage comes from actual model requests, successful tool responses and Run execution, not case flags.

Budget callback is attached to actual BaseChatModel/ChatOpenAI. Decimal maximum reserve persists before network; all main, SDK summary and retry starts share the ledger. BudgetExceeded is RunError + non-retryable ModelError, raise_error/run_inline true. Actual final cumulative usage reconciles exactly once; missing usage, timeout and lost responses retain reserve. Upper-bound mismatches stop later calls and mark current evaluation incomplete even if it is the final selected case. Calls record both initial reserved amount and final observed amount/null. Model/profile working context 64000 (long <=30000) remains distinct from monetary provider_max_input_tokens=1000000.

Raw live checkpoint files are deleted only inside the generated case/agent directory after child exit, including failure; SQL snapshot, call records and input/output reports remain. Stub checkpoints remain for teaching. This is not a sanitized checkpoint or a crash-recovery claim. First harness requires enable_thinking=false. Records extract only public text blocks and exclude reasoning/additional_kwargs and summary text.

## Concrete configuration

Non-executable template: `/tmp/resumate-live-budget.template.json` and README JSON example. `max_total_cost` and `max_case_cost` deliberately `APPROVAL_REQUIRED`, requiring explicit amount before use.

Model qwen3.7-flash-2026-07-15; CNY; highest Beijing input/output prices 1.2/4.8 per million; provider input reserve 1000000; output cap4096+10 tolerance; timeout60; max_calls120; per_case_calls30; context_window64000; enable_thinking=false. One call reserve is CNY1.21970880. Source URLs/date retained; no paid probe performed. Model/env mismatch fails preflight.

Template launch after approved amount is entered:

`uv run python -m evals.run --suite core --mode live --cases normal-api --config /tmp/resumate-live-budget.json --env-file /Users/bono/Desktop/code/ResuMate-Agent/.env --output artifacts/evals/live-smoke`

This is documentation, not execution authorization or a completed live result.

## Verification and raw evidence

Each check had an actionable failure target; no broad/repeated full-suite runs by B.

- `/tmp/t13-budget-red.txt`: five missing budget feature failures before implementation.
- `/tmp/t13-budget-green.txt`: initial five budget tests passed.
- `/tmp/t13-runner-red.txt`: missing CLI isolation/config behavior failed; public-text record test passed.
- `/tmp/t13-runner-green.txt`: initial budget+runner 9 passed.
- `/tmp/t13-cleanup-red.txt`: removing live cleanup reproduced retained raw checkpoint file failure against a real local ChatOpenAI request to a fake localhost endpoint.
- `/tmp/t13-budget-mismatch-red.txt`: out-of-capacity usage on final case reproduced exit1/fail instead of required exit2/incomplete.
- `/tmp/t13-runner-final-tests.txt`: **14 passed in12.90s** after final fixes. Command: `UV_CACHE_DIR=/tmp/resumate-uv-cache uv run --no-sync pytest backend/tests/test_eval_budget.py backend/tests/test_eval_runner.py -q`.

Tests cover actual no-call when reserve insufficient; unknown usage/timeout reserve retention and ledger reopening; SDK retry boundary; real long-context SDK summary success and denial without retry; usage-over-capacity; explicit .env whitelist; missing config without reading credentials; two independent DBs and real waiting/reopen; public text exclusion; real read/write faults, cancellation and duplicate tool results; localhost-only fake-provider error/mismatched usage; own-checkpoint cleanup and secret/error-body exclusion.

Long targeted CLI smoke (not all12): `/tmp/t13-long-smoke/20261029T175632Z-12564175/report.json`, case `long-context` passed with **8 actual SDK summary calls,5 actual file reads, actual waiting_input, checkpoint reopen and required constraints/version/action/artifact refs preserved**. Input and snapshot retained in case JSON. `/tmp/t13-long-smoke.txt` captures invocation path. Root owns final all12 stub archival and affected regression.

## Limits / truthful status

- No real `.env` content read by B and no external provider or Langfuse request. The only HTTP requests were to the test's localhost fake provider; do not count those test reports as real live evaluation.
- Full12 archived stub and affected runtime regression are root responsibility.
- Real smoke/full live remains pending explicit monetary approval. Current local tests prove callback mechanics against the installed SDK, not provider billing fulfillment.
- Live semantics stay unreviewed; stub semantics not_applicable. Deterministic source IDs cannot establish prose truth.
- Optional production telemetry is C's responsibility; evaluation children intentionally disable export and do not claim cloud receipt.
