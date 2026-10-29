# T12 memory backend implementation report

Workspace: `/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`.
No commit created. Parent owns full regression, E2E, screenshots, and teaching notes.

Implemented files:
- `backend/schemas/memory.py`: only preference/interview_feedback, nonblank 1–4000 characters, strict explicit confirmed=true, forbid client-supplied source/owner fields.
- `backend/services/memory.py`: authenticated owner-filtered CRUD; manual source; list with durable pendingDeletions; capture_memory_ids/memories_for_run; deletion overwrites content with empty string and source_ref with empty object (matches model schema), keeps identity/times for idempotent status.
- `backend/routes/memory.py` and `backend/routes/api.py`: GET/POST/DELETE /api/memories with existing structured error contract.
- `backend/services/agent_runs.py`: freeze only memory IDs after obtaining the Session slot; all old affected tailoring sessions are fenced for create (including duplicate request lookup), retry, answer, claim, and guard_execution. Preserve session_context_invalidated on cancelled task status. PDF export can still create, claim, guard and retry in the same invalidated session.
- `backend/worker_tasks.py`: cleanup only while holding the existing execution_lock. Scanner and execution finally call SqliteSaver.delete_thread, then mark checkpoint_deleted_at. Failures leave pending SQL state to retry next scan. No API access to checkpoints and no new cleanup platform. A stopped running task can be finalized under the OS lock even before the stale-heartbeat threshold.
- `backend/tests/test_agent_memory.py`: 26 cases across SQLite and MySQL.

The existing runner.py was sufficient: it catches RunError and calls finish_run; changes to the shared guard/status service carry the new behavior without another runner branch. Context agent uses the same guard at model/summary/tool boundaries.

Observed TDD evidence:
- `/tmp/t12-memory-red.txt`: 2 failures, missing API gave 405 instead of 422.
- `/tmp/t12-memory-lifecycle-red.txt`: missing frozen IDs plus empty-value schema mismatch; schema contract clarified to ''/{} and corrected.
- `/tmp/t12-memory-fence-red.txt`: invalidated historical sessions accepted new tailoring before the lifecycle fence; initial custom event rejected by existing event union and corrected to run.status/error_code.
- `/tmp/t12-memory-before-cleanup.txt`: 20 passed, 4 failed, remaining failures were missing checkpoint cleanup/recovery.
- `/tmp/t12-memory-green-first.txt`: 26 passed, 7 existing dependency/lifespan warnings.
- `/tmp/t12-memory-regression.txt`: 110 passed, 1 skipped, 7 existing warnings in 24.25s.

Last regression command:
`RESUMATE_TEST_MYSQL_SOCKET=/tmp/resumate-mysql-t02/mysql.sock .venv/bin/python -m pytest backend/tests/test_agent_memory.py backend/tests/test_agent_run_routes.py backend/tests/test_worker_delivery.py backend/tests/test_agent_runtime.py backend/tests/test_resume_export.py -q`

The one skip is the existing SQLite read/write-interleaving test which is intentionally skipped on MySQL because its row lock excludes that interleaving.

Meaningful exercised behaviors:
- Confirmation, limits, manual source and owner isolation.
- Run memory selection is fixed by ID; later additions affect later Runs; deletion removes active content immediately and prevents old reuse.
- queued/waiting_input/waiting_approval become cancelled immediately; running stops cooperatively; failed/succeeded history remains unchanged.
- All tailoring Runs sharing the affected graph thread are included, even completed history; PDF Runs are excluded.
- A deterministic provider deletes memory during its first call: that in-flight response can return, then the next boundary stops, with one provider call and zero saved drafts.
- Real SQLite saver stores three checkpoint versions including messages, summary, /conversation_history file and pending writes. While execution_lock is held cleanup remains pending. The next scanner deletes all checkpoints and writes for affected thread while preserving an unrelated thread.
- A transient delete_thread failure remains pending and is repaired by the next scan.
- Existing Run idempotency, cancellation, interrupt recovery, worker fencing and PDF behavior pass alongside new context middleware.

UI/E2E handoff:
DELETE only persists SQL intent, so pausing the worker before deletion gives a real observable pending state. Resume the worker and run recover_runs to verify complete. Error code is exactly `session_context_invalidated`. affectedRunIds includes historical tailoring task IDs; UI must not describe those existing artifacts as erased. The initial result is pending whenever an affected Session still awaits worker cleanup.

Review follow-up: two confirmed findings are fixed with reproducible red/green tests. See `/tmp/task-12-memory-fix-report.md` and `/tmp/t12-memory-scoped-fix.diff`: (1) MySQL create/delete memory lock ordering with preserved SQLite writer exclusion; (2) sessionInvalidated snapshot boolean without rewriting historical failure codes/events. Final scoped memory/Run/PDF suite: 90 passed, 4 expected skips.
