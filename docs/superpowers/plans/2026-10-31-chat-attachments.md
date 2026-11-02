# Chat attachments implementation plan

**Goal:** Send a local attachment with a question; reuse an owned library document or classify and parse it before answering.
**Architecture:** Keep the existing chat Run/worker/event lifecycle. A multipart chat endpoint stores one original and atomically attaches its metadata to the Run. The worker resolves content identity, emits truthful progress, saves resume/JD results, and passes resolved content to the chat agent. Other files never create library rows.
**Spec:** User-approved flow in this chat, 2026-10-31.
**Constraints:** Preserve existing workspace changes; reuse the existing upload content hash and parsing functions; no additional job framework. Library links open the specific document.

- [x] Test multipart admission, history metadata and retry; implement upload endpoint.
- [x] Test owned duplicate reuse, new resume/JD saves, other-file non-persistence and failure; implement worker preparation and answer integration.
- [x] Replace immediate imports with composer attachments; test no request on selection, multipart send, removal and retained draft on failure.
- [x] Add document deep links and verify focused backend/frontend tests plus frontend build.
