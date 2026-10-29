# T14C — four actual process-kill experiments

All four requested integration experiments executed and passed with a complete stable artifact archive: **4 passed in 453.10 seconds (7m33s)**. No production change was needed. This demonstrates the existing durable recovery path at four distinct boundaries; it does not establish exactly-once model calls or paid-provider token/cost certainty.

Final invocation: `f635af81-ed6d-4a40-92d9-7628d7be6d04`.

- Context: `/tmp/task-14-eval-context.json` (four fixed IDs and complete input objects).
- Final machine-readable evidence: `/tmp/task-14-recovery-evidence.json`.
- Raw pytest output: `/tmp/task-14-recovery-run.txt`.
- Stable full artifact archive: `/tmp/task-14-recovery-artifacts-f635af81-8w07lg1j/` (source snapshot, before/after SQL/checkpoint JSON, command logs, Compose logs, disposable final databases, context, evidence and raw pytest copy). This independent directory is outside pytest automatic retention cleanup.

An earlier invocation, `1609db48-1bed-4e47-95ee-ff26922c4dfd`, also executed all four cases and passed in 456.86 seconds. Concurrent pytest retention cleanup removed its temporary per-case logs and source snapshot before archival. Its complete embedded JSON, raw pytest output and context are retained as `/tmp/task-14-recovery-first-evidence.json`, `/tmp/task-14-recovery-first-run.txt`, and `/tmp/task-14-recovery-first-context.json`; the artifact paths inside that first JSON are no longer usable. No first-run raw logs were reconstructed or claimed to exist. The fixture was corrected to allocate a persistent independent `/tmp` root, then all four experiments reran under the **new invocation** above solely to preserve complete raw evidence. Final eval must use only this second invocation, without mixing first-run records.


## What ran

`backend/tests/test_agent_recovery.py` is opt-in under `RESUMATE_COMPOSE_TEST=1`. New test-only `recovery_worker_fixture.py` and `recovery_api_fixture.py` add the four barriers; production has no pause hooks or recovery flags. Each case uses a unique Compose project and isolated SQLite/Redis/data, the actual scheduler and worker, and actual Docker `SIGKILL`. Container inspection confirmed `ExitCode=137` and stopped process in all four cases.

The existing `resumate-t11-worker:latest` image supplied dependencies only. Before the first case, the runner copied the entire current backend source tree to one fixed snapshot and mounted that tree read-only at `/app/backend` for API, worker and scheduler. Thus current T14 models/result column, core services and new fixtures were used rather than the image's old backend. Evidence records the fixed source snapshot path that was both mounted during execution and retained in the stable archive. Baseline before the uncommitted T14 changes was T13 `26d1a35`.

Each Run was seeded from the exact context input object before Linux services started. All live SQLite/checkpoint inspection ran inside the Linux API container; no native host SQL reads/edits occurred while Linux writers were active. No manual `finish_run` calls, accelerated recovery timeout, or manual heartbeat aging were used. Worker-loss cases waited for the existing 90-second stale threshold and 15-second scheduler. Each final state includes contiguous durable event sequences, one successful operation, one version, one artifact event, and one terminal success event.

## Results by boundary

| Case | State immediately before SIGKILL | Recovered state | Model starts | Distinct proof |
| --- | --- | --- | --- | --- |
| `recovery-model-before-return` | running, attempt 1 / epoch 1; no version/operation; checkpoint next=model | succeeded, attempt 2 / epoch 2 | 1 → 4 | The initial model phase started twice, proving unfinished model work can repeat. One eventual version/operation/artifact. |
| `recovery-draft-after-commit` | running, attempt 1 / epoch 1; saved draft and successful operation; checkpoint next=tools | succeeded, attempt 2 / epoch 2 | 2 → 3 | The exact original version ID, complete structured content, fact refs and operation row survived replay unchanged. |
| `recovery-checkpoint-before-terminal` | running, attempt 1 / epoch 1; same Run checkpoint next=[] and interrupts=[]; draft already present | succeeded, attempt 2 / epoch 2 | 3 → 3 | Graph had finished before SQL terminal write. Recovery converged Run state without another model start or another artifact. |
| `recovery-answer-before-delivery` | queued, attempt 1 / epoch 1; one answered action with original ID/response; interrupted checkpoint retained | succeeded, **attempt 1 / epoch 2** | 2 → 5 | API died after answer commit and before publishing. Scanner delivered the queued continuation; the same answered action was retained and cited by the generated draft. |

The fourth case is a legitimate continuation after user input, not recovery of a lost running worker. Therefore attempt stays **1**, while a fresh execution claim increments epoch to **2**. Increasing attempt there would misdescribe existing semantics. For the three killed-running-worker cases, recovery increments both attempt and epoch.

For the answer case, the worker was stopped after the real graph reached `waiting_input`, while scheduler/Redis remained. This prevented a scanner from winning the few milliseconds between the paused API's committed answer and its SIGKILL. API's interrupted HTTP call did not return 202. API and worker were then restarted, and the already queued SQL Run resumed through the actual scanner/delivery path. The answer endpoint was not retried and its publish call never completed.

## Evidence interpretation

Evidence carries exact invocation ID, case ID and input JSON, `executed:true`, `status:pass`, recorded SIGKILL/container state, SQL run before/after, epoch/attempt, output refs, version IDs and contents, successful operation rows, action IDs/responses, full checkpoint state, event sequence and per-phase model start records. It includes normalized keys expected by the eval importer (`run_before`, `run_after`, `model_starts_before/after`, `version_ids`, `operation_rows`, `action_rows`, `events`, `checkpoint`).

These four executed records belong only to the stated invocation. Root will run the final eval CLI with this context/evidence; no final 24-case result is claimed in this report. A stub-only/default eval remains 20 executed plus four `not_run` cases requiring Compose.

The model was the deterministic DraftModel inside the real SDK/checkpoint/tool workflow. Model start counts are exact for these fixtures. Usage for an interrupted equivalent external model call remains **unknown**, not zero; three recovery steps do not imply exactly-once model execution or external cost accounting.

## Command and cleanup

```sh
RESUMATE_COMPOSE_TEST=1 \
RESUMATE_RECOVERY_CONTEXT=/tmp/task-14-eval-context.json \
RESUMATE_RECOVERY_EVIDENCE=/tmp/task-14-recovery-evidence.json \
PATH=/Applications/Docker.app/Contents/Resources/bin:$PATH \
.venv/bin/python -m pytest backend/tests/test_agent_recovery.py -vv -s
```

Every case completed its `docker compose down -v --remove-orphans`; command logs contain the successful cleanup. After completion, the source snapshot, context/evidence copies and all 21 per-case artifact paths were confirmed present (24 required paths total). Existing named application projects/data were not targeted. Test fixture files and reports remain uncommitted for parent integration. No paid models, remote services, Git changes or production recovery changes were performed by this subunit.
