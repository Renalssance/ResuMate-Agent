# Chrome Autofill Extension Design

## Context

ResuMate already parses resumes and job descriptions into structured profiles, runs evidence-based resume-to-JD matching, and persists workflow results through the FastAPI backend. The next product step is to let a user fill application forms on company recruiting websites from those structured resume profiles.

The first version will follow the direction selected during brainstorming:

- Build a Chrome Manifest V3 extension.
- Use a hybrid data model: prefer ResuMate backend profiles, cache editable profile fields locally in the extension.
- Prioritize Chinese company recruiting pages, then fall back to generic form scanning.
- Fill fields only after user confirmation.
- Never submit an application automatically.

The design borrows the practical browser-side pattern from `Zheyi-D/job-hub`: a side panel UI, a content-script fill engine, page scraping rules, local extension storage, and React/Vue-compatible field updates. ResuMate should not copy JobHub's extension-local AI and resume parsing architecture wholesale, because ResuMate already has a backend LLM harness and structured resume parser.

## Goals

1. Let users open a recruiting application page and fill resume fields from ResuMate with one confirmed action.
2. Keep the workflow safe: scan, show matches, let the user review, then fill. The user manually submits.
3. Reuse existing `ResumeProfile` data instead of asking the user to maintain a separate resume from scratch.
4. Work when the backend is temporarily unavailable by using the latest cached application profile.
5. Make field matching explainable enough to debug through confidence levels and match reasons.

## Non-Goals

- No automatic submit, apply, next-step, or final confirmation clicks.
- No captcha, login, anti-bot, or two-factor automation.
- No automatic file upload in the first version.
- No broad hard-coded automation flow per company website.
- No password, verification code, payment, bank card, or national ID field filling.

## Recommended Approach

Use ResuMate as the "brain" and the Chrome extension as the "hand":

```text
ResuMate backend
  -> ApplicationProfile generation
  -> field matching API
  -> safe event logging

Chrome extension
  -> current-page scanning
  -> company/job scraping
  -> match review UI
  -> confirmed field filling
  -> local cache fallback
```

This is more stable than backend-controlled Playwright automation because it runs inside the user's normal logged-in browser session. It avoids handling most login, session, captcha, and anti-automation problems.

## Architecture

Add a new top-level extension package:

```text
extension/
  manifest.json
  service-worker.js
  content/
    fill-engine.js
    scraper.js
  sidepanel/
    sidepanel.html
    sidepanel.css
    sidepanel.js
    resume-fill.js
  lib/
    api-client.js
    storage.js
    constants.js
    field-matcher.js
```

Backend additions live under the existing FastAPI structure:

```text
backend/
  schemas/
    autofill.py
  services/
    autofill.py
  routes/
    autofill.py
  tests/
    test_autofill_profile.py
    test_autofill_matching.py
    test_autofill_events.py
```

Frontend app changes are optional for the first version. Existing document upload and parsed resume management remain the primary way to create source data.

## Backend Data Model

Expose a simplified `ApplicationProfile` for the extension instead of sending raw `ResumeProfile` directly.

```text
ApplicationProfile
  id
  name
  sourceResumeId
  updatedAt
  sections[]
    id
    label
    fields[]
      key
      label
      value
      aliases[]
      category
      confidence
      source
```

Derived field examples:

```text
candidate_name        -> name
contact.email         -> email
contact.phone         -> phone
contact.location      -> city
education[0].school   -> school 1
education[0].degree   -> degree 1
education[0].major    -> major 1
education[0].years    -> education dates 1
work_experience[0]    -> company 1 / title 1 / work dates 1 / work description 1
projects[0]           -> project 1 / role 1 / project description 1
skills                -> skills
languages             -> languages
certifications        -> certifications
self_summary          -> self introduction
```

Fields keep stable keys so the extension can store user edits and reconcile cached data with refreshed backend profiles.

## Backend API

Add an authenticated autofill API namespace:

```text
GET /api/autofill/profiles
```

Returns profile summaries available to the current user.

```text
GET /api/autofill/profiles/{profile_id}
```

Returns one full `ApplicationProfile`.

```text
POST /api/autofill/match
```

Input:

- `profile`: an `ApplicationProfile` or profile id.
- `page`: URL, title, scraped company, scraped position.
- `elements`: scanned form element summaries.

Output:

- matched field key.
- target element id/index.
- confidence: `high`, `medium`, or `low`.
- reason.
- warnings.

```text
POST /api/autofill/events
```

Records scan and fill outcomes for debugging and product improvement. It stores field keys, element summaries, status, and error types. It does not store full field values.

## Matching Strategy

Use a two-layer matcher.

Layer 1: deterministic rules

- Match common Chinese and English labels, names, placeholders, and aria labels.
- Cover name, email, phone, city, school, degree, major, company, role, date range, skills, languages, certificates, project description, self introduction.
- Treat sensitive fields as blocked, including password, captcha, verification code, ID number, bank card, salary expectation if policy requires manual entry, and any field with unclear sensitive meaning.

Layer 2: LLM fallback

- Use existing `AgentHarness` for schema-constrained JSON matching only when rules cannot confidently match enough fields.
- Send element summaries and field summaries, not secrets or password-like fields.
- Validate returned element indexes, field keys, confidence values, and duplicate targets before showing them to the user.

The extension also keeps a lightweight local rule matcher for offline cache mode. Backend matching is authoritative when available.

## Extension Flow

```text
1. User opens a recruiting application page.
2. User opens the ResuMate extension side panel.
3. Extension connects to ResuMate backend and loads available profiles.
4. User selects one profile.
5. User clicks "scan page".
6. content/fill-engine.js returns fillable form elements.
7. content/scraper.js returns company, position, URL, page title, and confidence.
8. Extension calls /api/autofill/match.
9. Side panel shows grouped matches: high, medium, low, blocked, failed.
10. High-confidence matches are selected by default.
11. Medium and low-confidence matches require user review.
12. User clicks "fill selected".
13. content/fill-engine.js fills selected fields and dispatches input/change events.
14. Extension shows success and failure counts.
15. User manually reviews the page and submits if they choose.
```

## Content Script Behavior

`fill-engine.js` runs on application pages and handles:

- Focus tracking for one-off field filling.
- Form scanning for `input`, `textarea`, `select`, and `[contenteditable="true"]`.
- Element metadata extraction:
  - tag.
  - type.
  - id.
  - name.
  - placeholder.
  - aria-label.
  - label text through `label[for]`.
  - closest label text.
  - nearby text.
  - visibility and bounding box.
- Live element caching by scan index.
- React/Vue-compatible input filling:
  - call the native `value` setter when available.
  - dispatch bubbling `input` and `change` events.
  - support `select` by exact and fuzzy option text/value matching.
  - support contenteditable by setting text content and dispatching events.

Before filling, the script verifies the cached element still exists and is still fillable.

## Page Scraper

`scraper.js` is injected on demand and identifies:

- company.
- position.
- URL.
- page title.
- confidence source.

Priority order:

1. Chinese company recruiting site rules.
2. Recruiting SaaS rules.
3. OpenGraph metadata.
4. document title splitting.
5. `h1` and hostname fallback.

Initial Chinese company targets:

- ByteDance: `jobs.bytedance.com`
- Tencent: `careers.tencent.com`, `join.qq.com`
- Alibaba: `talent.alibaba.com`
- Meituan: `zhaopin.meituan.com`
- Baidu: `talent.baidu.com`
- JD: `careers.jd.com`, `zhaopin.jd.com`
- NetEase: `hr.163.com`, `campus.163.com`
- Pinduoduo: `careers.pinduoduo.com`
- Xiaohongshu recruiting subdomains

Initial recruiting SaaS targets:

- Moka: `*.mokahr.com`
- Beisen: `*.beisen.com`, `hotjob`
- Dayee: `*.dayee.com`
- Workday: `*.myworkdayjobs.com`
- Greenhouse: `*.greenhouse.io`
- Lever: `*.lever.co`
- SAP SuccessFactors: domains containing `.successfactors.`

## Local Cache Mode

The extension stores:

- backend base URL.
- auth token or API token if required by existing auth flow.
- selected profile id.
- latest `ApplicationProfile` snapshots.
- user edits to cached fields.
- last scan draft and match results.

If the backend is unavailable:

- Show a clear "using cached profile" status.
- Allow scan and basic rule matching.
- Allow the user to edit cached field values.
- Skip backend event logging until connectivity returns.

## Privacy And Safety

- Do not fill or record password, captcha, verification code, payment, bank card, or national ID fields.
- Do not store full values in autofill event logs.
- Do not automatically click submit, apply, next-step, save, upload, or confirmation buttons.
- Do not bypass login, captcha, 2FA, rate limits, or anti-bot flows.
- For development, `<all_urls>` can be used to simplify testing.
- For release, prefer `activeTab` plus user-triggered injection and optional site allowlists.

## Error Handling

- Backend unavailable: use local cache and show degraded mode.
- No fillable fields: ask user to navigate to the application form page and rescan.
- Low confidence: leave unchecked by default.
- Blocked sensitive field: show blocked status, never fill.
- Missing element at fill time: mark failed and suggest rescanning.
- Unsupported field type: mark failed with the input type.
- Select option not found: report the missing option and leave the field unchanged.
- Dynamic form changed: require rescan before retry.
- File upload encountered: show "manual upload required" in the side panel.

## Testing Strategy

Backend tests:

- `ResumeProfile -> ApplicationProfile` mapping.
- deterministic matching for Chinese and English labels.
- sensitive field filtering.
- LLM match output schema validation and duplicate-target rejection.
- event logging value redaction.

Extension tests and fixtures:

- static Chinese application form.
- static English application form.
- select, textarea, and contenteditable fields.
- React/Vue controlled input simulation.
- scraper fixtures for target Chinese company recruiting pages.
- backend-down cache mode.

Manual acceptance:

- Open a real recruiting application page.
- Scan fields.
- Review grouped confidence matches.
- Fill selected fields only.
- Confirm no submit button was clicked.
- Edit the page or navigate within the form and rescan successfully.

## Rollout

Phase 1:

- Backend `ApplicationProfile` API.
- Deterministic backend matcher.
- MV3 extension shell.
- Content script scanning and confirmed filling.
- Local cache fallback.

Phase 2:

- LLM fallback matcher using `AgentHarness`.
- More Chinese company scraper rules.
- Better side panel review UI.
- Autofill events dashboard or debug view.

Phase 3:

- Optional browser extension packaging.
- Permission hardening.
- User-managed site allowlist.
- More ATS-specific improvements.

## Open Decisions

- Authentication between extension and ResuMate should follow the existing backend auth model unless implementation shows a simpler local token is needed.
- File upload remains manual in version one.
- The first implementation should use plain extension JavaScript unless a build step becomes necessary.
