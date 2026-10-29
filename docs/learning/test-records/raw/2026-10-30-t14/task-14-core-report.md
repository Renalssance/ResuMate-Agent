# T14A durable core report

Baseline: T13 commit `26d1a35`. Workspace: `/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`. No commit, remote deployment, paid model call, or full test-suite run was performed.

## Implemented

- Added explicit `document_parse`, `match_analysis`, `question_generation`, `answer_followup` request fields and strict cross-kind rejection. `documentId` is `resume:N`/`jd:N`; request keys remain user-scoped while accepted task identity is the server UUID.
- Added nullable `AgentRun.result_json`, additive SQLite startup upgrade, manual MySQL `deploy/schema/004_long_task_results.sql`. Existing historical SQL files are unchanged; base/schema READMEs document base → 001 → 002 → 003 → 004 and no remote upgrade claim.
- Durable creation captures document source/timestamp, a fixed AnalysisJob and ordered candidate IDs in the initial transaction, saved question report snapshot plus fixed source identities, or typed followup input. Request dedupe compares request fields rather than captured snapshots. `find_upload_run` lets the upload route dedupe before file storage.
- `require_task_sources(db,run)` refreshes and locks fixed owned inputs for new task kinds. Manual retry branches explicitly; it never calls tailoring context logic for migrated tasks. Artifact reads return an explicit empty collection for these task kinds; snapshots expose `result`.
- Replaced the entire FastAPI background task runner with `submit_task(db,user_id,RunCreate,prefer='')`. It commits first, closes the request session, publishes best effort, and returns exact normal async `{taskId}`. The no-Prefer path polls independent short sessions for 45 seconds: original successful JSON, HTTP 400 plus task headers on failure/cancel, or 202 `{taskId,status,code:'task_pending'}` with Location.
- Removed global progress hub, owners, queues, history, and last-progress memory. `TaskProgress(run_id,epoch,session_factory=None).publish(**nonterminal_event)` writes a guarded short SQL transaction; `append_progress(db,run_id,epoch,...)` participates in the caller's business transaction. Progress is monotonic from persisted SQL history.
- `/api/tasks/{UUID}/events` validates SQL ownership and `after`/Last-Event-ID before headers, closes the auth session, and streams ordinary data frames with SQL sequence IDs. Projection preserves legacy result shapes, advances full filtered pages, skips prior failed-attempt terminals after retry, and maps cancelled to legacy failed/cancelled. Terminal frames come from lifecycle state and saved result, never early progress success.
- Added the four explicit worker handler branches; existing lock/scanner/heartbeat code remains unchanged.
- Queued cancellation, failed finish, and exhausted stale recovery synchronize owned document parse status in the same terminal transaction while retaining document/source. Running cancellation still cooperates through the existing execution guard.

## Contracts supplied to B/C

`TaskProgress(run_id, epoch, session_factory=None)`; `.publish(stage=..., status='running', progress=..., message=..., document_id=None, filename=None, stage_progress=None, current=None, total=None, data=None)`.

`append_progress(db, run_id, epoch, **same)`; caller commits. Raw `task.progress` payload uses snake_case; legacy projection emits existing camelCase.

`finish_run(db,run_id,epoch,status, ..., result_json=None)` stores result only for the first successful running→terminal transition; no successful response is written for a cancelled run.

Match input includes `analysisJobId`, ordered `candidateIds` aligned with `resumeIds`. Question input includes `analysisJobId`, `candidateId`, `questionCount`, `resumeId`, `jdId`, `reportSnapshot`.

## Verification and evidence

All checks used disposable test databases and `RESUMATE_TEST_MYSQL_SOCKET=/tmp/resumate-mysql-t02/mysql.sock`; MySQL was executed, not skipped globally.

- `/tmp/task-14-core-red.txt`: **24 failed** before implementation (new-kind rejection/missing persistence and upgrade), establishing red for new durable contracts.
- `/tmp/task-14-core-green-initial.txt`: **24 passed** after core implementation.
- `/tmp/task-14-core-red-cancel.txt`: **6 failed** proving handler-free cancellation/recovery left document state pending.
- `/tmp/task-14-core-green-cancel.txt`: **6 passed**, 24 deselected after narrow transactional status fix.
- `/tmp/task-14-core-focused.txt`: 46 passed / 4 failed while converting old memory tests. Investigation identified test seed Sessions with expire-on-commit holding their own connection after reading run.id. Closing those seed Sessions before testing streaming resolved the fixture interference; production session-close code was already correct.
- `/tmp/task-14-core-green.txt`: **126 passed, 1 skipped, 7 warnings**, 24.89 seconds. Command:

```sh
RESUMATE_TEST_MYSQL_SOCKET=/tmp/resumate-mysql-t02/mysql.sock .venv/bin/python -m pytest backend/tests/test_long_task_core.py backend/tests/test_progress_events.py backend/tests/test_legacy_task_auth.py backend/tests/test_agent_models.py backend/tests/test_run_events.py backend/tests/test_agent_run_routes.py backend/tests/test_worker_delivery.py -q
```

The one skip is the existing SQLite-specific interleaving case on MySQL, whose row lock excludes that interleaving. Warnings are existing framework/dependency deprecations. Checks cover strict schemas, owned source capture, upload key lookup, initial AnalysisJob transaction rollback on event failure, immutable result, new-kind retry ownership, cancelled progress fencing, broker-down acceptance, sync timeout connection release, legacy >100 filtered rows and manual retry history, real additive database upgrade, lifecycle/Run route regression, SQL event atomicity/concurrency, and the existing single-host execution lock.

`git diff --check` for owned files returned no whitespace errors. No full-suite repetition was performed; B/C own their migrated-handler integration tests. Parent owns browser/eval/recovery acceptance and independent final review.
