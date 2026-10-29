# T14 frontend review and scoped repairs

Workspace: `/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`. Baseline: `26d1a35`. Reviewed modified task flows plus their direct callers: accepted-ID persistence, document queue, Matching/Questions/Jobs restoration, SSE transport lifecycle, and AgentTaskView/LongTaskResult. This is source and deterministic interaction review, not visual or real-browser acceptance.

## Findings and assessment

Three supported-use P2 issues were reproduced and repaired after the parent explicitly expanded the initial read-only assignment. No P1 was found. The parent separately owns QuestionsView's restored form selection/count correction and actual browser/visual verification; this report does not claim those complete.

### P2 fixed: unstarted files continued under the next account

`frontend/src/composables/useDocumentParseTasks.ts`, `drain()` and `closeAll()` (current lines 111-121 and 172-177).

The multi-file upload queue waits for each accepted parse result before draining the next file. Closing the document page previously closed UI subscriptions only. The independent accepted-result waiter remained active, and its completion drained the unstarted files. If Alice logged out and Bob logged in before that completion, the next file was submitted by the ordinary Axios interceptor using Bob's current bearer token. This was reproduced with the real queue, upload API, Axios request interception and result stream; only server transport was replaced. It is a normal multi-file upload/account-switch sequence, not an adversarial or narrow race scenario. The queue lifetime behavior predates T14, but the migrated persistent task flow still exercised it and account switching was expressly in this review's scope.

Repair: capture the queue's owner token; stop draining when closed or the owner changes; settle never-started items as unsuccessful in `closeAll()`. Keep the already accepted Run/result waiter alive. DocumentsView now explains that leaving stops files that have not begun uploading while accepted work continues. No backend task is cancelled by leaving a page.

Formal regression covers both page close and owner-token change without close. It asserts the accepted first file succeeds, the second resolves false, and only Alice's first upload request exists. Before repair both returned `[true, true]`; the isolated reproduction explicitly recorded `alice-second.pdf` with `Bearer bob-token`.

### P2 fixed: the Run detail viewer kept a stalled offline stream

`frontend/src/services/agentStream.ts`, `subscribeRun()` transport ownership and retry loop (current lines 64-147).

The new long-task result viewer uses `subscribeRun`, separate from legacy `sse.ts`. Existing reconnect/backoff worked after a fetch error or stream EOF, but a browser `offline` event did not interrupt a reader that remained pending. Server heartbeat comments cannot reach that reader while offline, and no client transport timeout existed. This is the same stalled-reader condition the parent had already fixed and exercised for legacy SSE. The Run viewer could stay on old progress after connectivity returned unless reopened.

Repair: retain the subscription-level controller for explicit close/retry waits, use a fresh transport controller per connection, and abort only that transport on `offline`. A nonterminal interrupted connection reports disconnection and follows the existing backoff/snapshot/cursor replay. Closing aborts both scopes; completion removes the offline listener.

Formal regression verifies the offline reader is cancelled once, the viewer reports disconnection, reconnects with `after=1`, ignores duplicate sequence 1, receives terminal sequence 2, and does not reconnect or emit another error after completion.

### P2 fixed: an old account's pending question request updated the new account's store

`frontend/src/stores/question.ts`, `createQuestionSet()` and `restoreQuestionSet()` (current lines 27-65).

Actual callers are `QuestionsView.generate()` and `restoreGeneratedQuestionSet()`. Generation waits for an accepted task's independent result stream; restoration awaits `fetchAgentRun(taskId)`. Both previously published their eventual result into the shared Pinia `questionSets` and unconditionally updated `error`/`loading`. Logging out clears document state, while the pending question operation can still complete after the next account loads its question state. Thus A's result could appear in B's question list, A's completion could clear B's loading indicator, and A's late failure could replace B's own error. This is a supported account-switch sequence and does not involve a server authorization bypass.

Repair: reuse the existing `readAccessToken()` ownership pattern from the document store. Capture the token when each operation starts; after the awaited API response, return without publishing if the token changed. Error and final loading writes also require the same current token. Old request failures still reject to their original caller. No new store framework, watcher, API request or cancellation path was added.

Four formal regressions use the real question store with deferred API responses. For each of create and restore, they cover A succeeding while B remains pending (no A result, B still loading, then only B's result) and A failing after B has failed (B's error remains). Existing accepted-task result immutability and cached history tests also pass. Before the repair, both result cases appended A's question set and both error cases replaced B's error with A's error.

## Correct behavior retained

- Accepted server IDs replace local request keys before upload/reparse progress subscriptions and active-task persistence. No subscription starts for a merely guessed request ID.
- Active task storage keys include the account username. Reload restores accepted tasks without resubmitting model work. Matching and Jobs restore the accepted task; document restore removes completed entries after terminal replay.
- Result waiters own a separate transport from page progress. Closing UI subscriptions does not cancel the accepted task or its result waiter; the queue repair only prevents starting files that were not uploaded yet.
- Legacy SSE reconnect uses the last durable sequence, tolerates filtered gaps, ignores duplicate replay, and stops on terminal frames or non-retryable HTTP errors. The parent's `sse.ts` offline fix remains intact.
- Question restore fetches `fetchAgentRun(taskId).result`, not the mutable current candidate report. LongTaskResult renders saved question content directly, preserving the older Run's question response after explicit later generation.
- AgentRun store guards its async callbacks with generation IDs, clears on account token changes, and treats replay events as history rather than authoritative status.
- JobsView scopes detail/parse callbacks to its context/request generation and stores the server-accepted parse ID. UI navigation does not cancel the worker.

## Evidence

- `/tmp/task-14-frontend-review-repro.log`: two isolated expected failures. Real Axios interception showed the second Alice file using Bob's token; the stalled Run reader cancellation count was zero.
- `/tmp/task-14-frontend-review-red.log`: **3 failed / 23 passed** in the two formal files, covering close, account change and offline viewer. All failures were the intended behavior assertions.
- `/tmp/task-14-frontend-review-green.log`: **43 passed**, five files, 780 ms.
- `/tmp/task-14-question-owner-red.txt`: **4 failed / 2 passed**, one file; all four failures are the intended stale-result/stale-error assertions.
- `/tmp/task-14-question-owner-green.txt`: **6 passed**, one file, 656 ms. No real server/model calls, no full frontend-suite repeat, no commits.

Initial scoped GREEN command:

```sh
npm run test:unit -- src/composables/useDocumentParseTasks.spec.ts src/services/agentStream.spec.ts src/composables/useTaskSse.spec.ts src/services/sse.spec.ts src/stores/agentRun.spec.ts
```

Question ownership GREEN command:

```sh
npm run test:unit -- src/stores/question.spec.ts
```

The initial temporary runner attempt failed before collection because macOS `/tmp` resolves to `/private/tmp`. The canonical path was corrected before obtaining the two behavior failures; that collection error was not used as RED evidence.

## Modified under expanded authorization

- `frontend/src/composables/useDocumentParseTasks.ts`
- `frontend/src/composables/useDocumentParseTasks.spec.ts`
- `frontend/src/services/agentStream.ts`
- `frontend/src/services/agentStream.spec.ts`
- `frontend/src/views/DocumentsView.vue` (one explanatory paragraph)
- `frontend/src/stores/question.ts`
- `frontend/src/stores/question.spec.ts` (four account-switch regressions; preserves existing history/immutable-result tests)

No edits to RunTimeline, LongTaskResult, root's QuestionsView correction, or browser fixtures. Real browser screenshots and first complete integration runs remain parent-owned evidence.
