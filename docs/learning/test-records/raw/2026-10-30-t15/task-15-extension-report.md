# T15 extension implementation report

Workspace: `/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`.
Base implementation began after T14 commit `4fd1bd6`. Scope: extension worker, lib/content/sidepanel, manifest, and Node tests only. Root owns fixtures, real Chromium/SQL acceptance, screenshots, package/README/download page; backend owner owns the HTTP implementation. No commits, browser runs or full extension-suite runs by this agent.

## Implemented behavior

### T15a: background authentication and fixed messages

- `service-worker.js` registers the real runtime listener and keeps the asynchronous response channel open. Only `sender.id === chrome.runtime.id` and the exact own `sidepanel/sidepanel.html` URL are accepted, including when that trusted extension page has a `sender.tab` in browser acceptance. Unknown commands and malformed required payloads return controlled errors without fetching.
- Startup restricts local storage to `TRUSTED_CONTEXTS`. The worker owns login and all cross-origin HTTP calls. GET_SESSION/AUTH replies return only `apiBase`, `authenticated`, `username`; no token/password is returned to the side panel. Password is sent once with login and is not persisted.
- Explicit switch handles GET_SESSION, SAVE_SETTINGS, AUTH_LOGIN, AUTH_LOGOUT, LIST_PROFILES, GET_PROFILE, MATCH_FIELDS, RECORD_EVENT, CAPTURE_JOB_PAGE and SAVE_JOB. There is no arbitrary URL/method/header proxy.
- Auth logout/login, changed API base and current-session 401 clear auth, full-profile cache, activeProfileId and lastMatches. Ordinary network failure preserves the current account's loaded cache.
- The parent identified a supported long-request/account-switch boundary. Formal deferred-response tests reproduced A's old 401 clearing B and A's old LIST result arriving after B. The worker now compares the request's original token/apiBase before clearing a session or publishing account-scoped results. GET_PROFILE also compares that owner before caching. Side panel LIST/GET/scan publishing compares its starting account identity; delayed A responses do not replace B's current fields. Current-session 401 clears visible fields and explicitly requests login.
- Existing SCAN_FORM/FILL_SELECTED/FILL_FOCUSED content commands now require the exact trusted sender and validate their required shapes. Existing combobox behavior still passes using a real-shaped side-panel sender, without a production bypass for empty sender.

### T15b: user-triggered capture and separate editable save

- New `content/job-capture.js` reads existing visible main/article/role-main text, with body fallback. It includes scrollable below-the-fold content and paragraph boundaries; skips hidden ancestors, script/style, navigation/footer, iframe and form controls. It does not fetch, read storage or create a page bridge. It is injected only after the user clicks; not registered as automatic collection in manifest.
- Worker CAPTURE_JOB_PAGE queries the active tab and executes the existing scraper plus the new body reader. It returns one snapshot with full current URL. No URL normalization/truncation or fabricated source IDs are introduced.
- A new job card supports editable title/company/URL/body, explicit separate save, local required/length guidance, busy buttons and success/duplicate-source text. Reading failure or restricted-page failure leaves a paste fallback. Page navigation/activation clears the previous captured draft so old text is not silently combined with a new URL. Re-reading replaces the whole preview.
- SAVE_JOB sends the edited snapshot to `POST /api/jobs/capture`. Optional primaryResumeId is sent only for the selected profile's positive sourceResumeId; a frozen version whose source was deleted omits it. No task/model/application-attach request is made.
- Frozen UI IDs for root integration: `captureJobBtn`, `saveJobBtn`, `jobTitleInput`, `jobCompanyInput`, `jobUrlInput`, `jobTextInput`, `jobCaptureStatus`; card `.job-capture-card`. Chinese buttons: `读取当前岗位`, `收藏岗位`. Existing profile/scan/fill/settings IDs retained.

### T15c: confirmed source selection and manual fill

- Original resume options are labelled “原简历”/“Original resume”. Confirmed options show confirmation source, revision, **creation** date and their existing version ID. Two same-name versions created the same day with the same revision remain distinguishable. No confirmation timestamp is invented.
- Cached summaries preserve sourceKind/sourceResumeId/resumeVersionId/revision/jdId/updatedAt and field counts. Only complete GET_PROFILE results are cached. Offline fallback retains the saved selected ID when present and explicitly displays “缓存版本”/“Cached version”.
- Changing original → version one → version two clears prior matches/checkboxes and disables fill until re-scan. Online MATCH_FIELDS sends only `{profileId,page,elements}`; it does not send the cached profile. Offline matching remains the existing local matcher.
- Fill sends only the selected preview values to existing FILL_SELECTED, never a submit or application action. No投递状态/JobApplication mutation was added.
- Existing beige/oat/brown visual language retained; textarea/URL can wrap and resize, headings/buttons can wrap in the narrow card. All new interaction strings are in English/Chinese i18n. Existing diagnostic details now default to collapsed, as root requested.
- Manifest version is `0.2.0`; permissions and host permissions are unchanged.

## Red/green evidence

Counts describe individual overlapping executions, not a sum or the final suite. All exit codes were observed and outputs read back.

| Unit / command | RED | GREEN |
| --- | --- | --- |
| `node --test extension/tests/auth.test.mjs extension/tests/background.test.mjs extension/tests/fill-engine-combobox.test.mjs` | `/tmp/task-15-extension-auth-red.txt`: 5 failed, 1 passed. Real worker lacked listener; content script accepted untrusted sender. | `/tmp/task-15-extension-auth-green.txt`: 6 passed, 0 failed. |
| `node --test extension/tests/job-capture.test.mjs extension/tests/background.test.mjs extension/tests/i18n.test.mjs` | `/tmp/task-15-extension-capture-red.txt`: 5 failed, 5 passed. Missing CAPTURE route/card and new script (two expected missing-file failures before creation). | `/tmp/task-15-extension-capture-green.txt`: 10 passed, 0 failed. |
| `node --test extension/tests/version-selection.test.mjs extension/tests/background.test.mjs` | `/tmp/task-15-extension-version-red.txt`: 6 failed, 7 passed. Missing version labels, wrong cached selection, old-session 401/list and stale UI list/profile results. | `/tmp/task-15-extension-version-green.txt`: 13 passed, 0 failed. |
| `node --test --test-name-pattern='current account 401' extension/tests/version-selection.test.mjs` | `/tmp/task-15-extension-session-ui-red.txt`: 1 failed: status remained `Connecting...`. | `/tmp/task-15-extension-session-ui-green.txt`: 1 passed. |

The new tests run actual worker listeners, actual content-reader script in a Node VM, and actual sidepanel.js DOM event handlers in the existing frontend jsdom dependency. The sidepanel helper supplies Chrome/HTTP boundary responses; it does not duplicate the selection/capture implementation. Worker tests inspect real HTTP request URL/body/auth header and storage state. Content tests provide fetch/storage traps. Real rendering, extension permissions, production API/SQL behavior and browser submit counters are explicitly left to root's integration run.

## Files

Modified production: `extension/service-worker.js`, `extension/lib/api-client.js`, `extension/lib/storage.js`, `extension/lib/i18n.js`, `extension/content/fill-engine.js`, `extension/sidepanel/sidepanel.js`, `extension/sidepanel/sidepanel.html`, `extension/sidepanel/sidepanel.css`, `extension/manifest.json`.

New production: `extension/content/job-capture.js`.

New tests: `extension/tests/background.test.mjs`, `extension/tests/job-capture.test.mjs`, `extension/tests/version-selection.test.mjs`, `extension/tests/helpers/sidepanel.mjs`. Updated existing test: `extension/tests/fill-engine-combobox.test.mjs` uses the real sender contract and checks rejection. Existing auth/i18n tests were run without relaxing their production contracts.

No fixtures, backend, README, download page, ZIP, main lesson/test record or plan files were edited by this agent. Implementation frozen and root notified for integration after the final one-case 401 GREEN.

## Root integration handoff update

After this agent froze implementation, root reported the first real packaged-extension capture case passed. Root's full Node run initially had 24 passed / 2 failed: unchanged `label-utils.test.mjs` and `visibility-utils.test.mjs` used CommonJS exports while the root package is ESM and the actual scripts exposed their browser globals. Root alone corrected those two test imports to load the scripts and inspect `globalThis.ResuMate*`; no production code changed. Root reported the subsequent full run **26 passed**. Evidence: `/tmp/resumate-t15-extension-full.txt` and `/tmp/resumate-t15-extension-full-fixed.txt`. This agent did not repeat that full run or edit those files. Remaining real-browser/SQL/screenshots/package acceptance is still root-owned.
