# macOS Lightweight Runtime Design

**Status:** Approved design

**Date:** 2026-08-15

**Goal:** Make ResuMate Agent straightforward to install and develop on a Mac without Docker or separately managed PostgreSQL, Redis, or Milvus services, while preserving the existing Vue, FastAPI, LangChain, and LangGraph product behavior.

This design optimizes operational weight rather than the absolute transitive package count. The embedded `chromadb` package is accepted even though it currently installs ONNX Runtime, tokenizers, OpenTelemetry, gRPC, Kubernetes client libraries, and other transitive dependencies.

## Decisions

- Target one local machine and one FastAPI process.
- Create a fresh local data set; do not migrate PostgreSQL or Milvus data.
- Use SQLite as the sole source of truth for business data.
- Use an embedded Chroma `PersistentClient` for document-chunk vector search.
- Remove Redis instead of replacing its chat cache; keep only a small in-process rate limiter.
- Keep LangChain and LangGraph.
- Use an OpenAI-compatible Embeddings API by default.
- Offer `sentence-transformers` as the `local-embeddings` optional dependency.
- Support PDF, DOCX, TXT, and Markdown by default; remove legacy `.doc` support.
- Make OCR optional and disabled by default.
- Remove Docker support and documentation.
- Perform the implementation on the local `main` branch created from `new-agent`.

## Architecture

```text
Vue/Vite :5173
    |
    | HTTP and SSE
    v
FastAPI :8000 (one process)
    |-- SQLite: data/resumate.db
    |-- Chroma PersistentClient: data/chroma/
    |-- Uploaded files: data/documents/
    `-- OpenAI-compatible API
          |-- LLM requests
          `-- embedding requests
```

The supported development command must use a single Uvicorn process. Multiple workers, multiple application instances, and concurrent writers sharing the same Chroma path are outside the supported architecture. Chroma documents `PersistentClient` as a local development and embedded client and states that a local persistence path is not process-safe for concurrent writers.

## Storage Responsibilities

### SQLite

SQLite stores all authoritative application state:

- users and authentication data;
- chat sessions and messages;
- document metadata, extracted text, and structured profiles;
- analysis jobs and candidate state;
- match reports and generated questions.

The default URL is `sqlite:///data/resumate.db`. Engine initialization enables foreign-key enforcement, WAL journaling, a busy timeout, and cross-thread use required by FastAPI synchronous handlers. Startup runs `Base.metadata.create_all()` only.

The existing additive PostgreSQL/SQLite schema patching helpers are removed. This design starts from a fresh database and does not add Alembic or another migration system speculatively.

### Chroma

Chroma stores only retrievable document chunks in one `document_chunks` collection. Each record contains:

- a stable chunk ID;
- the chunk text as the Chroma document;
- an explicitly supplied embedding;
- flat metadata fields: `user_id`, `document_id`, `document_type`, `filename`, `page_number`, `section`, and `chunk_index`.

The current `document_profiles` and `analysis_artifacts` collections are removed. Structured profiles and reports already have authoritative SQLite representations, and candidate report artifacts are not read through vector search.

Queries always filter by user, resume document, and document type before ranking. With cosine distance, the existing API similarity score is computed as `1 - distance`.

The collection records the embedding provider, model, and dimension. A configuration change that conflicts with an existing collection fails with an instruction to remove `data/chroma/` and reparse documents. The application never resets the collection automatically.

## Data Flows

### Upload and parse

```text
store upload
-> extract supported text
-> parse a structured profile with the LLM
-> flush the SQLite document row to obtain document_id
-> embed document chunks in one batched request
-> upsert chunks into Chroma
-> commit the successful SQLite state
```

If a step fails, the SQLite transaction rolls back, newly written Chroma records are deleted as compensation, the unsuccessful newly uploaded file is removed, and the SSE task receives a terminal failure event.

### Reparse

Reparse produces the new text, profile, chunks, and embeddings before touching the old Chroma records. It upserts the new chunk IDs first and deletes obsolete old IDs only after the upsert succeeds. A generation or embedding failure therefore leaves the previous indexed version available. A partial Chroma write is marked failed and can be repaired by retrying reparse; SQLite receives the new text, profile, and parse status only after the replacement completes.

### Matching

```text
load JD and resume structured_data from SQLite
-> retrieve resume evidence chunks from Chroma
-> evaluate criteria through the existing LangGraph and LLM flow
-> calculate the deterministic score in Python
-> save the report and questions to SQLite
```

The workflow no longer loads profiles from the vector store or writes reports to it.

### Chat, progress, and rate limits

- Chat history reads and writes SQLite directly. No replacement cache is introduced.
- `TaskProgressHub` remains the process-local SSE history and queue implementation.
- Rate limiting uses a locked, process-local fixed-window dictionary. Requests opportunistically remove expired windows, so no cleanup thread or scheduler is added.
- Restarting the process clears rate-limit counters and SSE event history. Persisted business results and chat messages remain available from SQLite.

## Embeddings

The default provider uses the existing `openai` SDK against an OpenAI-compatible endpoint:

```env
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_API_KEY=
EMBEDDING_BASE_URL=
```

`EMBEDDING_API_KEY` falls back to `OPENAI_API_KEY`, and `EMBEDDING_BASE_URL` falls back to `OPENAI_BASE_URL`. Inputs are sent in batches and mapped back to the original chunk order.

Local embeddings are enabled with `EMBEDDING_PROVIDER=local` after installing `uv sync --extra local-embeddings`. `EMBEDDING_DEVICE=cpu` remains available for this provider only.

Missing credentials, a missing model name, malformed embedding responses, inconsistent vector dimensions, or a missing optional local package produce explicit errors at first embedding use. No network call is required by unit tests.

## Documents and OCR

Default formats are PDF, DOCX, TXT, and Markdown. `.doc` is rejected as unsupported, allowing removal of `unstructured` and its related loaders.

OCR is disabled by default. The `ocr` extra installs RapidOCR and PDFium support. Native PDF text extraction continues to work without the extra. If OCR is enabled and actually needed without its packages installed, the API returns an instruction to install `uv sync --extra ocr`.

## Dependency Design

`pyproject.toml` becomes the only Python dependency manifest. `backend/requirements.txt` is deleted and `uv.lock` is regenerated.

### Add to the default environment

- `chromadb`

### Remove from direct default dependencies

- `pymilvus`
- `redis`
- `psycopg2-binary`
- `psycopg[binary]`
- `psycopg-pool`
- `sentence-transformers`
- `rapidocr-onnxruntime`
- `pypdfium2`
- `pillow`
- `unstructured`
- `pypdf`
- `docx2txt`
- `openpyxl`
- `tabulate`
- `msoffcrypto-tool`
- `langchain-community`
- `langchain-text-splitters`
- the direct `langsmith` declaration
- `rich`
- `passlib[bcrypt]`

LangChain, LangChain Core, LangChain OpenAI, and LangGraph remain direct dependencies because runtime modules import and use them. The legacy passlib/bcrypt verification branch is removed because no user data is migrated.

Removing a package from the direct list does not guarantee its absence from the resolved environment. In particular, Chroma currently declares `onnxruntime`, `rich`, and `bcrypt` among its own dependencies. Those packages may remain transitively installed even though ResuMate no longer imports them directly. PyTorch and `sentence-transformers` remain excluded from the default environment.

### Optional and development groups

```toml
[project.optional-dependencies]
local-embeddings = [
    "sentence-transformers>=3.0.0",
]
ocr = [
    "rapidocr-onnxruntime>=1.4.4",
    "pypdfium2>=5.6.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.27.0",
]
```

## File Map

### Delete

- `Dockerfile`
- `.dockerignore`
- `docker-compose.yml`
- `frontend/Dockerfile`
- `frontend/nginx.conf`
- `backend/requirements.txt`
- `backend/db/cache.py`
- `backend/vector/milvus_store.py`
- `backend/rag/document_loader.py`
- `backend/rag/milvus.py`
- `backend/tests/test_vector_profile_text.py`
- `pics/framework.png`

Local `volumes/` contents are not deleted. They cease to participate in runtime behavior but may contain recoverable user data.

### Create

- `backend/rag/chroma.py`: embedded client construction and chunk upsert, search, and deletion.
- `backend/tests/test_chroma_store.py`: temporary-directory integration tests using a real embedded Chroma client.
- `backend/tests/test_rate_limit.py`: in-process limit, expiry, and identity isolation tests.
- `backend/tests/test_embedding.py`: remote batch and optional local provider tests.

### Modify

- `pyproject.toml` and `uv.lock`
- `backend/db/database.py`
- `backend/middleware/rate_limit.py`
- `backend/agent/agent.py`
- `backend/vector/embedding.py`
- `backend/routes/documents.py`
- `backend/routes/runs.py`
- `backend/services/analysis.py`
- `backend/graph/candidate_workflow.py`
- `backend/services/documents.py`
- `backend/services/pdf_ocr.py`
- `backend/auth/security.py`
- `.env.example`
- `.gitignore`
- `README.md`
- backend tests that name or mock Milvus/PostgreSQL behavior

The frontend API contract and UI behavior remain unchanged.

## Error Handling

- Chroma failure prevents a document from reaching a successful parse state.
- SQLite errors are raised and logged rather than swallowed.
- Compensation cleanup is attempted after partial Chroma writes; cleanup failure is logged without hiding the original failure.
- The rate limiter preserves HTTP 429 and `Retry-After` behavior.
- Optional features fail with their exact install command.
- Embedding model or dimension changes require explicit local reindexing and never trigger destructive reset behavior.

## Verification

### Automated

```bash
uv run pytest backend/tests -q
npm --prefix frontend test
npm --prefix frontend run build
uv tree --depth 1
```

Tests cover SQLite creation and repositories, Chroma filtering and score conversion, embedding batch ordering, optional-provider failures, chat persistence without Redis, rate-limit windows, upload/reparse compensation, SQLite profile loading in LangGraph, report persistence, OCR defaults, and `.doc` rejection.

A final search checks that infrastructure names are absent from runtime code and current documentation. Resume-parser fixture text that happens to mention technologies such as Redis or Docker remains valid test data.

### macOS smoke test

```bash
uv sync --group dev
cp .env.example .env
uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
npm --prefix frontend ci
npm --prefix frontend run dev
```

The smoke test registers a user, uploads a JD and PDF or DOCX resume, completes parsing and indexing, runs matching, opens evidence and reports, generates questions, and verifies persistence after a backend restart.

## Acceptance Criteria

- Default `uv sync` does not install PyTorch, `sentence-transformers`, Milvus, Redis, or PostgreSQL drivers as ResuMate runtime dependencies. ONNX Runtime and other packages pulled transitively by Chroma are explicitly accepted.
- A developer needs only Python, Node.js, and an OpenAI-compatible API; no local service manager or Docker is required.
- Persistent application data is limited to `data/resumate.db`, `data/chroma/`, and `data/documents/`; existing local log files remain diagnostic output rather than application state.
- Backend tests, frontend checks, and the macOS smoke flow pass.
- README instructions take a new Mac from clone to the complete demo workflow.
- No old-infrastructure compatibility layer, migration utility, or unused configuration switch remains.

## References

- Chroma Python clients: https://docs.trychroma.com/reference/python/client
- Chroma local-client constraints: https://cookbook.chromadb.dev/core/system_constraints/
- Chroma storage layout: https://cookbook.chromadb.dev/core/storage-layout/
- uv dependency groups and extras: https://docs.astral.sh/uv/concepts/projects/dependencies/
- OpenAI embedding model pricing: https://developers.openai.com/api/docs/models/text-embedding-3-small
- Chroma package dependency declaration: https://github.com/chroma-core/chroma/blob/main/pyproject.toml
