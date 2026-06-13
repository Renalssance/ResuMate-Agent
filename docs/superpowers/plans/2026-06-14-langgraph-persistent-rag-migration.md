# LangGraph Persistent RAG Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the authenticated, PostgreSQL-persisted LangGraph and Milvus RAG workflow the application's only upload, parsing, matching, report, and question architecture.

**Architecture:** PostgreSQL becomes the source of truth for documents, runs, reports, and questions; stored files support reparsing and OCR; Milvus stores user-scoped document chunks and searchable artifacts. The Vue frontend sends durable document IDs into an ID-based LangGraph run API and reloads persisted state after refresh.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL/SQLite tests, Pydantic v2, LangGraph, PyMuPDF, RapidOCR, sentence-transformers, Milvus, Vue 3, Pinia, TypeScript, Vitest, pytest

---

## File Structure

### New Production Modules

- `backend/schemas/workflow.py`: LangGraph profile, evidence, report, document, and run API schemas currently living in `schemas/demo.py`.
- `backend/services/documents.py`: unified upload storage, extraction, OCR, chunking, reparsing, and deletion helpers.
- `backend/services/analysis.py`: creates persisted runs and invokes the candidate workflow by database IDs.
- `backend/graph/candidate_workflow.py`: production-named LangGraph workflow.
- `backend/rag/milvus.py`: one Milvus RAG implementation using the existing local embedding service.
- `backend/repositories/runs.py`: SQLAlchemy repository for runs, reports, and question sets.
- `backend/tests/test_documents_api.py`: authenticated persisted document API tests.
- `backend/tests/test_persistent_runs.py`: run repository and ID-based analysis tests.
- `backend/tests/test_rag_filters.py`: user/document/run-scoped Milvus behavior.
- `frontend/src/api/runs.test.ts`: verifies ID-based run requests.
- `frontend/src/stores/document.test.ts`: verifies persisted document loading and upload behavior.

### Modified Modules

- `backend/db/models.py`: add durable document metadata and complete report persistence fields.
- `backend/db/database.py`: ensure additive local schema initialization for new columns.
- `backend/routes/documents.py`: authenticated CRUD/reparse API backed by PostgreSQL.
- `backend/routes/runs.py`: authenticated ID-based creation/list/detail/delete/evidence APIs.
- `backend/routes/api.py`: register only authentication, chat, document, and run routes.
- `backend/schemas/__init__.py`: export production workflow schemas.
- `backend/vector/embedding.py`: expose the single embedding service dimension through produced vectors.
- `backend/app.py`: unchanged routing behavior except through `routes/api.py`.
- `frontend/src/api/documents.ts`: persisted document CRUD contracts.
- `frontend/src/api/runs.ts`: ID-based run creation/list/delete contracts.
- `frontend/src/stores/document.ts`: backend-backed document state with no browser file map.
- `frontend/src/stores/match.ts`: persisted run and report state.
- `frontend/src/stores/question.ts`: use persisted reports/questions.
- `frontend/src/types/document.ts`: durable numeric/string ID document contract.
- `frontend/src/types/run.ts`: persisted run/report contract.

### Removed After Replacement Tests Pass

- `backend/routes/resume.py`
- `backend/routes/jd.py`
- `backend/routes/analysis.py`
- `backend/schemas/demo.py`
- `backend/services/demo_documents.py`
- `backend/services/demo_analysis.py`
- `backend/graph/demo_workflow.py`
- `backend/rag/demo_embedding.py`
- `backend/rag/demo_milvus.py`
- `backend/repositories/demo_runs.py`
- `backend/services/resume_upload.py`

---

### Task 1: Establish Production Names Without Behavioral Changes

**Files:**
- Create: `backend/schemas/workflow.py`
- Create: `backend/services/documents.py`
- Create: `backend/services/analysis.py`
- Create: `backend/graph/candidate_workflow.py`
- Create: `backend/rag/milvus.py`
- Modify: `backend/routes/documents.py`
- Modify: `backend/routes/runs.py`
- Modify: `backend/tests/test_demo_schemas.py`
- Modify: `backend/tests/test_demo_scoring.py`
- Modify: `backend/tests/test_demo_milvus.py`

- [ ] **Step 1: Rename existing tests to production terminology and imports**

Rename:

```text
backend/tests/test_demo_schemas.py -> backend/tests/test_workflow_schemas.py
backend/tests/test_demo_scoring.py -> backend/tests/test_workflow_scoring.py
backend/tests/test_demo_milvus.py -> backend/tests/test_rag_filters.py
```

Update imports to:

```python
from backend.graph.candidate_workflow import calculate_total_score, recommendation_for_score
from backend.rag.milvus import DOCUMENT_COLLECTION, MilvusRagStore
from backend.schemas.workflow import Criterion, EvidenceChunk, JobProfile, MatchEvaluation, QuestionSet
```

- [ ] **Step 2: Run renamed tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_workflow_schemas.py backend/tests/test_workflow_scoring.py backend/tests/test_rag_filters.py -q
```

Expected: collection errors because production-named modules do not exist.

- [ ] **Step 3: Copy active implementations into production-named modules and update internal imports**

Create production modules with the current implementation content, changing imports such as:

```python
from backend.rag.milvus import MilvusRagStore
from backend.repositories.runs import run_repository
from backend.schemas.workflow import CandidateReport, JobProfile
from backend.services.documents import DocumentChunk
```

Temporarily keep `backend/repositories/runs.py` as the current in-memory implementation so this rename is behavior-preserving. Update `backend/routes/documents.py` and `backend/routes/runs.py` to import only production-named modules.

- [ ] **Step 4: Run focused tests and verify they pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_workflow_schemas.py backend/tests/test_workflow_scoring.py backend/tests/test_rag_filters.py -q
```

Expected: all focused tests pass.

- [ ] **Step 5: Commit production naming**

```powershell
git add backend/schemas/workflow.py backend/services/documents.py backend/services/analysis.py backend/graph/candidate_workflow.py backend/rag/milvus.py backend/repositories/runs.py backend/routes/documents.py backend/routes/runs.py backend/tests
git commit -m "refactor: formalize LangGraph RAG modules"
```

---

### Task 2: Extend The Persistent Data Model

**Files:**
- Modify: `backend/db/models.py`
- Modify: `backend/db/database.py`
- Modify: `backend/schemas/workflow.py`
- Create: `backend/tests/test_persistent_models.py`

- [ ] **Step 1: Write failing persistence-model tests**

Add tests that initialize a temporary SQLite database and assert the durable fields:

```python
def test_document_and_match_models_store_workflow_payloads(db_session, user):
    resume = Resume(
        user_id=user.id,
        filename="candidate.pdf",
        file_path="data/documents/candidate.pdf",
        raw_text="Real uploaded resume text",
        structured_data={"candidate_name": "Real Candidate"},
        parse_status="success",
        document_size=123,
    )
    db_session.add(resume)
    db_session.flush()

    job = AnalysisJob(user_id=user.id, jd_id=None, title="Backend Engineer", status="completed")
    db_session.add(job)
    db_session.flush()
    candidate = AnalysisCandidate(job_id=job.id, resume_id=resume.id, status="completed")
    db_session.add(candidate)
    db_session.flush()
    result = MatchResult(
        job_id=job.id,
        candidate_id=candidate.id,
        resume_id=resume.id,
        overall_score=82,
        recommendation="strong_recommend",
        report_json={"candidate_name": "Real Candidate", "evaluations": []},
    )
    db_session.add(result)
    db_session.commit()

    assert resume.parse_status == "success"
    assert resume.document_size == 123
    assert result.report_json["candidate_name"] == "Real Candidate"
```

Also test `JobDescription.file_path`, `document_size`, and `parse_status`.

- [ ] **Step 2: Run the model test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_persistent_models.py -q
```

Expected: failures for missing model fields.

- [ ] **Step 3: Add durable fields and additive local initialization**

Add:

```python
class Resume(Base):
    document_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parse_status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False, index=True)

class JobDescription(Base):
    filename: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    document_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parse_status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False, index=True)

class MatchResult(Base):
    report_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
```

In `backend/db/database.py`, after `Base.metadata.create_all`, inspect existing local tables and issue additive `ALTER TABLE ADD COLUMN` statements only for missing columns. Do not drop or recreate existing tables.

- [ ] **Step 4: Run model tests and existing backend tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_persistent_models.py backend/tests/test_workflow_schemas.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit the persistent model**

```powershell
git add backend/db/models.py backend/db/database.py backend/schemas/workflow.py backend/tests/test_persistent_models.py
git commit -m "feat: persist workflow document and report state"
```

---

### Task 3: Build Unified Stored-Document Extraction And OCR

**Files:**
- Modify: `backend/services/documents.py`
- Modify: `backend/services/pdf_ocr.py`
- Create: `backend/tests/test_document_service.py`

- [ ] **Step 1: Write failing service tests for real upload content and OCR fallback**

Use `UploadFile` and temporary storage:

```python
@pytest.mark.asyncio
async def test_store_and_extract_text_uses_uploaded_content(tmp_path):
    upload = UploadFile(filename="resume.txt", file=BytesIO(b"Real Candidate\nPython FastAPI Milvus"))
    stored = await store_and_extract_upload(upload, storage_root=tmp_path)

    assert stored.path.exists()
    assert "Real Candidate" in stored.raw_text
    assert stored.size == len(b"Real Candidate\nPython FastAPI Milvus")


def test_extract_pdf_pages_uses_ocr_when_normal_text_is_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(documents, "_extract_pdf_text_pages", lambda path: [])
    monkeypatch.setattr(
        documents,
        "extract_pdf_text_with_ocr",
        lambda path: PdfOcrResult(text="--- OCR Page 1 ---\nReal OCR Candidate", page_count=1, ocr_page_count=1),
    )

    pages = extract_stored_pages(tmp_path / "scan.pdf", "scan.pdf")
    assert pages[0].text.endswith("Real OCR Candidate")
```

- [ ] **Step 2: Run the service tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_document_service.py -q
```

Expected: failures because unified storage/extraction helpers are missing.

- [ ] **Step 3: Implement safe storage, extraction, OCR page conversion, chunking, and cleanup**

Expose these focused interfaces:

```python
@dataclass(frozen=True)
class StoredDocument:
    filename: str
    path: Path
    size: int
    raw_text: str
    pages: list[PageText]


async def store_and_extract_upload(
    file: UploadFile,
    *,
    storage_root: Path = DOCUMENT_DIR,
) -> StoredDocument: ...


def extract_stored_pages(path: Path, filename: str) -> list[PageText]: ...


def delete_stored_file(path: str) -> None: ...
```

For PDFs, try PyMuPDF page text first; when combined text is below `PDF_TEXT_MIN_CHARS`, call `extract_pdf_text_with_ocr` and convert `--- OCR Page N ---` sections into `PageText` records. Reject unsupported or empty documents with `UnsupportedDocumentError`.

- [ ] **Step 4: Run service tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_document_service.py -q
```

Expected: all service tests pass.

- [ ] **Step 5: Commit the unified document service**

```powershell
git add backend/services/documents.py backend/services/pdf_ocr.py backend/tests/test_document_service.py
git commit -m "feat: unify stored document extraction and OCR"
```

---

### Task 4: Unify Embedding And User-Scoped Milvus RAG

**Files:**
- Modify: `backend/vector/embedding.py`
- Modify: `backend/rag/milvus.py`
- Modify: `backend/services/documents.py`
- Modify: `backend/tests/test_rag_filters.py`

- [ ] **Step 1: Extend failing RAG tests for user and durable-document isolation**

Add:

```python
def test_search_resume_evidence_filters_by_user_run_candidate_and_type():
    client = FakeMilvusClient()
    store = MilvusRagStore(client=client, embedding_client=FakeEmbedding())

    store.search_resume_evidence(
        user_id=7,
        run_id=11,
        candidate_id=13,
        query="Milvus RAG",
        top_k=4,
    )

    expr = client.search_calls[0]["filter"]
    assert "user_id == 7" in expr
    assert "run_id == 11" in expr
    assert "candidate_id == 13" in expr
    assert 'document_type == "resume"' in expr


def test_delete_document_chunks_filters_by_user_and_document():
    store = MilvusRagStore(client=client, embedding_client=FakeEmbedding())
    store.delete_document(user_id=7, document_type="resume", document_id=21)
    assert "user_id == 7" in client.delete_calls[0]["filter"]
    assert "document_id == 21" in client.delete_calls[0]["filter"]
```

- [ ] **Step 2: Run RAG tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_rag_filters.py -q
```

Expected: signature/filter assertion failures.

- [ ] **Step 3: Replace OpenAI-only embedding with the existing embedding service adapter**

In `backend/rag/milvus.py`, define:

```python
class EmbeddingAdapter:
    def embed(self, text: str) -> list[float]:
        return embedding_service.embed(text)
```

Create Milvus schemas lazily from `len(first_vector)`. Add `user_id`, integer
`document_id`, integer `run_id`, and integer `candidate_id` fields. Update:

```python
def index_chunks(self, *, user_id: int, document_id: int, chunks: list[DocumentChunk]) -> None: ...
def search_resume_evidence(self, *, user_id: int, run_id: int, candidate_id: int, query: str, top_k: int = 4) -> list[EvidenceChunk]: ...
def persist_artifact(self, *, user_id: int, run_id: int, candidate_id: int, artifact_type: str, summary: str, content: dict) -> None: ...
def delete_document(self, *, user_id: int, document_type: str, document_id: int) -> None: ...
def delete_candidate_artifacts(self, *, user_id: int, run_id: int, candidate_id: int) -> None: ...
```

- [ ] **Step 4: Run RAG and vector profile tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_rag_filters.py backend/tests/test_vector_profile_text.py -q
```

Expected: all tests pass without `EMBEDDING_DIMENSION`.

- [ ] **Step 5: Commit unified RAG**

```powershell
git add backend/vector/embedding.py backend/rag/milvus.py backend/services/documents.py backend/tests/test_rag_filters.py
git commit -m "feat: unify user-scoped Milvus RAG"
```

---

### Task 5: Replace Document Parsing API With Authenticated Persistence

**Files:**
- Modify: `backend/routes/documents.py`
- Modify: `backend/schemas/workflow.py`
- Modify: `backend/schemas/__init__.py`
- Create: `backend/repositories/documents.py`
- Create: `backend/tests/test_documents_api.py`

- [ ] **Step 1: Write failing authenticated document API tests**

Cover upload, list, detail, reparse, delete, and ownership:

```python
def test_uploaded_resume_is_persisted_and_listed(client, auth_headers, fake_harness, fake_rag):
    response = client.post(
        "/api/documents",
        headers=auth_headers,
        data={"document_type": "resume"},
        files=[("files", ("real.txt", b"Real Candidate Python Milvus", "text/plain"))],
    )
    assert response.status_code == 200
    document = response.json()["documents"][0]
    assert document["raw_text"].startswith("Real Candidate")
    assert document["local_stored"] is True

    listed = client.get("/api/documents", headers=auth_headers).json()
    assert listed[0]["id"] == document["id"]


def test_user_cannot_read_another_users_document(client, other_auth_headers, persisted_document):
    response = client.get(f"/api/documents/{persisted_document.id}", headers=other_auth_headers)
    assert response.status_code == 404
```

Use dependency overrides/fakes for LLM and Milvus; assertions must inspect the
uploaded text passed into those fakes.

- [ ] **Step 2: Run API tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_documents_api.py -q
```

Expected: unauthorized/current non-persistent route behavior fails assertions.

- [ ] **Step 3: Implement document repository and authenticated APIs**

Use:

```python
router = APIRouter(prefix="/api/documents", tags=["documents"])

@router.post("", response_model=DocumentParseResponse)
async def upload_documents(
    document_type: DocumentType = Form(...),
    files: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
): ...

@router.get("", response_model=list[DocumentParseResult])
async def list_documents(...): ...

@router.get("/{document_id}", response_model=DocumentParseResult)
async def get_document(document_id: str, ...): ...

@router.post("/{document_id}/parse", response_model=DocumentParseResult)
async def reparse_document(document_id: str, ...): ...

@router.delete("/{document_id}")
async def delete_document(document_id: str, ...): ...
```

Represent IDs as `"jd:<id>"` and `"resume:<id>"` at the API boundary so the two
existing tables remain usable without introducing an unnecessary generic
document table. Repository parsing must reject malformed IDs and always filter
by `user_id`.

On upload: store/extract, run `AgentHarness`, save the database row, chunk with
durable IDs, index in Milvus, then commit. On failure: roll back and delete the
stored file and inserted vectors.

- [ ] **Step 4: Run document API and service tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_documents_api.py backend/tests/test_document_service.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit persisted document APIs**

```powershell
git add backend/routes/documents.py backend/repositories/documents.py backend/schemas/workflow.py backend/schemas/__init__.py backend/tests/test_documents_api.py
git commit -m "feat: persist authenticated document uploads"
```

---

### Task 6: Replace In-Memory Runs With PostgreSQL Repository

**Files:**
- Modify: `backend/repositories/runs.py`
- Modify: `backend/schemas/workflow.py`
- Create: `backend/tests/test_persistent_runs.py`

- [ ] **Step 1: Write failing repository tests across sessions**

Add:

```python
def test_report_survives_new_database_session(session_factory, persisted_job_graph):
    first = session_factory()
    repository = SqlAlchemyRunRepository(first)
    repository.save_report(user_id=1, job=persisted_job_graph.job, candidate=persisted_job_graph.candidate, report=REPORT)
    first.close()

    second = session_factory()
    loaded = SqlAlchemyRunRepository(second).get_candidate_report(
        user_id=1,
        run_id=persisted_job_graph.job.id,
        candidate_id=persisted_job_graph.candidate.id,
    )
    assert loaded.candidate_name == REPORT.candidate_name
    assert loaded.evaluations == REPORT.evaluations


def test_repository_does_not_return_other_users_run(...):
    assert repository.get_run(user_id=2, run_id=user_one_job.id) is None
```

- [ ] **Step 2: Run repository tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_persistent_runs.py -q
```

Expected: `SqlAlchemyRunRepository` missing.

- [ ] **Step 3: Implement SQLAlchemy run repository**

Expose:

```python
class SqlAlchemyRunRepository:
    def __init__(self, db: Session) -> None: ...
    def create_run(self, *, user_id: int, jd: JobDescription, resumes: list[Resume]) -> AnalysisJob: ...
    def list_runs(self, *, user_id: int) -> list[RunSummary]: ...
    def get_run(self, *, user_id: int, run_id: int) -> RunSummary | None: ...
    def save_report(self, *, user_id: int, job: AnalysisJob, candidate: AnalysisCandidate, report: CandidateReport) -> None: ...
    def mark_candidate_failed(self, *, user_id: int, candidate: AnalysisCandidate, detail: str) -> None: ...
    def get_candidate_report(self, *, user_id: int, run_id: int, candidate_id: int) -> CandidateReport | None: ...
    def delete_candidate(self, *, user_id: int, run_id: int, candidate_id: int) -> bool: ...
```

`save_report` writes `MatchResult.report_json`, normalized score fields,
`InterviewQuestionSet.questions`, and `FollowUpQuestionSet.questions` in one
transaction. It must update candidate and job status.

- [ ] **Step 4: Run repository tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_persistent_runs.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit persistent run repository**

```powershell
git add backend/repositories/runs.py backend/schemas/workflow.py backend/tests/test_persistent_runs.py
git commit -m "feat: persist LangGraph run reports"
```

---

### Task 7: Adapt LangGraph To Durable IDs And Persistence

**Files:**
- Modify: `backend/graph/candidate_workflow.py`
- Modify: `backend/services/analysis.py`
- Modify: `backend/tests/test_workflow_scoring.py`
- Create: `backend/tests/test_analysis_service.py`

- [ ] **Step 1: Write failing analysis-service test that proves database content enters the graph**

Add:

```python
def test_analysis_uses_persisted_documents_not_uploaded_files(db_session, user, persisted_jd, persisted_resume):
    harness = RecordingHarness()
    rag = RecordingRagStore()
    service = AnalysisService(db=db_session, harness=harness, rag_store=rag)

    summary = service.analyze_document_ids(
        user_id=user.id,
        jd_document_id=f"jd:{persisted_jd.id}",
        resume_document_ids=[f"resume:{persisted_resume.id}"],
    )

    assert summary.candidates[0].candidate_name == "Real Candidate"
    assert "REAL JD DATABASE TEXT" in harness.rendered_inputs["parse_jd"]
    assert "REAL RESUME DATABASE TEXT" in harness.rendered_inputs["parse_resume"]
    assert rag.search_calls[0]["user_id"] == user.id
```

Also test that a missing/foreign document ID is rejected before graph execution.

- [ ] **Step 2: Run analysis-service tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_analysis_service.py -q
```

Expected: ID-based service interface is missing.

- [ ] **Step 3: Update graph state and analysis service**

Use integer durable IDs:

```python
class CandidateState(TypedDict, total=False):
    user_id: int
    run_id: int
    candidate_id: int
    jd_document_id: int
    resume_document_id: int
    filename: str
    jd_chunks: list[DocumentChunk]
    resume_chunks: list[DocumentChunk]
    # existing profile/evaluation/report fields remain
```

`AnalysisService.analyze_document_ids` validates ownership, creates the persisted
run and candidate rows, rebuilds chunks from stored `raw_text` with durable IDs,
invokes the graph per candidate, and marks individual failures. The graph's
index/retrieve/persist nodes pass `user_id`, integer run ID, and integer candidate
ID into the RAG store and SQLAlchemy repository.

- [ ] **Step 4: Run graph and service tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_analysis_service.py backend/tests/test_workflow_scoring.py backend/tests/test_rag_filters.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit durable LangGraph workflow**

```powershell
git add backend/graph/candidate_workflow.py backend/services/analysis.py backend/tests/test_analysis_service.py backend/tests/test_workflow_scoring.py
git commit -m "feat: run LangGraph analysis from persisted documents"
```

---

### Task 8: Replace Run Routes With Authenticated ID-Based APIs

**Files:**
- Modify: `backend/routes/runs.py`
- Modify: `backend/schemas/workflow.py`
- Create: `backend/tests/test_runs_api.py`

- [ ] **Step 1: Write failing run API tests**

Add:

```python
def test_create_run_accepts_document_ids_not_files(client, auth_headers, persisted_documents, fake_analysis_service):
    response = client.post(
        "/api/runs",
        headers=auth_headers,
        json={
            "jd_document_id": persisted_documents.jd_api_id,
            "resume_document_ids": [persisted_documents.resume_api_id],
        },
    )
    assert response.status_code == 200
    assert fake_analysis_service.calls[0]["jd_document_id"] == persisted_documents.jd_api_id


def test_run_and_report_can_be_loaded_after_creation(client, auth_headers, persisted_run):
    assert client.get("/api/runs", headers=auth_headers).status_code == 200
    assert client.get(f"/api/runs/{persisted_run.id}", headers=auth_headers).status_code == 200
    assert client.get(
        f"/api/runs/{persisted_run.id}/candidates/{persisted_run.candidate_id}",
        headers=auth_headers,
    ).status_code == 200


def test_old_multipart_analyze_route_is_removed(client, auth_headers):
    response = client.post("/api/runs/analyze", headers=auth_headers)
    assert response.status_code == 404
```

- [ ] **Step 2: Run route tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_runs_api.py -q
```

Expected: ID-based route/list/delete behavior is missing.

- [ ] **Step 3: Implement authenticated routes**

Add:

```python
@router.post("", response_model=AnalyzeResponse)
async def create_run(request: AnalyzeRequest, current_user=Depends(get_current_user), db=Depends(get_db)): ...

@router.get("", response_model=list[RunSummary])
async def list_runs(...): ...

@router.get("/{run_id}", response_model=RunSummary)
async def get_run(run_id: int, ...): ...

@router.get("/{run_id}/candidates/{candidate_id}", response_model=CandidateReport)
async def get_candidate_report(run_id: int, candidate_id: int, ...): ...

@router.delete("/{run_id}/candidates/{candidate_id}")
async def delete_candidate_report(run_id: int, candidate_id: int, ...): ...

@router.post("/{run_id}/candidates/{candidate_id}/evidence/search", response_model=EvidenceSearchResponse)
async def search_candidate_evidence(run_id: int, candidate_id: int, request: EvidenceSearchRequest, ...): ...
```

Every route filters by authenticated ownership. Candidate deletion removes
database records and related Milvus artifacts.

- [ ] **Step 4: Run run API tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_runs_api.py backend/tests/test_persistent_runs.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit persisted run APIs**

```powershell
git add backend/routes/runs.py backend/schemas/workflow.py backend/tests/test_runs_api.py
git commit -m "feat: expose persisted ID-based run APIs"
```

---

### Task 9: Migrate Frontend Documents To Persisted APIs

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/src/api/documents.ts`
- Modify: `frontend/src/stores/document.ts`
- Modify: `frontend/src/types/document.ts`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/stores/document.test.ts`

- [ ] **Step 1: Add the frontend test runner**

Run:

```powershell
npm install --save-dev vitest@^3.2.0 jsdom@^26.1.0
```

Workdir: `frontend`

Add the script:

```json
{
  "scripts": {
    "test": "vitest"
  }
}
```

Add to `frontend/vite.config.ts`:

```typescript
test: {
  environment: 'jsdom',
  setupFiles: ['./src/test/setup.ts'],
  clearMocks: true,
},
```

Create `frontend/src/test/setup.ts`:

```typescript
import { afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

afterEach(() => {
  setActivePinia(createPinia())
})
```

- [ ] **Step 2: Write failing document-store tests**

Add tests with mocked API functions:

```typescript
it('loads persisted documents from the backend', async () => {
  vi.mocked(fetchDocumentsApi).mockResolvedValue([persistedResume])
  const store = useDocumentStore()
  await store.loadDocuments()
  expect(store.documents).toEqual([persistedResume])
})

it('uploads a resume once and keeps the durable backend id', async () => {
  vi.mocked(uploadDocumentsApi).mockResolvedValue({ documents: [persistedResume] })
  const store = useDocumentStore()
  await store.uploadDocuments('resume', [new File(['REAL RESUME'], 'real.txt')])
  expect(store.documents[0].id).toBe('resume:21')
  expect(uploadDocumentsApi).toHaveBeenCalledTimes(1)
})
```

- [ ] **Step 3: Run frontend tests to verify they fail**

Run:

```powershell
npm test -- --run src/stores/document.test.ts
```

Workdir: `frontend`

Expected: failures because loading is a no-op and upload uses split legacy APIs.

- [ ] **Step 4: Implement persisted document API/store**

Replace split upload functions with:

```typescript
export function uploadDocumentsApi(formData: FormData) {
  return request.post<ParseDocumentsResponse, ParseDocumentsResponse>('/documents', formData)
}

export function fetchDocumentsApi() {
  return request.get<DocumentRecord[], DocumentRecord[]>('/documents')
}

export function reparseDocumentApi(id: string) {
  return request.post<DocumentRecord, DocumentRecord>(`/documents/${id}/parse`)
}
```

Delete `documentFiles` and `getDocumentFile`. `loadDocuments`, `uploadDocuments`,
`reparseDocument`, and `deleteDocument` must all call the backend and replace
state from returned durable records.

- [ ] **Step 5: Run document-store tests and frontend typecheck/build**

Run:

```powershell
npm test -- --run src/stores/document.test.ts
npm run build
```

Workdir: `frontend`

Expected: test and build pass.

- [ ] **Step 6: Commit frontend persisted documents**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/src/test/setup.ts frontend/src/api/documents.ts frontend/src/stores/document.ts frontend/src/types/document.ts frontend/src/stores/document.test.ts
git commit -m "feat: load persisted documents in frontend"
```

---

### Task 10: Migrate Frontend Matches And Questions To Persisted Runs

**Files:**
- Modify: `frontend/src/api/runs.ts`
- Modify: `frontend/src/stores/match.ts`
- Modify: `frontend/src/stores/question.ts`
- Modify: `frontend/src/types/run.ts`
- Create: `frontend/src/api/runs.test.ts`
- Create: `frontend/src/stores/match.test.ts`

- [ ] **Step 1: Write failing ID-based run and reload tests**

Add:

```typescript
it('creates a run with durable document ids and no FormData', async () => {
  await createRunApi({ jd_document_id: 'jd:4', resume_document_ids: ['resume:9'] })
  expect(request.post).toHaveBeenCalledWith('/runs', {
    jd_document_id: 'jd:4',
    resume_document_ids: ['resume:9'],
  })
})

it('loads persisted runs and reports after store creation', async () => {
  vi.mocked(fetchRunsApi).mockResolvedValue([persistedRun])
  vi.mocked(fetchCandidateReportApi).mockResolvedValue(persistedReport)
  const store = useMatchStore()
  await store.loadMatches()
  expect(store.results[0].candidateName).toBe('Real Candidate')
})
```

- [ ] **Step 2: Run focused frontend tests to verify they fail**

Run:

```powershell
npm test -- --run src/api/runs.test.ts src/stores/match.test.ts
```

Workdir: `frontend`

Expected: FormData/re-upload and no-op load behavior fails.

- [ ] **Step 3: Implement ID-based run creation and persisted loading**

Use:

```typescript
export interface CreateRunPayload {
  jd_document_id: string
  resume_document_ids: string[]
}

export function createRunApi(payload: CreateRunPayload) {
  return request.post<RunSummary, RunSummary>('/runs', payload)
}

export function fetchRunsApi() {
  return request.get<RunSummary[], RunSummary[]>('/runs')
}
```

`match.ts` sends selected durable IDs, loads run summaries and candidate reports,
and calls backend deletion. `question.ts` uses an existing persisted candidate
report or creates a single-candidate ID-based run; it never reads browser files.

- [ ] **Step 4: Run frontend tests and build**

Run:

```powershell
npm test -- --run src/api/runs.test.ts src/stores/match.test.ts src/stores/document.test.ts
npm run build
```

Workdir: `frontend`

Expected: all focused tests and build pass.

- [ ] **Step 5: Commit frontend persisted analysis**

```powershell
git add frontend/src/api/runs.ts frontend/src/stores/match.ts frontend/src/stores/question.ts frontend/src/types/run.ts frontend/src/api/runs.test.ts frontend/src/stores/match.test.ts
git commit -m "feat: use persisted LangGraph runs in frontend"
```

---

### Task 11: Remove Legacy Routes And Duplicate Demo Implementations

**Files:**
- Modify: `backend/routes/api.py`
- Modify: `backend/schemas/__init__.py`
- Modify: `README.md`
- Delete: `backend/routes/resume.py`
- Delete: `backend/routes/jd.py`
- Delete: `backend/routes/analysis.py`
- Delete: `backend/schemas/demo.py`
- Delete: `backend/services/demo_documents.py`
- Delete: `backend/services/demo_analysis.py`
- Delete: `backend/graph/demo_workflow.py`
- Delete: `backend/rag/demo_embedding.py`
- Delete: `backend/rag/demo_milvus.py`
- Delete: `backend/repositories/demo_runs.py`
- Delete: `backend/services/resume_upload.py`
- Create: `backend/tests/test_legacy_routes_removed.py`

- [ ] **Step 1: Write failing legacy-removal and import-scan tests**

Add:

```python
@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/resume/upload"),
        ("get", "/resume"),
        ("post", "/jd/upload"),
        ("get", "/jd"),
        ("post", "/analysis/jobs"),
        ("post", "/api/runs/analyze"),
    ],
)
def test_legacy_routes_are_removed(client, method, path):
    assert getattr(client, method)(path).status_code == 404
```

Also run an import scan:

```powershell
rg -n "demo_|backend\.routes\.(resume|jd|analysis)|resume_upload" backend frontend/src
```

Expected before removal: matches remain.

- [ ] **Step 2: Remove legacy router registration and duplicate files**

`backend/routes/api.py` must register:

```python
router.include_router(chat_router)
router.include_router(runs_router)
router.include_router(documents_router)
```

Keep authentication endpoints in the same module. Delete the listed duplicate
files only after all production imports have been migrated.

- [ ] **Step 3: Update README and environment documentation**

Document only:

```text
POST/GET /api/documents
GET/POST/DELETE /api/documents/{id}
POST/GET /api/runs
GET /api/runs/{run_id}
GET/DELETE /api/runs/{run_id}/candidates/{candidate_id}
POST /api/runs/{run_id}/candidates/{candidate_id}/evidence/search
```

Remove `EMBEDDING_DIMENSION` from required configuration and describe local
embedding plus Milvus requirements.

- [ ] **Step 4: Run removal tests and verify no active demo imports**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_legacy_routes_removed.py -q
rg -n "demo_|backend\.routes\.(resume|jd|analysis)|resume_upload" backend frontend/src
```

Expected: route tests pass; `rg` returns no active-code matches.

- [ ] **Step 5: Commit legacy removal**

```powershell
git add backend frontend/src README.md .env.example
git commit -m "refactor: remove legacy upload and analysis architecture"
```

---

### Task 12: Full Verification And Runtime Smoke Test

**Files:**
- Modify only files required by failures found during verification.

- [ ] **Step 1: Run the complete backend test suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

Expected: zero failures.

- [ ] **Step 2: Run the complete frontend tests and production build**

Run:

```powershell
npm test -- --run
npm run build
```

Workdir: `frontend`

Expected: zero test failures and successful build.

- [ ] **Step 3: Start backend and frontend for local smoke testing**

Run backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Run frontend:

```powershell
npm run dev -- --host 127.0.0.1
```

Workdir: `frontend`

Expected: backend API at `http://127.0.0.1:8000/docs` and frontend at the Vite
URL shown in output.

- [ ] **Step 4: Exercise the real persisted workflow**

Verify through API/browser:

1. Log in.
2. Upload a text PDF/Word resume and JD.
3. Upload a scanned PDF and confirm OCR-produced content appears.
4. Refresh and confirm documents remain.
5. Run a match by durable IDs.
6. Refresh and confirm match report/questions remain.
7. Search candidate evidence and confirm returned text belongs to that resume.
8. Delete a candidate result and a document and confirm related API data is gone.
9. Confirm `/resume`, `/jd`, `/analysis`, and `/api/runs/analyze` return 404.

- [ ] **Step 5: Run final repository scans**

Run:

```powershell
rg -n "demo_|preset|sample data|documentFiles|getDocumentFile|/resume|/jd|/analysis|/runs/analyze" backend frontend/src README.md
git -c safe.directory='C:/Users/Zhu/Desktop/code/ResuMate-Agent' status --short
git -c safe.directory='C:/Users/Zhu/Desktop/code/ResuMate-Agent' diff --stat
```

Expected: no active duplicate architecture references; only intentional user
worktree changes plus this migration are present.

- [ ] **Step 6: Request code review and address findings**

Use the `requesting-code-review` skill with the design spec and this plan. Fix
all Critical and Important findings, then repeat the full backend tests, frontend
tests, and frontend build.

- [ ] **Step 7: Commit final verification fixes**

```powershell
git add backend frontend README.md .env.example
git commit -m "test: verify persistent LangGraph RAG workflow"
```
