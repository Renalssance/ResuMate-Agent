# T14 C — matching, interview questions and answer followup

Workspace: `/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`.
Base supplied by parent: `26d1a35` (T13 closed). No commits, paid calls, external model calls, or full-suite runs performed.

## Delivered

- `backend/agents/harness.py`: synchronous optional `guard: Callable[[], None]` and `progress_callback: Callable[..., None]`. Guard executes immediately before the actual OpenAI SDK request, including reflection retries and response-format fallback. RunError exits immediately. Progress callback receives only event keyword arguments; global progress_hub removed.
- `backend/repositories/runs.py`: create_run, save_report, save_questions and mark_candidate_failed flush; caller owns transaction. Deletion keeps its existing commit behavior.
- `backend/graph/candidate_workflow.py`: existing scoring, evidence hydration and report generation retained; graph accepts plain job_data/resume_data, has no ORM state, repository or write/checkpoint. Optional scoped progress callback.
- `backend/services/analysis.py`: retains question blueprint → batches → ambiguity followup workflow, normalization and validation. `AnalysisService(harness=..., progress_callback=...).generate_questions(user_id=..., report=CandidateReport, task_id=..., question_count=...)` computes a QuestionSet from the frozen supplied report and does not write SQL or create Runs.
- New `backend/services/analysis_tasks.py`: sync `run_match_analysis`, `run_question_generation`, `run_answer_followup(run_id, epoch)`. Short sessions guard ownership/epoch/cancel before model and business writes. Model/graph computation runs without an open SQL transaction. Each candidate commits report/status + `match:<candidateId>` operation + artifact/progress in one transaction. Replay skips complete candidates, uses fixed AnalysisJob/candidate group, and does not even initialize a model when all candidates already committed. Question/followup final operations + output response + artifact + Run terminal state commit atomically. Succeeded replay returns the stored immutable response. Failures use existing `finish_run` lifecycle.
- `backend/routes/runs.py`: match and questions submit typed durable Run requests through shared submission/wait helper; legacy taskId is request key, returned task UUID is server authority. No API model execution or FastAPI BackgroundTasks branch.
- B owns and migrated followup route using typed `answer_followup` request. B/A were informed of exact callback/API shape early.

## Verification and exact evidence

Specific checks were selected to detect model reissue after cancellation, repeat candidate evaluation, changed historical results, writes after supported source deletion/reassignment, and split business/event commits; failures would change guard placement, retry unit or transaction boundary.

1. Harness callback/cancel retry/fallback + repository rollback red: `/tmp/task-14-analysis-red-initial.txt` — 4 failed, 10 passed. A concurrently removed progress_hub first; temporary external runner injected only the removed symbol to let old implementation demonstrate these failures. Production never got a compatibility shim.
2. Same initial tests green: `/tmp/task-14-analysis-green-initial.txt` — 14 passed.
3. New task contract suite before worker existed: `/tmp/task-14-analysis-red-units.txt` — expected explicit fixture assertion `durable analysis worker is missing`; feature module absent (setup errors, not claimed as behavior-level red).
4. Initial durable workers dual database: `/tmp/task-14-analysis-green-units.txt` — 18 passed.
5. Terminal-only match replay regression red: `/tmp/task-14-analysis-red-terminal-replay.txt` — replay failed because eager Harness setup was still required after candidate commit. Fixed via lazy graph/model creation.
6. Final focused command:

```sh
RESUMATE_TEST_MYSQL_SOCKET=/tmp/resumate-mysql-t02/mysql.sock .venv/bin/python -m pytest backend/tests/test_analysis_tasks.py backend/tests/test_agent_harness.py backend/tests/test_run_repository_session.py backend/tests/test_question_generation_separation.py backend/tests/test_prompt_improvement_contracts.py backend/tests/test_matching_uses_persisted_profiles.py backend/tests/test_workflow_scoring.py backend/tests/test_resume_parsing_pipeline.py -q
```

Output: `/tmp/task-14-analysis-green-focused.txt` — **77 passed**, 5 pre-existing PyMuPDF/SWIG import deprecation warnings. SQLite and disposable MySQL both ran; no skips in this command.

`test_analysis_tasks.py` has 15 cases, each on both databases:
- partial candidate failure/retry preserves one group and successful candidate, model calls First=1/Second=2;
- new explicit question generation can overwrite current question tables; older Run replay returns old saved response and makes no model calls;
- answer-followup replay saves once;
- cancel/delete resume/delete JD/reassign resume/delete AnalysisJob after model return forbids business writes;
- candidate artifact insertion failure rolls back report/operation/status;
- final-only recovery needs no model configuration;
- question cancel after blueprint stops the next call; cancel after final model stops all SQL output;
- question validation failure produces failed durable Run without partial question result;
- question/followup artifact insertion failures roll back final result and operation (question current tables/report remain unchanged).

Existing unit test asserting synchronous route-local model failure was replaced by the durable question validation-failure test. Existing scoring, count, evidence normalization, split generation and Harness fallback behavior continue passing.

## Honest evidence boundaries

- These are deterministic model/SQL integration tests, **not** the four actual worker SIGKILL experiments. A/root owns those.
- Legacy AgentHarness still records existing user-level LlmUsageEvent. It is **not linked to T13 Run/attempt/epoch telemetry**. No claim of exact-once model call billing or zero interrupted-call usage. Killed in-flight model usage remains unknown; retry may repeat a started call.
- All three worker handler functions read result_json first for succeeded replay. Question/followup operations and result_json are in the same final transaction, so no separate operation-only recovery state is produced by supported code.
- Graph state is plain values now; no ORM checkpoint serialization, registry, compatibility framework, extra hash or source-cleanup policy introduced.
