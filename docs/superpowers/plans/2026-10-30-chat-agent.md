# Chat Agent Implementation Plan

> Execute in this session. Use subagent-driven-development for the independent frontend task; backend integration remains with the primary agent.

**Goal:** Turn ResuMate into a persistent chat-centered career assistant using existing Deep Agents.
**Architecture:** Chat turns are durable AgentRuns. Business tools delegate long tasks to existing workers and return task references. Vue renders conversations and task cards.
**Tech Stack:** Vue 3, TypeScript, FastAPI, SQLAlchemy, Celery, Deep Agents / LangGraph.
**Spec:** docs/superpowers/specs/2026-10-30-chat-agent-design.md

## Global Constraints
- Preserve all existing workflows and uncommitted user edits.
- No new framework, database migration, hashes, paid model call or deployment.
- Current feature checkout is used so existing user changes remain visible; no branch switch or auto commit.
- Model receives authenticated user identity only from server-bound Run.

### Task 1: Persistent chat backend
- [x] Add failing tests for chat admission, ownership, mutual exclusion, history, real graph continuation, tool task creation.
- [x] Extend RunCreate, Run service and worker dispatch with chat.
- [x] Add backend/services/chat.py and backend/routes/chat_sessions.py; reuse Run routes/errors/events.
- [x] Add backend/agent_runtime/chat.py and chat_tools.py, resume checkpoint across turns and preserve business idempotency.
- [x] Run targeted pytest suites; fix concrete failures.

### Task 2: Vue conversation workspace
- [x] Implement frontend/src/api/chat.ts, views/ChatView.vue and components/chat/ChatTaskCard.vue.
- [x] Test send/reload/task states; use existing SSE subscribeRun and existing upload APIs.
- [x] Add /chat/:sessionId? route and make login/home workspace entry go to /chat.
- [x] Preserve old workflow navigation; scope all new styles to chat components.
- [x] Run component tests and production build.

### Task 3: Integration and delivery
- [x] Verify existing Run and workflow regressions plus browser chat journey.
- [x] Review actual diff for resource ownership and incorrect completion claims.
- [x] Document base project provenance, execution architecture, commands and validation limits.

## Delivery notes

Implemented in the current feature checkout, without commits or deployment. Existing user edits preserved. Reviewer identified two frontend async-state bugs; both reproduced with behavioral tests and fixed. Added restoration/clearing of per-conversation document selections. Real browser/API/worker/Redis/checkpoint journey passed with deterministic model responses; production model quality and MySQL execution were not claimed.
