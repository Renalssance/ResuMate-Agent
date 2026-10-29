# T13 A scoped review fix

Finding confirmed: an evidence source may refer to a whole `/work_experience/0` or `/projects/0` object. Production accepts these paths and uses the final object's own `source_refs`. The pure verifier stopped one level early and used the inherited root marks instead, causing both false rejection of valid marks and false acceptance of incorrect inherited marks.

Change: `evals/verifiers.py` adds two lines after traversal to take the resolved object's `source_refs` when the value is a dict. The edit-target regex is unchanged. No production files changed.

Regression: `backend/tests/test_eval_verifiers.py::test_whole_entry_source_uses_its_own_marks` covers both supported collections and both correct/incorrect source marks. It also verifies the same whole-object path remains forbidden as a change target.

Before checking: the targeted red detects false source-identity verdicts and would require correcting end-of-path source resolution. The green suite detects any regression to existing scalar-source, ownership, before, duplicate, cancellation and rollback rules; failures would require narrowing the two-line fix.

Commands (direct existing environment; no package sync):
- `.venv/bin/python -m pytest backend/tests/test_eval_verifiers.py -q -k whole_entry_source` → **4 failed, 21 deselected** in `/tmp/t13-cases-scoped-red.log`.
- `.venv/bin/python -m pytest backend/tests/test_eval_verifiers.py -q` → **25 passed** in `/tmp/t13-cases-scoped-green.log`.

Only this follow-up's diff: `/tmp/t13-cases-scoped-fix.diff` (captured against pre-fix working files, not against the project base).

No full CLI/backend run, dependency synchronization, live call or Git commit performed.
