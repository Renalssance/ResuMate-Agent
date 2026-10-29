# T14 backend review and narrow repair

Workspace: `/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`. Base: `26d1a35`; reviewed current uncommitted production changes, schema/SQL, and supplied focused evidence. Frontend, eval cases, and in-progress crash/browser fixtures were outside this review.

## Assessment

One P2 was reproduced and repaired after the parent explicitly extended this review's scope. No P1 or additional confirmed blocking P2 was found in the reviewed transaction, replay, ownership, response, or event-projection paths. No commits, full-suite repeats, paid model calls, or extra agents.

## Correct behavior confirmed

- `backend/routes/documents.py:48-79` resolves upload request keys before storing a second original. First acceptance saves a pending document, durable Run and queued event through the same SQL commit; accepted failure retains its original for retry.
- `backend/services/agent_runs.py:223-277` uses per-user request identity and captures the fixed AnalysisJob/candidate group during acceptance. Request comparison excludes captured snapshots. Strict kind-specific fields and additive nullable `result_json` are consistent with the migration plan; the manual MySQL 004 and SQLite startup upgrade preserve old rows.
- `backend/services/analysis_tasks.py:80-113` uses committed per-candidate operations to resume only unfinished matches. It initializes model/graph lazily, so terminal-only recovery makes no model request. Report, operation, artifact and progress commit together.
- `backend/services/document_tasks.py:113-138` and `backend/services/analysis_tasks.py:132-166` fence final writes and save successful responses with final business operations and lifecycle state. Failed or cancelled execution cannot publish a successful result. Question input captures the report, and completed Run replay reads immutable `result_json` even after later explicit generation changes current question tables.
- `backend/agents/harness.py:441-447` checks immediately before actual chat SDK calls, including reflection/fallback paths. Calls run without holding the business write transaction. `RunError` escapes retry handling.
- `backend/services/background_tasks.py:13-40` releases the request session before publishing or bounded polling; synchronous success retains the old JSON shape, pending returns a durable ID, and async acceptance does not depend on broker success.
- `backend/services/run_events.py:98-156` derives legacy terminal events from the current lifecycle and saved result, skips an earlier failed attempt after retry, and advances SQL cursors across filtered full pages. There is no process-local progress owner/history remaining.
- Existing reports supplied actual focused dual-database evidence: core 126 passed / one known dialect-specific skip; documents 161 passed; analysis 77 passed. Those suites were not repeated wholesale.

## P2 found and fixed: cancelled matching still started later embedding queries

**Original location:** `backend/graph/candidate_workflow.py:121-127` (now 123-131).

A normal JD with multiple criteria triggers one evidence query per criterion. Both production RAG backends call `embedding_client.embed(query)` for each query (`backend/rag/chroma.py:136-140`, `backend/rag/mysql.py:143-149`). If the user cancels while the first query is in flight, the old loop started every remaining embedding query before the next progress/chat-model guard ran. The final Run was correctly cancelled and business output remained fenced, but extra remote model work and cancellation delay violated the planned per-operation cancellation boundary. This does not rely on a narrow timing race; the cancellation is committed before the next loop iteration.

**Minimal repair:** optional synchronous `guard` on `CandidateAnalysisGraph`, called immediately before each evidence query, supplied by the existing `harness.guard` in `analysis_tasks.py:97-98`. The same existing guard revalidates Run epoch, cancellation and source ownership; no new registry, wrapper, retry framework or storage was added.

**Formal regression:** `backend/tests/test_analysis_tasks.py:107-136`. Real worker, graph, run cancellation, and MySQLRagStore SQL retrieval run against temporary SQLite and MySQL databases. Only the external embedding response is replaced. The first embedding callback cancels the Run; expected behavior is one embedding call, no chat model calls, no match result and cancelled durable state.

Evidence:

- Initial isolated reproduction: `/tmp/test_t14_backend_review.py`, `/tmp/task-14-backend-review-repro.log`: 2 failed, both databases issued the second query.
- Formal RED: `/tmp/task-14-backend-review-red.log`: 2 failed / 30 deselected. Both failures were the extra `Second query`, not fixture errors.
- GREEN: `/tmp/task-14-backend-review-green.log`: **44 passed**, five existing PyMuPDF/SWIG deprecation warnings, 8.15 seconds. Includes analysis task integration, persisted-profile matching, question separation and scoring.
- `git diff --check` on the three touched files had no errors. No full backend suite was run.

Exact GREEN command:

```sh
RESUMATE_TEST_MYSQL_SOCKET=/tmp/resumate-mysql-t02/mysql.sock .venv/bin/python -m pytest backend/tests/test_analysis_tasks.py backend/tests/test_matching_uses_persisted_profiles.py backend/tests/test_question_generation_separation.py backend/tests/test_workflow_scoring.py -q
```

## Related embedding paths and remaining boundary

Document parsing checks `_guard` before `replace_document_chunks` (`document_tasks.py:107-112`), and both actual RAG implementations invoke `before_write` after embedding returns and before index mutation. The supplied document integration evidence already verifies cancel/delete during embedding leaves no new index rows. No additional index fix was needed.

`backend/vector/embedding.py:32` constructs its shared OpenAI client with default SDK retries, unlike chat Harness's `max_retries=0`. The existing outer guard cannot intercept internal SDK retries during one `embed`/`embed_many` call. This is a pre-existing shared-client boundary, not changed or claimed solved by this graph fix. It was specifically reported to the parent; changing global embedding retry behavior was outside this narrow repair. Direct `/evidence/search` is a synchronous read without a Run cancellation contract.

## Optional minor observation

`document_tasks.py:132-138` collapses known non-RunError validation failures such as the explicit multiple-position rejection at line 30 into `document_parse_failed`. This loses the previous actionable split-the-JD explanation in the final legacy frame/synchronous error. If preserving that explanation is desired, map that known validation to a stable explicit error code/message; do not introduce a general error framework. No schema/output-correctness problem or extra model call is implied by this observation.

## Modified under expanded authorization

- `backend/graph/candidate_workflow.py`
- `backend/services/analysis_tasks.py` (graph construction only)
- `backend/tests/test_analysis_tasks.py`

The independent review ended after this focused repair and evidence capture. Actual process-kill recovery and browser acceptance remain with the parent/other agents; this report makes no claim about those runs.
