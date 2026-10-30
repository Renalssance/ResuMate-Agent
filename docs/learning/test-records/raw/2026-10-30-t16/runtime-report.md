# T16 B runtime + C worker guard report

Production and shared model fixture frozen, 2026-10-30. No commit, no paid request, no full backend/browser run by this agent. T21 cancelled by user; this implementation uses existing HTTP commands/snapshots/events and does not implement WebSocket or question.delta.

## Implemented

- `backend/agent_runtime/factory.py`: `build_interview_agent(user_id,checkpointer,*,run_id,epoch,telemetry=None)` creates the actual installed Deep Agents graph with `response_format=InterviewStep`, StateBackend, existing filesystem budget, disabled execute/task/subagent, and read-only business context tool.
- `backend/agent_runtime/interview_context.py`: typed complete-step schema; exact quote validation against immutable submitted resume/start-time job or accepted SQL answers; server-bound version/revision/job capture/turn IDs. Unsupported output fails as a whole. Opening/feedback/eighth-answer rules and follow-up references are enforced. Context reloads permitted confirmed memories each time, uses frozen sources and SQL turns, and exposes larger material as paginated StateBackend JSON.
- InterviewContextMiddleware overrides only the existing business middleware's context loader. Every actual model call, SDK summary attempt and retry uses the existing fresh guard. SQL gates commit and close before provider/checkpoint I/O.
- `backend/agent_runtime/interviews.py`: one SDK generation followed by a fenced short SQL transaction writing feedback, next question, `ToolOperation(interview:step)`, durable events, immutable Run result and terminal status. Answer eight finishes without question nine. Redis notification is best effort after commit. Uses A's lock ordering and finish helper. Completed graph checkpoint recovery persists its structured response without a second provider call; a new Run clears prior messages/files/todos/summary/structured response.
- `backend/worker_tasks.py`: dispatches interview_generation through existing worker heartbeat/lock and includes these graph sessions in memory-revocation checkpoint cleanup.
- `backend/agent_runtime/telemetry.py`: root observation name uses actual Run.kind, verified with metadata-only fake client.
- `skills/interview-prep/SKILL.md`: frozen-source practice instructions and output/reference contract.
- Shared `backend/tests/interview_model_fixture.py`: actual BaseChatModel provider boundary, native SDK tool structured output, dynamic material/accepted answer references, before_generate/transform_step hooks, long question, actual request/context/step evidence, and real StateBackend paginated reads. No production handler replacement.

## Evidence and exact results

1. `/tmp/task-16-runtime-context-red.txt`: 12 failures because the new context module was absent.
2. `/tmp/task-16-runtime-context-green.txt`: 12 passed.
3. `/tmp/task-16-runtime-graph-red.txt`: 12 passed, 2 expected MySQL skips (socket not yet specified), 2 fixture assertion errors because the real handler was absent.
4. `/tmp/task-16-runtime-graph-green.txt`: 16 passed in 2.26s using SQLite and disposable MySQL databases. Actual eight-round graph, opening/two followups/new topic, no ninth question, immutable old results, exact event sequence, operation uniqueness, worker dispatch and duplicate no-op.
5. `/tmp/task-16-runtime-metadata-red.txt`: 3 failed, 28 deselected. Frozen job title was not accepted as source text; telemetry still reported tailoring. Minimal fixes include frozen title/company and use run.kind.
6. `/tmp/task-16-runtime-boundaries-green.txt`: intermediate 28 passed, 3 failed. Failures were test-only: MySQL observer retained an old repeatable-read transaction, and shared fixture incorrectly counted SDK pagination notices. No production fencing/transaction failure was found.
7. `/tmp/task-16-runtime-memory-green.txt`: 6 passed, 31 deselected, 6.46s. Real next-model guard, actual SDK summary retry after memory deletion, actual checkpointed graph triggering summary and rejecting post-summary provider call; each in SQLite/MySQL.
8. `/tmp/task-16-runtime-green-final.txt`: intermediate despite filename: 35 passed, 2 failed, 11.02s. Only long-material fixture parsing still failed. Do not describe this log as a fully green final invocation.
9. `/tmp/task-16-runtime-pages-green.txt`: final parser correction, 2 passed, 35 deselected, 1.41s. Actual long frozen paragraph is recovered exactly across SDK-truncated file pages. SDK JSON reads contain a range header and plain JSON; truncation notice precedes range header and must not count toward source offset.

All 37 owned tests have passing results across the last combined run and the two-case parser correction; root is performing the final whole-backend run after freeze. No redundant full runtime rerun was requested. Current results cover actual concurrent model pause + committed cancellation/finish, invalid quote and explicit new-Run retry retaining answer, failure after flushed feedback/question with total rollback, checkpoint crash/recovery and stale epoch, frozen inputs despite latest document edits, and real summary/next-call memory guards. Only the external model is synthetic; these are contract/runtime results, not real-model semantic-quality claims.

`/tmp/task-16-runtime-pages-diagnostic*.txt` and page diagnostic JSON are intermediate synthetic debug evidence, not required final artifacts. Prefer red/green logs above for archive; do not archive temporary diagnostic material by default.

## Cross-layer review of A HTTP/service/memory

The reviewed create/command flow is correct: SQL sessions close before Redis admission awaits; replay returns original durable acceptance; only new generation commands use capacity; answer/Run/command/event acceptance is atomic; current locking reads under the InterviewSession gate avoid old MySQL authentication snapshots; memory capture occurs before parent/Run/session gates; cancellation and finish do not invent model work or overwrite accepted answers; explicit feedback confirmation creates source-bound memory and cannot revive deleted memory. Post-commit publish does not roll back SQL.

One supported gap was reported to A: public Run snapshot `sessionInvalidated` still only recognized tailoring even when an interview graph was revoked. A has fixed both graph kinds and supplied regression evidence. A also fixed same-second latest-generation selection by accepted command order, replacing timestamps/random UUID ordering; inspected final implementation uses the latest generating command and falls back to the sole initial Run.

No unresolved P1/P2 correctness finding in the reviewed production paths. Existing generic recovery is intentionally not changed to acquire InterviewSession while holding Run locks; public snapshot derives final state from Run. No T21 event projection/WS work was added.
