# macOS Lightweight Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the complete ResuMate Agent development workflow on one Mac process using SQLite and embedded Chroma, with no Docker, PostgreSQL, Redis, or Milvus service.

**Architecture:** SQLite becomes the only business-data store, while one embedded Chroma collection stores searchable document chunks. The existing FastAPI, Vue, LangChain, and LangGraph behavior remains; OpenAI-compatible embeddings are the default and local embeddings/OCR become optional extras.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2, SQLite, ChromaDB 1.x, OpenAI Python SDK, LangChain, LangGraph, pytest, Vue 3, TypeScript, Vite, uv

---

## File Structure

- `backend/db/database.py`: construct the SQLite engine and enable native SQLite safety pragmas.
- `backend/vector/embedding.py`: expose `embed()` and `embed_many()` for remote or optional local embeddings.
- `backend/rag/chroma.py`: own the single embedded Chroma collection and its replace/search/delete operations.
- `backend/middleware/rate_limit.py`: own the process-local fixed-window limiter.
- `backend/agent/agent.py`: persist chat directly through SQLAlchemy without a cache.
- `backend/routes/documents.py`: coordinate upload/reparse/delete compensation between SQLite, files, and Chroma.
- `backend/graph/candidate_workflow.py`: load profiles from SQLAlchemy objects and use Chroma only for evidence.
- `backend/services/analysis.py` and `backend/routes/runs.py`: construct and call `ChromaRagStore`.
- `backend/services/documents.py` and `backend/services/pdf_ocr.py`: enforce the reduced default format set and optional OCR.
- `pyproject.toml`: remain the only Python dependency manifest.
- `README.md` and `.env.example`: document the zero-service macOS workflow.

### Task 1: Replace the PostgreSQL Engine With SQLite

**Files:**
- Create: `backend/tests/test_sqlite_database.py`
- Modify: `backend/db/database.py`
- Modify: `backend/tests/test_persistent_models.py`

- [ ] **Step 1: Write the failing SQLite configuration tests**

```python
# backend/tests/test_sqlite_database.py
from sqlalchemy import text

from backend.db.database import build_engine


def test_build_engine_enables_sqlite_safety_pragmas(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'resumate.db'}")
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert connection.execute(text("PRAGMA journal_mode")).scalar_one().lower() == "wal"
        assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 30000


def test_build_engine_creates_parent_directory(tmp_path):
    database = tmp_path / "nested" / "resumate.db"
    engine = build_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE check_table (id INTEGER PRIMARY KEY)"))
    assert database.exists()
```

Delete the additive-schema-specific tests from `backend/tests/test_persistent_models.py`: tests for `ADDITIVE_SCHEMA_COLUMNS`, `ADDITIVE_SCHEMA_INDEXES`, `_execute_additive_ddl`, and duplicate PostgreSQL DDL errors. Keep the model, JSON, relationship, repository, and SQLite `create_all()` tests.

- [ ] **Step 2: Run the tests and verify the new API is missing**

Run: `uv run pytest backend/tests/test_sqlite_database.py -q`

Expected: FAIL during collection because `build_engine` is not defined.

- [ ] **Step 3: Implement the minimal SQLite engine factory**

Replace the engine/configuration portion of `backend/db/database.py` with:

```python
import os
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker


DEFAULT_DATABASE_URL = "sqlite:///data/resumate.db"
DATABASE_URL = os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL


def build_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite:///"):
        database_path = Path(database_url.removeprefix("sqlite:///"))
        database_path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False, "timeout": 30},
        )

        @event.listens_for(engine, "connect")
        def _configure_sqlite(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

        return engine
    return create_engine(database_url, pool_pre_ping=True)


engine = build_engine(DATABASE_URL)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)
Base = declarative_base()
```

Keep `get_db()`. Reduce `init_db()` to the delayed model import plus `Base.metadata.create_all(bind=engine)`. Delete all additive-schema constants and helper functions.

- [ ] **Step 4: Run the focused persistence tests**

Run: `uv run pytest backend/tests/test_sqlite_database.py backend/tests/test_persistent_models.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the SQLite foundation**

```bash
git add backend/db/database.py backend/tests/test_sqlite_database.py backend/tests/test_persistent_models.py
git commit -m "refactor: use sqlite for local persistence"
```

### Task 2: Make Remote Embeddings the Default

**Files:**
- Create: `backend/tests/test_embedding.py`
- Modify: `backend/vector/embedding.py`

- [ ] **Step 1: Write failing remote/local provider tests**

```python
# backend/tests/test_embedding.py
from types import SimpleNamespace

import pytest

from backend.vector.embedding import EmbeddingService


class FakeEmbeddingsApi:
    def __init__(self):
        self.calls = []

    def create(self, *, model, input):
        self.calls.append({"model": model, "input": input})
        return SimpleNamespace(
            data=[
                SimpleNamespace(index=1, embedding=[0.0, 1.0]),
                SimpleNamespace(index=0, embedding=[1.0, 0.0]),
            ]
        )


def test_remote_embedding_batches_and_restores_response_order(monkeypatch):
    api = FakeEmbeddingsApi()
    client = SimpleNamespace(embeddings=api)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("EMBEDDING_MODEL", "embed-model")
    service = EmbeddingService(client=client)

    assert service.embed_many(["first", "second"]) == [[1.0, 0.0], [0.0, 1.0]]
    assert api.calls == [{"model": "embed-model", "input": ["first", "second"]}]


def test_remote_embedding_requires_an_api_key_without_injected_client(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="EMBEDDING_API_KEY or OPENAI_API_KEY"):
        EmbeddingService().embed("text")


def test_local_embedding_reports_optional_install_command(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    service = EmbeddingService()
    monkeypatch.setattr(service, "_load_local_model", lambda: (_ for _ in ()).throw(ImportError()))
    with pytest.raises(RuntimeError, match="uv sync --extra local-embeddings"):
        service.embed("text")
```

- [ ] **Step 2: Run the embedding tests and verify failure**

Run: `uv run pytest backend/tests/test_embedding.py -q`

Expected: FAIL because `EmbeddingService` has no injectable client or `embed_many()`.

- [ ] **Step 3: Implement the provider switch and batch API**

Replace `backend/vector/embedding.py` with an `EmbeddingService` that has this public contract:

```python
import os
from functools import cached_property

from openai import OpenAI


DEFAULT_REMOTE_MODEL = "text-embedding-3-small"
DEFAULT_LOCAL_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class EmbeddingService:
    def __init__(self, *, client=None):
        self.provider = (os.getenv("EMBEDDING_PROVIDER") or "openai").lower()
        default_model = DEFAULT_LOCAL_MODEL if self.provider == "local" else DEFAULT_REMOTE_MODEL
        self.model_name = os.getenv("EMBEDDING_MODEL") or default_model
        self.device = os.getenv("EMBEDDING_DEVICE") or "cpu"
        self._client = client

    @property
    def contract(self) -> dict[str, str]:
        return {"provider": self.provider, "model": self.model_name}

    def _remote_client(self):
        if self._client is not None:
            return self._client
        api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("EMBEDDING_API_KEY or OPENAI_API_KEY is required")
        base_url = os.getenv("EMBEDDING_BASE_URL") or os.getenv("OPENAI_BASE_URL") or None
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        return self._client

    @cached_property
    def _local_model(self):
        try:
            return self._load_local_model()
        except ImportError as exc:
            raise RuntimeError(
                "Local embeddings require: uv sync --extra local-embeddings"
            ) from exc

    def _load_local_model(self):
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(self.model_name, device=self.device)

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self.provider == "local":
            vectors = self._local_model.encode(
                texts, normalize_embeddings=True, show_progress_bar=False
            )
            return [[float(value) for value in vector] for vector in vectors]
        if self.provider != "openai":
            raise RuntimeError(f"Unsupported EMBEDDING_PROVIDER: {self.provider}")
        response = self._remote_client().embeddings.create(
            model=self.model_name,
            input=texts,
        )
        rows = sorted(response.data, key=lambda row: row.index)
        if len(rows) != len(texts):
            raise RuntimeError("Embedding API returned an unexpected vector count")
        vectors = [[float(value) for value in row.embedding] for row in rows]
        if not vectors[0] or any(len(vector) != len(vectors[0]) for vector in vectors):
            raise RuntimeError("Embedding API returned inconsistent vector dimensions")
        return vectors

    def embed(self, text: str) -> list[float]:
        return self.embed_many([text])[0]


embedding_service = EmbeddingService()
```

- [ ] **Step 4: Run the embedding tests**

Run: `uv run pytest backend/tests/test_embedding.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the embedding provider**

```bash
git add backend/vector/embedding.py backend/tests/test_embedding.py
git commit -m "refactor: default to remote embeddings"
```

### Task 3: Replace the Milvus Store With Embedded Chroma

**Files:**
- Create: `backend/rag/chroma.py`
- Create: `backend/tests/test_chroma_store.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add Chroma and write real embedded-store tests**

Add `"chromadb>=1.5.9,<2"` to `project.dependencies`, then create:

```python
# backend/tests/test_chroma_store.py
import pytest

from backend.rag.chroma import ChromaRagStore
from backend.services.documents import DocumentChunk


class FakeEmbedding:
    contract = {"provider": "fake", "model": "fake-v1"}

    def __init__(self):
        self.calls = []

    def embed_many(self, texts):
        self.calls.extend(texts)
        return [[1.0, 0.0] if "Python" in text else [0.0, 1.0] for text in texts]

    def embed(self, text):
        return [1.0, 0.0]


def chunk(chunk_id, text, *, user_document=21, index=0):
    return DocumentChunk(
        id=chunk_id,
        run_id=0,
        candidate_id=user_document,
        document_type="resume",
        filename="resume.pdf",
        page_number=1,
        section="Projects",
        chunk_index=index,
        text=text,
        metadata={},
    )


def test_replace_search_filter_and_delete(tmp_path):
    store = ChromaRagStore(path=tmp_path / "chroma", embedding_client=FakeEmbedding())
    store.replace_document_chunks(
        user_id=7,
        document_id=21,
        chunks=[chunk("python", "Python APIs"), chunk("java", "Java services", index=1)],
    )
    store.replace_document_chunks(
        user_id=8,
        document_id=22,
        chunks=[chunk("other", "Python for another user", user_document=22)],
    )

    results = store.search_resume_evidence(
        user_id=7, document_id=21, query="Python", top_k=4
    )
    assert [item.chunk_id for item in results] == ["python", "java"]
    assert results[0].score == pytest.approx(1.0)
    assert all(item.chunk_id != "other" for item in results)

    store.replace_document_chunks(
        user_id=7,
        document_id=21,
        chunks=[chunk("python", "Python APIs updated")],
    )
    assert store.collection.get(where=store.document_filter(7, 21, "resume"))["ids"] == ["python"]

    store.delete_document(user_id=7, document_type="resume", document_id=21)
    assert store.collection.get(where=store.document_filter(7, 21, "resume"))["ids"] == []


def test_embedding_contract_mismatch_requires_reindex(tmp_path):
    path = tmp_path / "chroma"
    ChromaRagStore(path=path, embedding_client=FakeEmbedding()).replace_document_chunks(
        user_id=7, document_id=21, chunks=[chunk("python", "Python APIs")]
    )
    incompatible = FakeEmbedding()
    incompatible.contract = {"provider": "fake", "model": "fake-v2"}
    with pytest.raises(RuntimeError, match="remove data/chroma.*reparse"):
        ChromaRagStore(path=path, embedding_client=incompatible).search_resume_evidence(
            user_id=7, document_id=21, query="Python"
        )


def test_chunk_embedding_prefers_embedding_text(tmp_path):
    embedding = FakeEmbedding()
    item = chunk("python", "raw display text")
    item.metadata["embedding_text"] = "Python normalized text"
    ChromaRagStore(
        path=tmp_path / "chroma", embedding_client=embedding
    ).replace_document_chunks(user_id=7, document_id=21, chunks=[item])
    assert embedding.calls == ["Python normalized text"]
```

- [ ] **Step 2: Run the store tests and verify the module is absent**

Run: `uv run pytest backend/tests/test_chroma_store.py -q`

Expected: FAIL because `backend.rag.chroma` does not exist.

- [ ] **Step 3: Implement the one-collection Chroma store**

Create `backend/rag/chroma.py` with the following complete implementation shape:

```python
import os
from pathlib import Path

import chromadb

from backend.schemas.workflow import EvidenceChunk
from backend.services.documents import DocumentChunk
from backend.vector.embedding import embedding_service


DOCUMENT_COLLECTION = "document_chunks"
DOCUMENT_TYPES = {"jd", "resume"}


def _int_id(value: int | str, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if result < 0:
        raise ValueError(f"{name} must be non-negative")
    return result


class ChromaRagStore:
    def __init__(self, *, path=None, embedding_client=None, client=None):
        self.path = Path(path or os.getenv("CHROMA_PATH") or "data/chroma")
        self.embedding_client = embedding_client or embedding_service
        self.client = client or chromadb.PersistentClient(path=str(self.path))
        self._collection = None

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=DOCUMENT_COLLECTION,
                embedding_function=None,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    @staticmethod
    def document_filter(user_id: int, document_id: int, document_type: str) -> dict:
        if document_type not in DOCUMENT_TYPES:
            raise ValueError(f"document_type must be one of {sorted(DOCUMENT_TYPES)}")
        return {
            "$and": [
                {"user_id": _int_id(user_id, "user_id")},
                {"document_id": _int_id(document_id, "document_id")},
                {"document_type": document_type},
            ]
        }

    def _collection_for_dimension(self, dimension: int):
        contract = self.embedding_client.contract
        expected = {
            "hnsw:space": "cosine",
            "embedding_provider": contract["provider"],
            "embedding_model": contract["model"],
            "embedding_dimension": dimension,
        }
        collection = self.client.get_or_create_collection(
            name=DOCUMENT_COLLECTION,
            embedding_function=None,
            metadata=expected,
        )
        actual = collection.metadata or {}
        mismatches = {
            key: (actual.get(key), value)
            for key, value in expected.items()
            if key in actual and actual.get(key) != value
        }
        missing = expected.keys() - actual.keys()
        if mismatches or (missing and collection.count()):
            raise RuntimeError(
                "Embedding configuration changed; remove data/chroma and reparse documents"
            )
        if missing:
            collection.modify(metadata=expected)
        self._collection = collection
        return collection

    def replace_document_chunks(
        self, *, user_id: int, document_id: int, chunks: list[DocumentChunk]
    ) -> None:
        if not chunks:
            return
        document_types = {chunk.document_type for chunk in chunks}
        if len(document_types) != 1:
            raise ValueError("all chunks must have the same document_type")
        document_type = document_types.pop()
        where = self.document_filter(user_id, document_id, document_type)
        texts = [
            str(
                chunk.metadata.get("embedding_text")
                or chunk.metadata.get("normalized_text")
                or chunk.text
            )
            for chunk in chunks
        ]
        vectors = self.embedding_client.embed_many(texts)
        if len(vectors) != len(chunks) or not vectors or not vectors[0]:
            raise RuntimeError("Embedding service returned invalid vectors")
        collection = self._collection_for_dimension(len(vectors[0]))
        existing_ids = set(collection.get(where=where, include=[])["ids"])
        new_ids = [chunk.id for chunk in chunks]
        collection.upsert(
            ids=new_ids,
            embeddings=vectors,
            documents=[chunk.text for chunk in chunks],
            metadatas=[
                {
                    "user_id": _int_id(user_id, "user_id"),
                    "document_id": _int_id(document_id, "document_id"),
                    "document_type": document_type,
                    "filename": chunk.filename,
                    "page_number": int(chunk.page_number),
                    "section": chunk.section,
                    "chunk_index": int(chunk.chunk_index),
                }
                for chunk in chunks
            ],
        )
        stale_ids = sorted(existing_ids - set(new_ids))
        if stale_ids:
            collection.delete(ids=stale_ids)

    def search_resume_evidence(
        self, *, user_id: int, document_id: int, query: str, top_k: int = 4
    ) -> list[EvidenceChunk]:
        vector = self.embedding_client.embed(query)
        collection = self._collection_for_dimension(len(vector))
        result = collection.query(
            query_embeddings=[vector],
            where=self.document_filter(user_id, document_id, "resume"),
            n_results=int(top_k),
            include=["documents", "metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        return [
            EvidenceChunk(
                chunk_id=str(chunk_id),
                filename=str((metadata or {}).get("filename") or ""),
                page_number=int((metadata or {}).get("page_number") or 0),
                section=str((metadata or {}).get("section") or ""),
                text=str(document or ""),
                score=max(-1.0, min(1.0, 1.0 - float(distance))),
            )
            for chunk_id, document, metadata, distance in zip(
                ids, documents, metadatas, distances, strict=True
            )
        ]

    def delete_document(
        self, *, user_id: int, document_type: str, document_id: int
    ) -> None:
        self.collection.delete(
            where=self.document_filter(user_id, document_id, document_type)
        )
```

Keep the old Milvus files temporarily so the application remains importable until Task 4 switches every call site in one commit.

- [ ] **Step 4: Run the Chroma and parsing tests**

Run: `uv run pytest backend/tests/test_chroma_store.py backend/tests/test_resume_parsing_pipeline.py -q`

Expected: PASS; the existing Milvus-backed parsing tests remain green until Task 4 rewires them.

- [ ] **Step 5: Commit the store replacement**

```bash
git add pyproject.toml backend/rag/chroma.py backend/tests/test_chroma_store.py
git commit -m "feat: add embedded chroma store"
```

### Task 4: Wire Chroma Into Documents and Matching

**Files:**
- Modify: `backend/routes/documents.py`
- Modify: `backend/routes/runs.py`
- Modify: `backend/services/analysis.py`
- Modify: `backend/graph/candidate_workflow.py`
- Modify: `backend/tests/test_matching_uses_persisted_profiles.py`
- Modify: `backend/tests/test_resume_parsing_pipeline.py`
- Modify: `backend/tests/test_resume_second_round_postprocess.py`
- Modify: `backend/tests/test_progress_events.py`
- Delete: `backend/rag/milvus.py`
- Delete: `backend/tests/test_rag_filters.py`
- Delete: `backend/vector/milvus_store.py`
- Delete: `backend/tests/test_vector_profile_text.py`
- Modify: `backend/vector/__init__.py`

- [ ] **Step 1: Change tests to require SQLite profiles and no report artifacts**

In `backend/tests/test_matching_uses_persisted_profiles.py`, construct state objects with SQLAlchemy-shaped relationships:

```python
job = SimpleNamespace(jd=SimpleNamespace(structured_data=job_profile.model_dump(mode="json")))
candidate = SimpleNamespace(
    resume=SimpleNamespace(structured_data=resume_profile.model_dump(mode="json"))
)
state = {
    "user_id": 7,
    "run_id": 11,
    "candidate_id": 13,
    "resume_document_id": 21,
    "job": job,
    "candidate": candidate,
}
result = graph.load_structured_profiles(state)
assert result["job_profile"] == job_profile
assert result["resume_profile"] == resume_profile
assert not hasattr(rag_store, "load_document_profile")
```

Update progress assertions to expect `chroma_search`, `chroma_save`, and `SQLite`, not Milvus/PostgreSQL. In `backend/tests/test_resume_parsing_pipeline.py`, remove `test_resume_profile_embedding_uses_semantic_resume_content_not_only_name` because profile embeddings no longer exist, and remove `test_chunk_embedding_uses_normalized_text_and_preserves_metadata` because its remaining embedding-text contract now lives in `test_chroma_store.py`. Remove the imports of `MilvusRagStore`, collection constants, `build_resume_semantic_summary`, `FakeEmbedding`, and `_ready_client`.

In `backend/tests/test_resume_second_round_postprocess.py`, remove the unused `build_resume_semantic_summary` import. Rename `test_resume_summary_deduplicates_aliases_and_chunk_versions_are_non_empty` to `test_chunk_versions_are_non_empty`, delete its `content`, `summary`, and summary assertions, and keep the four `chunks[0].metadata` assertions. Do not move `build_resume_semantic_summary`: it becomes dead code when profile vectors are deleted.

- [ ] **Step 2: Run the affected tests and verify old imports fail**

Run: `uv run pytest backend/tests/test_matching_uses_persisted_profiles.py backend/tests/test_resume_parsing_pipeline.py backend/tests/test_progress_events.py -q`

Expected: FAIL on Milvus imports and vector-store profile calls.

- [ ] **Step 3: Rewire the production call sites**

Make these concrete changes:

```python
# backend/services/analysis.py
from backend.rag.chroma import ChromaRagStore

# constructor annotation/default
rag_store: ChromaRagStore | None = None
self.rag_store = rag_store or ChromaRagStore()
```

```python
# backend/graph/candidate_workflow.py: load_structured_profiles
job_data = state["job"].jd.structured_data if state["job"].jd else None
resume_data = state["candidate"].resume.structured_data
if not job_data or not resume_data:
    raise ValueError("SQLite is missing a structured JD or resume; reparse the document")
state["job_profile"] = JobProfile.model_validate(job_data)
state["resume_profile"] = ResumeProfile.model_validate(resume_data)
return state
```

Keep `retrieve_evidence()` but rename its stage/message to Chroma. In `persist_report()`, keep the `repository.save_report` call and delete the entire `rag_store.persist_artifact` call and vectorization progress stage.

In both upload and reparse routes, replace `MilvusRagStore()` with `ChromaRagStore()`, call only `replace_document_chunks`, and delete the `persist_document_profile` call. On upload failure, keep the compensating `delete_document` call. In `backend/routes/runs.py`, remove candidate-artifact deletion and use `ChromaRagStore` only for evidence search.

After all imports are switched, delete the four legacy Milvus implementation/test files listed for this task. Make `backend/vector/__init__.py` contain only a module docstring so importing it does not construct a store.

- [ ] **Step 4: Run workflow and route regression tests**

Run: `uv run pytest backend/tests/test_matching_uses_persisted_profiles.py backend/tests/test_resume_parsing_pipeline.py backend/tests/test_resume_second_round_postprocess.py backend/tests/test_progress_events.py backend/tests/test_question_generation_separation.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the application wiring**

```bash
git add backend/routes backend/services/analysis.py backend/graph/candidate_workflow.py backend/tests
git commit -m "refactor: use chroma only for evidence retrieval"
```

### Task 5: Remove Redis From Chat and Rate Limiting

**Files:**
- Create: `backend/tests/test_rate_limit.py`
- Create: `backend/tests/test_conversation_storage.py`
- Modify: `backend/middleware/rate_limit.py`
- Modify: `backend/agent/agent.py`
- Delete: `backend/db/cache.py`

- [ ] **Step 1: Write isolated fixed-window and chat persistence tests**

```python
# backend/tests/test_rate_limit.py
from backend.middleware.rate_limit import FixedWindowLimiter


def test_fixed_window_limit_and_expiry():
    limiter = FixedWindowLimiter()
    assert limiter.hit("auth:user:alice", limit=2, window_seconds=60, now=100) == 0
    assert limiter.hit("auth:user:alice", limit=2, window_seconds=60, now=101) == 0
    assert limiter.hit("auth:user:alice", limit=2, window_seconds=60, now=102) == 18
    assert limiter.hit("auth:user:alice", limit=2, window_seconds=60, now=121) == 0


def test_fixed_window_isolates_identities():
    limiter = FixedWindowLimiter()
    limiter.hit("auth:user:alice", limit=1, window_seconds=60, now=100)
    assert limiter.hit("auth:user:bob", limit=1, window_seconds=60, now=100) == 0
```

```python
# backend/tests/test_conversation_storage.py
from langchain_core.messages import HumanMessage
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.agent.agent import ConversationStorage
from backend.db.database import Base
from backend.db.models import User


def test_conversation_storage_round_trips_without_cache(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chat.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        db.add(User(username="alice", password_hash="hash", role="user"))
        db.commit()
    storage = ConversationStorage(session_factory=sessions)
    storage.save("alice", "session-1", [HumanMessage(content="hello")])
    assert [message.content for message in storage.load("alice", "session-1")] == ["hello"]
```

- [ ] **Step 2: Run the tests and verify missing APIs**

Run: `uv run pytest backend/tests/test_rate_limit.py backend/tests/test_conversation_storage.py -q`

Expected: FAIL because `FixedWindowLimiter` and injectable `session_factory` do not exist.

- [ ] **Step 3: Implement the in-process limiter and direct SQL chat**

Add this core to `backend/middleware/rate_limit.py` and delete Redis/Lua imports and code:

```python
from threading import Lock


class FixedWindowLimiter:
    def __init__(self):
        self._windows: dict[str, tuple[int, int]] = {}
        self._lock = Lock()

    def hit(self, key: str, *, limit: int, window_seconds: int, now: int) -> int:
        window_start = now - (now % window_seconds)
        with self._lock:
            self._windows = {
                item_key: value
                for item_key, value in self._windows.items()
                if value[0] + window_seconds > now
            }
            stored_start, count = self._windows.get(key, (window_start, 0))
            if stored_start != window_start:
                stored_start, count = window_start, 0
            count += 1
            self._windows[key] = (stored_start, count)
            if count <= limit:
                return 0
            return max(1, stored_start + window_seconds - now)


limiter = FixedWindowLimiter()
```

The FastAPI dependency builds `key=f"{group}:{identity}"`, calls `limiter.hit(key, limit=max_requests, window_seconds=window_seconds, now=int(time.time()))`, and raises the existing 429 response when retry seconds are nonzero.

Change `ConversationStorage.__init__(self, session_factory=SessionLocal)` and replace every `SessionLocal()` with `self.session_factory()`. Remove all cache keys, reads, writes, and imports; `load()` calls `get_session_messages()` directly.

- [ ] **Step 4: Run the Redis-removal tests**

Run: `uv run pytest backend/tests/test_rate_limit.py backend/tests/test_conversation_storage.py backend/tests/test_agent_harness.py backend/tests/test_autofill_routes.py -q`

Expected: PASS.

- [ ] **Step 5: Delete the cache module and commit**

```bash
git rm backend/db/cache.py
git add backend/middleware/rate_limit.py backend/agent/agent.py backend/tests/test_rate_limit.py backend/tests/test_conversation_storage.py
git commit -m "refactor: remove redis runtime dependency"
```

### Task 6: Make Legacy Documents and OCR Optional

**Files:**
- Modify: `backend/services/documents.py`
- Modify: `backend/services/pdf_ocr.py`
- Modify: `backend/auth/security.py`
- Modify: `backend/tests/test_document_service.py`
- Create: `backend/tests/test_auth_security.py`
- Delete: `backend/rag/document_loader.py`

- [ ] **Step 1: Write format, OCR, and legacy-hash tests**

```python
# append to backend/tests/test_document_service.py
def test_doc_is_not_a_supported_upload_extension():
    assert ".doc" not in documents.SUPPORTED_EXTENSIONS


def test_missing_ocr_extra_has_install_instruction(monkeypatch):
    from backend.services import pdf_ocr
    monkeypatch.setenv("PDF_OCR_ENABLED", "true")
    monkeypatch.setattr(pdf_ocr, "_import_rapidocr", lambda: (_ for _ in ()).throw(ImportError()))
    with pytest.raises(RuntimeError, match="uv sync --extra ocr"):
        pdf_ocr._get_ocr_engine()
```

```python
# backend/tests/test_auth_security.py
from backend.auth.security import get_password_hash, verify_password


def test_pbkdf2_passwords_still_verify_without_passlib():
    password_hash = get_password_hash("secret")
    assert verify_password("secret", password_hash)
    assert not verify_password("wrong", password_hash)
    assert not verify_password("secret", "$2b$legacy-bcrypt-hash")
```

- [ ] **Step 2: Run tests and verify current defaults fail**

Run: `uv run pytest backend/tests/test_document_service.py backend/tests/test_auth_security.py -q`

Expected: FAIL because `.doc` is supported, OCR defaults on, and `_import_rapidocr` is absent.

- [ ] **Step 3: Remove legacy parsing and make OCR explicitly optional**

Set `SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}` and remove `_extract_doc()`, `import_module`, and every `.doc` branch from `backend/services/documents.py`.

In `backend/services/pdf_ocr.py`:

```python
def ocr_enabled() -> bool:
    return (os.getenv("PDF_OCR_ENABLED") or "false").lower() == "true"


def _import_rapidocr():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR


def _get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        try:
            _ocr_engine = _import_rapidocr()()
        except ImportError as exc:
            raise RuntimeError("PDF OCR requires: uv sync --extra ocr") from exc
    return _ocr_engine
```

Wrap the `pypdfium2` import with the same user-facing error. In `backend/auth/security.py`, delete only the legacy passlib/bcrypt branch; PBKDF2 behavior stays unchanged.

- [ ] **Step 4: Run document and authentication tests**

Run: `uv run pytest backend/tests/test_document_service.py backend/tests/test_auth_security.py backend/tests/test_resume_parsing_pipeline.py -q`

Expected: PASS.

- [ ] **Step 5: Delete the unused loader and commit**

```bash
git rm backend/rag/document_loader.py
git add backend/services/documents.py backend/services/pdf_ocr.py backend/auth/security.py backend/tests
git commit -m "refactor: make ocr and local parsing optional"
```

### Task 7: Prune Manifests, Docker Assets, and Runtime Documentation

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `.env.example`
- Modify: `.gitignore`
- Modify: `README.md`
- Delete: `backend/requirements.txt`
- Delete: `Dockerfile`
- Delete: `.dockerignore`
- Delete: `docker-compose.yml`
- Delete: `frontend/Dockerfile`
- Delete: `frontend/nginx.conf`
- Delete: `pics/framework.png`

- [ ] **Step 1: Make `pyproject.toml` the single dependency source**

Keep runtime imports as direct dependencies and remove the direct packages enumerated in the approved spec. Add:

```toml
[project.optional-dependencies]
local-embeddings = ["sentence-transformers>=3.0.0"]
ocr = ["rapidocr-onnxruntime>=1.4.4", "pypdfium2>=5.6.0"]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.27.0",
]
```

Remove the old `test` and `study` extras. Keep `chromadb>=1.5.9,<2`, accepting its documented ONNX Runtime and other transitive dependencies.

- [ ] **Step 2: Regenerate and inspect the lockfile**

Run: `uv lock`

Expected: exit 0 and an updated `uv.lock`. The lock may contain `sentence-transformers` and PyTorch because uv resolves optional extras into one lock, but they must not appear in the default dependency path. `onnxruntime` may appear through Chroma.

Run: `uv sync --group dev`

Expected: exit 0 and removal of packages no longer selected by the project plus its dev group.

Run: `uv tree --depth 1`

Expected: the direct project list matches `pyproject.toml`; no removed infrastructure client or `local-embeddings` package is selected.

- [ ] **Step 3: Update the environment contract**

Replace the database/vector/cache sections of `.env.example` with:

```env
# ===== Local storage =====
DATABASE_URL=sqlite:///data/resumate.db
CHROMA_PATH=data/chroma

# ===== Embeddings =====
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_API_KEY=
EMBEDDING_BASE_URL=
EMBEDDING_DEVICE=cpu

# ===== Optional PDF OCR =====
PDF_OCR_ENABLED=false
PDF_OCR_MAX_PAGES=8
PDF_OCR_RENDER_SCALE=2.5
PDF_TEXT_MIN_CHARS=30
```

Remove `REDIS_*`, `MILVUS_*`, `VECTOR_STORE_ENABLED`, and PostgreSQL examples. Keep LLM, auth, CORS, and rate-limit settings.

- [ ] **Step 4: Replace README startup and architecture instructions**

Document exactly these commands:

```bash
uv sync --group dev
cp .env.example .env
uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
npm --prefix frontend ci
npm --prefix frontend run dev
```

Add optional sections for `uv sync --extra local-embeddings` and `uv sync --extra ocr`. Replace the old architecture image with the text architecture from the approved spec. State the single-process limitation and that changing embedding models requires deleting `data/chroma/` and reparsing.

- [ ] **Step 5: Delete obsolete build/dependency files without touching local service data**

```bash
git rm backend/requirements.txt Dockerfile .dockerignore docker-compose.yml frontend/Dockerfile frontend/nginx.conf pics/framework.png
```

Do not delete `volumes/` or any untracked runtime data. Ensure `.gitignore` contains `data/`, `*.sqlite`, `*.sqlite3`, `*.db`, and `.DS_Store`.

- [ ] **Step 6: Run static residue checks**

Run:

```bash
rg -n "pymilvus|from redis|import redis|psycopg|MilvusRagStore|PostgreSQL" backend pyproject.toml .env.example README.md
```

Expected: no runtime/config/documentation matches. Mentions inside resume-parser fixture strings may remain when searching the entire test tree.

- [ ] **Step 7: Commit dependency and documentation cleanup**

```bash
git add pyproject.toml uv.lock .env.example .gitignore README.md
git commit -m "chore: remove external service tooling"
```

### Task 8: Run the Complete Verification Matrix

**Files:**
- Modify only files required to fix failures caused by Tasks 1–7.

- [ ] **Step 1: Run all backend tests**

Run: `uv run pytest backend/tests -q`

Expected: PASS with no Redis, PostgreSQL, or Milvus service running.

- [ ] **Step 2: Run frontend checks**

Run: `npm --prefix frontend test`

Expected: PASS.

Run: `npm --prefix frontend run build`

Expected: PASS and `frontend/dist/` generated as ignored output.

- [ ] **Step 3: Verify default dependency boundaries**

Run:

```bash
uv tree | rg "pymilvus|redis v|psycopg|sentence-transformers|torch"
```

Expected: no output for the default environment. Chroma's `onnxruntime` output is accepted.

- [ ] **Step 4: Perform the local smoke test**

Start the backend and frontend with the README commands, then verify registration, login, one JD upload, one PDF or DOCX resume upload, matching, evidence search, question generation, and persistence after a backend restart. Confirm only `data/resumate.db`, `data/chroma/`, and `data/documents/` are created as persistent application data.

- [ ] **Step 5: Check the final diff and commit any verification-only fixes**

Run:

```bash
git status --short
git diff --check
```

Expected: no unexpected or whitespace-error output. If verification fails, return to the task that owns the failing file, add a failing regression test there, apply the minimal fix, rerun that task's focused command, and repeat Task 8. Do not create an empty verification commit.
