# ResuMate CloudBase deployment

The user selected deployment of the entire existing application to CloudBase while preserving business code.

## Architecture

Run the Vue production build and FastAPI API together in one container on a CloudBase-managed Lighthouse server in Shanghai. FastAPI already serves the built frontend and its SPA routes. Keep relative `/auth`, `/api`, and SSE URLs, existing JWT accounts, SQLAlchemy, embedded Chroma, and application workflows.

Bind the server's local persistent `data/` directory to `/app/data` and `log/` to `/app/log`. SQLite WAL and Chroma must remain on a local filesystem, not CFS/NFS or object storage. The existing process-local progress hub requires exactly one application process and one container.

The existing environment is `dev-d0g73fv8v22380036` (`ap-shanghai`, domestic); a read-only detail query confirmed that PostgreSQL is absent. Using managed PostgreSQL would require a data-layer change and additional database/network provisioning. Lighthouse is a CloudBase-supported deployment target that preserves the current architecture.

## Deliverables

- Multi-stage Dockerfile: locked Vue build, locked Python dependencies, compiled frontend served by FastAPI, port 8000, one Uvicorn worker.
- Allowlisted Docker context and deployment archive excluding secrets, user data, logs, dependencies, and Git metadata.
- Compose service with server-local bind mounts, fixed service identity, restart policy, environment injection, and HTTP health check.
- A public `/healthz` returning a fixed payload, and application logs on stdout in addition to the existing files.
- Deployment guide covering CloudBase server prerequisites, environment setup, HTTPS gateway, extension configuration, updates, persistence verification, and backups.

## Deployment boundary

Prepare and test all local changes first. Creating or resizing a paid server, accepting new terms, and exposing the application through the CloudBase gateway require the final deployment approval. Prefer reusing an existing suitable server. Do not move local resumes, accounts, databases, or model credentials without an explicit migration/deployment authorization identifying those items.

Do not claim a successful cloud deployment until the remote container, health endpoint, SPA, authentication, SSE, and restart persistence have been verified. If the account lacks the relevant API permissions or a server is not available, provide the concrete remaining action and leave the tested artifacts ready.

## Verification

Health and stdout tests first, then the existing backend and frontend suites/build. Container build and real runtime tests require Docker; this workstation currently has no Docker executable. Do not substitute source-string checks for a container build. Cloud tests follow only once a server and deployment approval are available.
