# T12 memory review fixes

No commit created. All changes are in `/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`.
Scoped production/test diff: `/tmp/t12-memory-scoped-fix.diff`.

## 1. MySQL create/delete lock cycle

The review finding was reproduced on two real MySQL connections. Both creating a new Session and reusing an existing Session produced MySQL error 1213 at deletion's locking AgentRun scan. Synchronization uses threading Events and SQLAlchemy execution hooks; no sleeps or probabilistic stress loops. The test deliberately enters memory capture on one connection while deletion holds the memory row on the other, then releases both SQL operations.

The final change freezes memory IDs before any Session/Run INSERT or claim. Both capture_memory_ids and delete_memory first perform the same per-user no-op UPDATE of business_memories.deleted_at to itself. This gives MySQL the same memory-first row lock order in both paths and establishes SQLite's write transaction before ID selection. The existing graph insertion/session-claim sequence is unchanged: the memory lock is already held before the FK's shared Session lock can be taken. No user/account row lock, new lock table, retry framework, migration, or additional queue was added.

The no-op UPDATE covers the user's memory rows in the same query for both operations, including tombstones; capture's locking SELECT then reads currently active IDs. A creation waiting for a committed deletion therefore sees no deleted ID. If it requested the now-invalidated prior Session, it gets the intended session_context_invalidated error. A new Session can proceed with an empty memory selection.

SQLite has a separate real-connection regression: immediately after memory selection and before Run insertion, a second connection cannot acquire the writer to delete that memory. After the Run commits, deletion succeeds and includes/cancels that Run. The probe uses busy_timeout=0 only on that test connection, so it observes real exclusion without waiting on a guessed interval.

Evidence:
- `/tmp/t12-memory-concurrent-red.txt`: 2 failed, both actual MySQL 1213 deadlocks; 2 SQLite skips.
- `/tmp/t12-memory-concurrent-green.txt`: 2 passed, 2 SQLite skips.
- `/tmp/t12-memory-fix-regression.txt`: 113 passed, 4 expected skips for memory + Run routes + worker delivery + runtime + PDF, before the independent snapshot addition below.

## 2. Session invalidation in historical Run snapshots

The UI finding was reproduced separately: a failed historical Run retained its original error code correctly, but the response omitted session invalidation, so the UI could still offer retry.

run_snapshot now joins AgentSession and reads context_invalidated_at in the same existing SELECT as Run status, actions and event cursor. It returns `sessionInvalidated: true` only for tailoring Runs in invalidated Sessions; PDF Runs return false even if they reuse that Session. Status, original errorCode, history events and artifacts are unchanged.

The new two-database route test preserves failed/model_timeout, exposes sessionInvalidated=true, confirms the old Run's event count is unchanged, and confirms the same-Session PDF remains queued with sessionInvalidated=false.

Evidence:
- `/tmp/t12-memory-snapshot-red.txt`: 2 failures for missing sessionInvalidated, SQLite and MySQL.
- `/tmp/t12-memory-snapshot-green.txt`: 62 passed, 4 expected skips for memory + Run routes.
- `/tmp/t12-memory-fix-final.txt`: final implementation, 90 passed, 4 expected skips in 15.46s for memory + Run routes + PDF export.

Final command:
`RESUMATE_TEST_MYSQL_SOCKET=/tmp/resumate-mysql-t02/mysql.sock .venv/bin/python -m pytest backend/tests/test_agent_memory.py backend/tests/test_agent_run_routes.py backend/tests/test_resume_export.py -q`

The four final skips are deliberate: two MySQL-lock cases on SQLite, one SQLite writer case on MySQL, and the existing SQLite-only answer/cancel interleaving case on MySQL. Seven warnings are existing dependencies/FastAPI lifecycle deprecations.

Changed files for these review fixes only:
- backend/services/agent_runs.py
- backend/services/memory.py
- backend/tests/test_agent_memory.py

Parent owns the overall T12 review/UI/E2E and full-backend test result. Frontend agent was notified of the exact sessionInvalidated boolean contract.
