# T13 A retry predicate scoped fix

Confirmed combined-review finding: a normal case may encounter a transient provider failure and then complete on automatic attempt 2 or 3. Production `finish_run` queues retries while attempt < 3; the eval harness follows those queued retries. Requiring attempt == 1 globally incorrectly rejected an otherwise correct successful Run.

Change: `evals/verifiers.py` now accepts `1 <= attempt <= 3` and still requires `execution_epoch >= 1`. This is the automatic retry range executed by this harness. Epoch has no artificial upper bound: reopening after an applicant answer creates another execution epoch without incrementing attempt. No source rules, case behavior or production state-machine code changed.

Tests added in `backend/tests/test_eval_verifiers.py`:
- successful attempts 2 and 3, including attempt 3 at epoch 4 after continuation;
- rejected attempt zero, negative, and above the automatic retry cap;
- rejected zero and negative execution epochs.

Before checking: the red test would expose a verifier-only false failure on a supported successful retry. Green reruns only the verifier suite to ensure loosening that predicate does not affect the earlier duplicate/source/before/answer/rollback and whole-entry-source regressions.

Commands and raw evidence (direct existing .venv; no dependency sync):
- `.venv/bin/python -m pytest backend/tests/test_eval_verifiers.py -q -k 'successful_automatic_retry or invalid_automatic_attempt'` → **3 failed, 5 passed, 25 deselected**, `/tmp/t13-cases-retry-red.log`.
- `.venv/bin/python -m pytest backend/tests/test_eval_verifiers.py -q` → **33 passed**, `/tmp/t13-cases-retry-green.log`.

Only this follow-up's fix diff: `/tmp/t13-cases-retry-fix.diff`, captured against the prior scoped source-reference fix. No full harness/backend run, paid call, package sync or Git commit.
