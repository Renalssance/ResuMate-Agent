# T13 scoped eval re-review

Workspace: `/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`.
Scope: the three open findings in `/tmp/task-13-eval-review-report.md` and their direct regressions only. The earlier whole-entry source fix was already cleared and was not reviewed again.

## Finding status

### Public tool-call output retention — addressed

Reviewed `/tmp/t13-runner-scoped-fix.diff` and `/tmp/task-13-runner-fix-report.md`.

`evals/records.py` now retains an explicit public message representation with text and tool-call/invalid-tool-call IDs, names and arguments. This preserves rejected or malformed proposals without retaining reasoning, arbitrary additional metadata or parser error text. The callback test checks exact proposal retention and private-field exclusion. The existing real rollback integration now checks that the attempted draft remains in case output while the SQL artifact/operation/event transaction is absent. This directly closes the reported loss of failed proposal evidence.

### Supported successful retries rejected by the verifier — addressed

Reviewed `/tmp/t13-cases-retry-fix.diff` and `/tmp/task-13-cases-retry-fix-report.md`.

`evals/verifiers.py` accepts the harness's supported automatic attempt range 1–3 while requiring a claimed execution epoch. It does not incorrectly cap epochs, which also increase after applicant-answer continuation. Focused tests accept attempts two/three and reject attempts outside the supported range and unclaimed epochs. The change is confined to the predicate and does not loosen artifact or source checks.

### Required-context preservation using count/any-time evidence — addressed

`evals/run.py` freezes the initial required constraint values, facts, preferences and input versions, then queries actual answered-action and draft IDs available before each model call. `evals/records.py` compares that expectation with the current injected SystemMessage for the specific call, attempt, epoch and main/summary kind. Earlier HumanMessage transcripts cannot satisfy the comparison, and all captured calls must pass. Compact proofs are retained in both call and case records.

The new negative tests cover unchanged constraint count with replaced content, lost facts/preferences, lost answered-action/artifact references, and absence of the current SystemMessage masked by a valid older transcript. The real long-context positive test checks summaries after epoch-two continuation, available answers/artifacts, and one proof for every started model call. This closes the exact preservation gap without adding hashes or a second context mechanism.

## Direct regression assessment

No new important regression found in the scoped changes. The explicit public-output selection continues to exclude reasoning and arbitrary provider metadata. Context expectations use the isolated per-case SQL and synthetic baseline; they do not import operator data. The budget policy and production runtime are unchanged by these fixes. The retry predicate remains bounded by the existing automatic retry state machine.

## Evidence and remaining ownership

A reports 33 verifier tests passing after targeted red coverage. B reports seven focused red failures before the fix and 22 runner/budget tests passing after; its saved long-case evidence reports 18 actual requests, eight summaries, eight requests in resumed epoch two and five file reads. I inspected the exact fix diffs and associated tests/reports; I did not repeat their tests, the full 12-case run, dependency synchronization or any paid/live request.

All three findings from the combined eval review are addressed. Root owns the final full 12-case stub and locked-environment verification. This scoped review does not claim those final checks are complete or that real live semantics have passed.
