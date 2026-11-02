# CloudBase Deployment Implementation Plan

> Execute inline in the current checkout to preserve the user's uncommitted frontend and backend work. Do not commit unrelated changes.

**Goal:** Make the complete existing application deployable to CloudBase with durable SQLite, Chroma, and documents.

**Architecture:** One CloudBase Lighthouse server, one application container, one Uvicorn worker; Vue and FastAPI share an HTTPS origin through the CloudBase gateway. Server-local bind mounts preserve all runtime data across container replacement.

**Tech Stack:** Vue 3/Vite, FastAPI, SQLAlchemy/SQLite WAL, embedded Chroma, Docker Compose, CloudBase Lighthouse.

**Spec:** `docs/superpowers/specs/2026-10-16-cloudbase-deployment-design.md`

## Global constraints

- Preserve current business behavior and all pre-existing uncommitted changes.
- Never store SQLite WAL or Chroma on CloudRun ephemeral storage, NFS, or COS mounts.
- Do not upload local credentials or personal data with the source package.
- Prepare local artifacts and validation before asking for final resource/deployment approval.

## 1. Runtime readiness

- [x] Add tests that require `/healthz` JSON rather than SPA fallback, and one stdout application log after repeated setup.
- [x] Confirm both tests fail on the original implementation.
- [x] Implement a fixed health response and idempotent stdout handler; retain file logging.
- [x] Run the focused tests, then the backend suite to detect auth, upload, persistence, or SSE regressions. Result: 169 passed.

## 2. Deployment artifacts

- [x] Add root Dockerfile and allowlisted `.dockerignore`, using Node 24, Python 3.12, uv 0.12.5, and lockfiles.
- [x] Add Compose configuration that injects `.env.cloudbase`, binds `./data` and `./log`, listens on port 80, and health-checks port 8000.
- [x] Add a source-package command with an explicit file list and no secrets or runtime data.
- [x] Document first deployment, gateway, extension URL, restart persistence check, update and backup.
- [x] Run frontend tests/build; build the image if a Docker daemon is available. Report missing Docker explicitly if it cannot be run. Frontend checks passed; no Docker executable exists locally, image build unverified.

## 3. Concrete cloud handoff

- [x] Read existing CloudBase/Lighthouse resource state and gateway routes without mutations. Gateway exists; Lighthouse inventory returns UnauthorizedOperation.NoPermission for TCB_QcsRole.
- [x] Prepare source archive and report its contents, excluding `.env`, `data`, `log`, Git metadata and dependencies. Isolated archive startup/authentication and account persistence across two processes passed.
- [x] Present exact remaining resource, permission, cost and credential-transfer requirements for final deployment approval. Requested existing server SSH address or explicit read-only role grant; purchases and credential uploads remain unapproved.
- [ ] After approval, deploy and verify remote health, authentication, SPA, SSE and persistence; report the actual HTTPS URL only after successful verification.
