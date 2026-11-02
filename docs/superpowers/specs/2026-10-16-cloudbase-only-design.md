# CloudBase-only application deployment — accepted design

The user's later instructions supersede earlier PG, CloudBase AI and Lighthouse proposals.

One CloudBase Run container serves the existing Vue frontend, FastAPI, JWT authentication, document parsing, matching, interview questions, chat, application management and extension APIs. Use one worker, minimum1/maximum1 instance,1CPU/2GB because task progress remains process-local.

Reuse domestic Shanghai environment `dev-d0g73fv8v22380036`. Native SQLAlchemy access connects to the existing CloudBase MySQL at `172.17.0.11:3306`, database `dev-d0g73fv8v22380036`, username `resume`. All17applicationtables and indexes are initialized explicitly, with administrator-only CloudBase data permissions. Cloud startup verifies connectivity rather than creating tables.

Store original documents in the existing classic CloudBase private storage with native `cloud://` file IDs. Container disk is temporary scratch; reparse downloads the original. The user explicitly approved a permanent dedicated server API key for this storage. Do not use PG storage or create an independent COS bucket.

AI uses the project's existing Model/API Key/Base URL, with saved per-user settings taking precedence. The explicitly selected remote embedding model is `qwen3.7-text-embedding-flash` (verified1024dimensions). CloudBase AI is not used. This exception to CloudBase-only infrastructure is explicitly user-authorized.

Persist evidence text and JSON vectors in CloudBase MySQL. Filter by user/document/type before exact cosine retrieval over one resume's chunks. Keep existing evidence contracts and isolate users. Local development retains SQLite/Chroma and existing model configuration.

Long frontend AI operations use `Prefer: respond-async`, return202withtaskId, execute through worker-owned database sessions, and deliver existing result data through task SSE. The frontend waits for terminal result before completing its existing queue/store operation. Task/chat streams send periodic15second heartbeats. This addresses the actual82second parse that completed successfully behind a60second gateway timeout.

Secrets stay in ignored private `.env.cloudbase` and service environment variables. Source archive and Docker context exclude local data and credentials. Deploy on the MySQL VPC/subnet. Only report capabilities verified in the real cloud deployment; use a custom ICP-filed domain for production because the platform default domain displays an access notice.
