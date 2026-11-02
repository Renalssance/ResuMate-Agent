# Chat Document Picker and Content Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the chat composer’s exposed selectors with a polished attachment picker and import local documents through a durable content-based Resume/JD classification flow that asks the user when the type remains ambiguous.

**Architecture:** Keep saved Resume/JD selection in a focused Vue picker component and keep upload orchestration in a small composable. The backend accepts a single local file into an internal-only `document_import` AgentRun, stores private file metadata in that Run, classifies extracted content without using the filename, pauses through the existing `AgentAction` mechanism when user judgment is required, and then reuses the existing parsing/indexing pipeline on the same stored original. No new database table or public `RunCreate` kind is introduced.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2, Celery worker, existing AgentHarness, Vue 3 Composition API, Pinia, TypeScript, Vitest, Vue Test Utils, Playwright

**Spec:** `docs/superpowers/specs/2026-10-31-chat-document-picker-auto-classification-design.md`

## Global Constraints

- Preserve the current ResuMate visual language, left navigation, floating composer geometry, colors, typography, borders, and glass treatment.
- The composer upload affordance is one icon-only paperclip button with accessible name `添加材料` and visible hover/focus feedback.
- The floating picker is horizontally centered above the paperclip with an 8px gap, closes on outside click or Escape, and uses opacity, 6px vertical movement, and scale from 0.96 to 1 over 180ms on entry and 140ms on exit.
- `prefers-reduced-motion: reduce` removes transform motion and keeps only a short opacity transition.
- The picker exposes exactly three primary choices: database Resume, database Job, and local file.
- A chosen Resume and a chosen Job appear in the composer as removable type-icon plus filename chips; one of each type can be active.
- Local document classification uses extracted content only. Do not pass the filename to local classification rules or the LLM classification prompt.
- Only a high-confidence `resume` or `jd` classification may continue automatically. Medium, low, or `ambiguous` results require user confirmation.
- Ambiguous classification must use the existing Run input action endpoint and continue the same stored original after the answer.
- Existing typed `POST /api/documents` behavior remains unchanged.
- `POST /api/documents/import` accepts exactly one file and an optional request id and never accepts a document type from the client.
- Do not add a database migration framework, compatibility wrapper, feature flag, or speculative validation layer.
- Use `apply_patch` for every repository edit and do not reset unrelated working-tree changes.

## File Map

- `backend/schemas/document_import.py`: classification and import response schemas.
- `backend/services/document_classifier.py`: pure structural content classifier and LLM fallback; its API accepts document text, never a filename.
- `backend/prompts/classify_document.md`: constrained Resume/JD/ambiguous classifier prompt.
- `backend/services/document_imports.py`: internal Run creation, action creation/answer reading, typed-row adoption, cleanup, and import execution.
- `backend/routes/documents.py`: new `/import` route; existing typed route is retained.
- `backend/services/agent_runs.py`: safe public input, import source guarding, retry/cancel/recovery cleanup, and action resume support.
- `backend/worker_tasks.py`: dispatch `document_import` Runs.
- `backend/services/document_tasks.py`: expose one shared parse/index/save function used by typed uploads and imports.
- `frontend/src/api/documentImports.ts`: import upload and type-confirmation API.
- `frontend/src/composables/useDocumentImport.ts`: subscribe to an import Run, expose waiting confirmation, and return the parsed document.
- `frontend/src/components/chat/ChatMaterialPicker.vue`: icon button, floating three-choice panel, saved-document buttons, local file input, chips, motion, and dismissal.
- `frontend/src/views/ChatView.vue`: replace the two selects and old upload menu, preserve selected context IDs, and add imported documents to the store.
- Backend, component, view, and browser tests verify the full contract.

---

### Task 1: Content-only Document Classifier

**Files:**
- Create: `backend/schemas/document_import.py`
- Create: `backend/services/document_classifier.py`
- Create: `backend/prompts/classify_document.md`
- Create: `backend/tests/test_document_classifier.py`

**Interfaces:**
- Consumes: `AgentHarness.run_schema(...)` and extracted plain text.
- Produces: `DocumentClassification`, `classify_document_content(text: str) -> DocumentClassification | None`, and `classify_document(text: str, *, user_id: int, guard=None, progress_callback=None) -> DocumentClassification`.

- [ ] **Step 1: Write failing schema and structural-classifier tests**

```python
from backend.schemas.document_import import DocumentClassification
from backend.services.document_classifier import classify_document_content


def test_resume_structure_is_classified_without_filename():
    text = """教育经历\n清华大学 计算机硕士\n工作经历\n模型评测工程师\n项目经历\n构建 VLM 评测平台"""
    assert classify_document_content(text) == DocumentClassification(
        document_type="resume", confidence="high", reason="检测到教育、工作和项目经历结构"
    )


def test_job_structure_is_classified_without_filename():
    text = """岗位职责\n负责大模型评测平台建设\n任职要求\n熟悉 Python 和 Pytest\n加分项\n具备 Agent 工程经验"""
    assert classify_document_content(text) == DocumentClassification(
        document_type="jd", confidence="high", reason="检测到岗位职责、任职要求和加分项结构"
    )


def test_mixed_or_unstructured_content_defers_to_model():
    assert classify_document_content("我们希望找到合适的人，一起建设模型评测系统。") is None
    assert classify_document_content("工作经历\n任职要求\n熟悉 Python") is None
```

- [ ] **Step 2: Run the tests and confirm the new modules are missing**

Run: `pytest -q backend/tests/test_document_classifier.py`

Expected: collection fails because `backend.schemas.document_import` does not exist.

- [ ] **Step 3: Add the strict classification schema and conservative structural rules**

```python
# backend/schemas/document_import.py
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class DocumentClassification(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    document_type: Literal["resume", "jd", "ambiguous"]
    confidence: Literal["high", "medium", "low"]
    reason: str = Field(min_length=1, max_length=160)
```

```python
# backend/services/document_classifier.py
import re
from backend.agents.harness import AgentHarness
from backend.schemas.document_import import DocumentClassification

RESUME_SECTIONS = {
    "教育": re.compile(r"^(教育经历|教育背景|education)$", re.I),
    "工作": re.compile(r"^(工作经历|实习经历|职业经历|work experience|experience)$", re.I),
    "项目": re.compile(r"^(项目经历|项目经验|projects?)$", re.I),
    "技能": re.compile(r"^(专业技能|技能清单|技术能力|skills?)$", re.I),
    "成果": re.compile(r"^(论文发表|研究成果|荣誉奖项|publications?|awards?)$", re.I),
}
JD_SECTIONS = {
    "职责": re.compile(r"^(岗位职责|职位职责|工作职责|responsibilities)$", re.I),
    "要求": re.compile(r"^(任职要求|职位要求|岗位要求|requirements|qualifications)$", re.I),
    "加分": re.compile(r"^(加分项|优先条件|preferred qualifications)$", re.I),
    "福利": re.compile(r"^(薪酬福利|员工福利|benefits?)$", re.I),
    "地点": re.compile(r"^(工作地点|办公地点|workplace|location)$", re.I),
}


def _matched_sections(text: str, patterns: dict[str, re.Pattern[str]]) -> list[str]:
    lines = [re.sub(r"[：:]$", "", line.strip()) for line in text.splitlines() if line.strip()]
    return [label for label, pattern in patterns.items() if any(pattern.fullmatch(line) for line in lines)]


def classify_document_content(text: str) -> DocumentClassification | None:
    resume = _matched_sections(text, RESUME_SECTIONS)
    jd = _matched_sections(text, JD_SECTIONS)
    if len(resume) >= 2 and not jd:
        return DocumentClassification(document_type="resume", confidence="high",
            reason=f"检测到{'、'.join(resume)}经历结构")
    if len(jd) >= 2 and not resume:
        return DocumentClassification(document_type="jd", confidence="high",
            reason=f"检测到{'、'.join(jd)}结构")
    return None
```

- [ ] **Step 4: Add LLM fallback tests that prove filename independence and strict ambiguity handling**

```python
from backend.services import document_classifier


def test_fallback_sends_only_content_to_model(monkeypatch):
    captured = {}
    class Harness:
        def __init__(self, **_kwargs): pass
        def run_schema(self, **kwargs):
            captured.update(kwargs)
            return DocumentClassification(document_type="jd", confidence="medium", reason="信息不足")
    monkeypatch.setattr(document_classifier, "AgentHarness", Harness)
    result = document_classifier.classify_document("岗位相关说明", user_id=7)
    assert result.document_type == "jd"
    assert captured["variables"] == {"document_text": "岗位相关说明"}
    assert "filename" not in captured["variables"]


def test_high_confidence_structural_result_skips_model(monkeypatch):
    monkeypatch.setattr(document_classifier.AgentHarness, "run_schema",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("model must not run")))
    result = document_classifier.classify_document(
        "教育经历\n学校\n工作经历\n公司\n项目经历\n平台", user_id=7)
    assert result.document_type == "resume"
    assert result.confidence == "high"
```

- [ ] **Step 5: Implement the LLM fallback and the prompt**

```python
def classify_document(text: str, *, user_id: int, guard=None,
                      progress_callback=None) -> DocumentClassification:
    structural = classify_document_content(text)
    if structural is not None:
        return structural
    return AgentHarness(user_id=user_id, guard=guard,
        progress_callback=progress_callback).run_schema(
            task="document.classify",
            prompt_name="classify_document",
            schema=DocumentClassification,
            variables={"document_text": text[:24000]},
            progress_stage="classify",
            progress=35,
        )
```

```markdown
<!-- backend/prompts/classify_document.md -->
根据文档正文判断它是候选人简历、职位描述，还是无法可靠判断。

判断依据只能来自正文。不要推测文件名、扩展名或上传位置。
- resume：以个人教育、工作、项目、技能和成果为主体。
- jd：以岗位职责、任职要求、资格条件、加分项和招聘信息为主体。
- ambiguous：两类内容混合，或正文不足以可靠判断。

只有正文结构和主体都明确时才返回 high。证据不足时返回 medium、low 或 ambiguous。

正文：
{{document_text}}
```

- [ ] **Step 6: Run the focused classifier tests**

Run: `pytest -q backend/tests/test_document_classifier.py`

Expected: all tests pass.

- [ ] **Step 7: Commit the classifier**

```bash
git add backend/schemas/document_import.py backend/services/document_classifier.py backend/prompts/classify_document.md backend/tests/test_document_classifier.py
git commit -m "feat: classify imported documents by content"
```

---

### Task 2: Durable Internal Document Import Run

**Files:**
- Modify: `backend/schemas/document_import.py`
- Modify: `backend/routes/documents.py`
- Modify: `backend/services/agent_runs.py`
- Create: `backend/services/document_imports.py`
- Create: `backend/tests/test_document_import_routes.py`

**Interfaces:**
- Consumes: `StoredUpload`, `persisted_upload_path(stored)`, `cleanup_upload_cache(stored)`, AgentRun/AgentSession, and `publish_run(run_id)`.
- Produces: `DocumentImportAccepted`, `create_document_import_run(db, user_id, stored, request_id) -> AgentRun`, and `POST /api/documents/import`.

- [ ] **Step 1: Write route tests for one durable upload and idempotent request ids**

```python
def test_import_accepts_one_file_without_document_type(client, auth_headers, monkeypatch):
    published = []
    monkeypatch.setattr("backend.routes.documents.publish_run", published.append)
    response = client.post("/api/documents/import",
        files={"file": ("profile.txt", b"Education\nWork Experience\nProjects", "text/plain")},
        data={"requestId": "import-1"}, headers=auth_headers)
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["runId"] in published
    snapshot = client.get(f"/api/agent/runs/{body['runId']}", headers=auth_headers).json()
    assert snapshot["kind"] == "document_import"
    assert snapshot["input"] == {"filename": "profile.txt"}
    assert "sourcePath" not in snapshot["input"]


def test_import_request_id_reuses_run_and_does_not_store_second_original(client, auth_headers, monkeypatch):
    calls = []
    async def fake_store(file):
        calls.append(file)
        return stored_upload()
    monkeypatch.setattr("backend.routes.documents.store_upload", fake_store)
    first = post_import(client, auth_headers, request_id="same-import")
    second = post_import(client, auth_headers, request_id="same-import")
    assert second.json()["runId"] == first.json()["runId"]
    assert len(calls) == 1


def test_import_rejects_multiple_files(client, auth_headers):
    response = client.post("/api/documents/import", files=[
        ("file", ("a.txt", b"a", "text/plain")),
        ("file", ("b.txt", b"b", "text/plain")),
    ], headers=auth_headers)
    assert response.status_code == 422
```

- [ ] **Step 2: Run the route tests and confirm `/import` is absent**

Run: `pytest -q backend/tests/test_document_import_routes.py -k 'accepts or reuses or multiple'`

Expected: the tests fail with a 404 response.

- [ ] **Step 3: Add safe response schemas and internal Run creation**

```python
# backend/schemas/document_import.py
from backend.schemas.agent_runs import RunStatus


class DocumentImportAccepted(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    run_id: str = Field(alias="runId")
    status: RunStatus
```

```python
# backend/services/document_imports.py
from uuid import uuid4
from backend.db.agent_models import AgentRun, AgentSession
from backend.services.agent_runs import RunError, _claim_session
from backend.services.documents import StoredUpload, persisted_upload_path
from backend.services.run_events import append_event


def create_document_import_run(db, user_id: int, stored: StoredUpload,
                               request_id: str) -> AgentRun:
    existing = db.scalar(select(AgentRun).where(
        AgentRun.user_id == user_id, AgentRun.request_id == request_id))
    if existing is not None:
        if existing.kind != "document_import":
            raise RunError(409, "request_conflict", "该 requestId 已用于另一项请求")
        return existing
    session = AgentSession(id=str(uuid4()), user_id=user_id, purpose="document_import")
    run = AgentRun(id=str(uuid4()), user_id=user_id, session_id=session.id,
        request_id=request_id, kind="document_import", input_json={
            "filename": stored.filename,
            "sourcePath": persisted_upload_path(stored),
            "contentHash": stored.content_hash,
            "documentSize": stored.size,
        }, input_versions={})
    db.add(session); db.flush(); db.add(run); db.flush()
    _claim_session(db, user_id, session.id, run.id, kind=run.kind)
    append_event(db, run.id, "run.status", {"status": run.status})
    return run
```

The implementation may move `_claim_session` to a non-private name because it becomes shared service code; update its callers in the same patch rather than importing a private function.

- [ ] **Step 4: Add safe public input and import Run visibility**

In `backend/services/agent_runs.py`, extend `_public_input` and non-artifact behavior without exposing private metadata:

```python
keys = {
    # existing mappings
    "document_import": ("filename",),
}.get(run.kind, ())
```

Include `document_import` in the kinds that return no artifacts. Do not add `document_import` to the public `RunCreate` Pydantic literal or `/api/agent/runs` POST contract.

- [ ] **Step 5: Add the upload route with pre-store idempotency and cleanup**

```python
@router.post("/import", response_model=DocumentImportAccepted,
             status_code=202, dependencies=[Depends(require_run_capacity)])
def import_document(file: list[UploadFile] = File(...), request_id: str = Form("", alias="requestId"),
                    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if len(file) != 1:
        raise HTTPException(status_code=422, detail="exactly one file is required")
    key = request_id or str(uuid4())
    existing = find_document_import_run(db, current_user.id, key)
    if existing is not None:
        return DocumentImportAccepted(runId=existing.id, status=existing.status)
    stored = None
    try:
        stored = anyio.from_thread.run(store_upload, file[0])
        run = create_document_import_run(db, current_user.id, stored, key)
        db.commit()
        publish_run(run.id)
        return DocumentImportAccepted(runId=run.id, status=run.status)
    except Exception:
        db.rollback()
        if stored is not None:
            delete_stored_file(persisted_upload_path(stored))
        raise
    finally:
        if stored is not None:
            cleanup_upload_cache(stored)
```

Implement `find_document_import_run(db, user_id, request_id)` in `document_imports.py` so the request id is checked before the upload stream is persisted and conflicts return `RunError(409, "request_conflict", ...)`.

- [ ] **Step 6: Run route and existing upload tests**

Run: `pytest -q backend/tests/test_document_import_routes.py backend/tests/test_document_cloud_routes.py`

Expected: the new route tests pass and typed `/api/documents` tests remain green.

- [ ] **Step 7: Commit durable import acceptance**

```bash
git add backend/schemas/document_import.py backend/routes/documents.py backend/services/agent_runs.py backend/services/document_imports.py backend/tests/test_document_import_routes.py
git commit -m "feat: accept durable document import runs"
```

---

### Task 3: Classify, Adopt, Parse, and Index the Same Original

**Files:**
- Modify: `backend/services/document_tasks.py`
- Modify: `backend/services/document_imports.py`
- Modify: `backend/services/document_process.py`
- Modify: `backend/services/agent_runs.py`
- Modify: `backend/worker_tasks.py`
- Create: `backend/tests/test_document_import_tasks.py`

**Interfaces:**
- Consumes: `classify_document(...)`, `extract_stored_pages(...)`, `chunk_pages(...)`, `_parse_profile(...)`, existing Run fencing, RAG replacement, and document serialization.
- Produces: `parse_document_record(run_id, epoch, *, document_id, pages=None) -> dict`, `run_document_import(run_id, epoch) -> None`, and import worker dispatch.

- [ ] **Step 1: Write a worker test for automatic high-confidence Resume import**

```python
def test_high_confidence_import_adopts_and_parses_same_file(career_db, import_run, monkeypatch, tmp_path):
    source = tmp_path / "neutral.txt"
    source.write_text("教育经历\n学校\n工作经历\n公司\n项目经历\n平台", encoding="utf-8")
    import_run.input_json = {**import_run.input_json, "sourcePath": str(source), "filename": "neutral.txt"}
    career_db.commit()
    monkeypatch.setattr(document_imports, "classify_document",
        lambda *_args, **_kwargs: DocumentClassification(document_type="resume", confidence="high", reason="结构明确"))
    monkeypatch.setattr(document_tasks, "_parse_profile", lambda *_args, **_kwargs: valid_resume_profile())
    monkeypatch.setattr(document_tasks, "get_rag_store", lambda: fake_rag_store())

    document_imports.run_document_import(import_run.id, import_run.execution_epoch)

    career_db.expire_all()
    saved = career_db.scalar(select(Resume).where(Resume.user_id == import_run.user_id))
    run = career_db.get(AgentRun, import_run.id)
    assert saved.file_path == str(source)
    assert run.status == RunStatus.SUCCEEDED
    assert run.result_json["documents"][0]["id"] == f"resume:{saved.id}"
    assert run.input_json["documentId"] == f"resume:{saved.id}"
```

- [ ] **Step 2: Run the focused worker test and confirm the handler is missing**

Run: `pytest -q backend/tests/test_document_import_tasks.py::test_high_confidence_import_adopts_and_parses_same_file`

Expected: failure because `run_document_import` does not exist.

- [ ] **Step 3: Extract one shared parse/index/save function from `run_document_parse`**

Keep `run_document_parse` behavior and its result shape unchanged. Move its core after source lookup into:

```python
def parse_document_record(run_id: str, epoch: int, *, document_id: str,
                          pages: list[PageText] | None = None) -> dict:
    """Parse, index and persist one already-owned document under the current Run fence."""
```

The helper must:

1. Reuse supplied `pages` so an import does not extract the same file twice.
2. Build `raw_text` and chunks from those pages.
3. Reuse `_cached_structured_data` by content hash.
4. Call `_parse_profile`, replace RAG chunks, update structured data and parse status.
5. Return `DocumentParseResponse(documents=[...], taskId=run_id).model_dump(mode="json", by_alias=True)` without finishing the Run.

`run_document_parse` calls the helper, adds its existing operation/event, then calls `finish_run` exactly once.

- [ ] **Step 4: Implement atomic typed-row adoption before parsing**

```python
def adopt_import(db, run: AgentRun, document_type: Literal["resume", "jd"]):
    existing_id = run.input_json.get("documentId")
    if existing_id:
        return owned_import_document(db, run, existing_id)
    common = dict(user_id=run.user_id, filename=run.input_json["filename"],
        file_path=run.input_json["sourcePath"], content_hash=run.input_json["contentHash"],
        document_size=run.input_json["documentSize"], raw_text="", structured_data={},
        parse_status="running")
    row = Resume(**common) if document_type == "resume" else JobDescription(
        **common, title="待解析岗位", company="")
    db.add(row); db.flush()
    run.input_json = {**run.input_json, "documentId": f"{document_type}:{row.id}",
                      "detectedType": document_type}
    db.commit()
    return row
```

Persisting `documentId` before model parsing makes worker retry reuse the adopted row rather than create another row.

- [ ] **Step 5: Implement import execution and worker dispatch**

```python
def run_document_import(run_id: str, epoch: int) -> None:
    try:
        with SessionLocal() as db:
            run = guarded_import_run(db, run_id, epoch)
            pages = extract_stored_pages(run.input_json["sourcePath"], run.input_json["filename"])
            raw_text = "\n".join(page.text for page in pages).strip()
            classification = classify_document(raw_text, user_id=run.user_id,
                guard=lambda: guard_import(run_id, epoch))
            if classification.document_type == "ambiguous" or classification.confidence != "high":
                pause_for_document_type(db, run, epoch, classification)
                return
            row = adopt_import(db, run, classification.document_type)
        document_id = f"{classification.document_type}:{row.id}"
        result = parse_document_record(run_id, epoch, document_id=document_id, pages=pages)
        with SessionLocal() as db:
            finish_run(db, run_id, epoch, RunStatus.SUCCEEDED, result_json=result)
    except Exception as exc:
        with SessionLocal() as db:
            run = db.get(AgentRun, run_id)
            if run is not None and run.status == RunStatus.RUNNING and run.execution_epoch == epoch:
                finish_run(db, run_id, epoch, RunStatus.FAILED,
                    error_code=exc.code if isinstance(exc, RunError) else "document_import_failed")
```

Update `worker_tasks.execute_run`:

```python
elif kind == "document_import":
    from backend.services.document_process import run_document_import_process
    run_document_import_process(run_id, epoch)
```

Add `run_document_import_process` using the existing killable subprocess contract and make `document_process.main()` choose the handler from a third command argument (`document_parse` or `document_import`).

- [ ] **Step 6: Extend source guards and retry support**

In `require_task_sources`, accept an import before adoption by checking that `sourcePath` is present and, after adoption, lock the Resume/JD row referenced by `documentId`. In `retry_run`, permit failed `document_import` Runs while retaining the stored path and adopted document id. Extend `_mark_stopped_document` so a failed or cancelled import with `documentId` updates that owned Resume/JD row’s `parse_status`; an unadopted import has no typed row to update.

- [ ] **Step 7: Run the import, parse, and worker tests**

Run: `pytest -q backend/tests/test_document_import_tasks.py backend/tests/test_document_tasks.py backend/tests/test_worker_delivery.py`

Expected: all tests pass, including existing typed document parsing.

- [ ] **Step 8: Commit import execution**

```bash
git add backend/services/document_tasks.py backend/services/document_imports.py backend/services/document_process.py backend/services/agent_runs.py backend/worker_tasks.py backend/tests/test_document_import_tasks.py
git commit -m "feat: parse classified imports from one original"
```

---

### Task 4: Ambiguous Type Confirmation and Original Cleanup

**Files:**
- Modify: `backend/services/document_imports.py`
- Modify: `backend/services/agent_runs.py`
- Modify: `backend/tests/test_document_import_tasks.py`
- Modify: `backend/tests/test_agent_run_routes.py`

**Interfaces:**
- Consumes: `AgentAction`, `answer_action`, `finish_run(..., WAITING_INPUT)`, Run cancellation/recovery.
- Produces: `pause_for_document_type(...)`, `answered_document_type(db, run) -> Literal["resume", "jd"] | None`, and cleanup for unadopted terminal imports.

- [ ] **Step 1: Write a test for the waiting-input action payload**

```python
def test_ambiguous_import_waits_for_user_type(career_db, running_import, monkeypatch):
    monkeypatch.setattr(document_imports, "classify_document",
        lambda *_args, **_kwargs: DocumentClassification(
            document_type="ambiguous", confidence="low", reason="正文同时包含候选人和岗位内容"))
    document_imports.run_document_import(running_import.id, running_import.execution_epoch)
    career_db.expire_all()
    run = career_db.get(AgentRun, running_import.id)
    action = career_db.scalar(select(AgentAction).where(AgentAction.run_id == run.id))
    assert run.status == RunStatus.WAITING_INPUT
    assert action.kind == "input"
    assert action.payload == {
        "question": "这份文件属于哪一类？",
        "filename": "neutral.txt",
        "reason": "正文同时包含候选人和岗位内容",
        "choices": [
            {"value": "resume", "label": "简历"},
            {"value": "jd", "label": "岗位"},
        ],
    }
```

- [ ] **Step 2: Write route tests for answering and resuming the same Run**

```python
def test_document_type_answer_requeues_same_import(client, auth_headers, waiting_import, action):
    response = client.post(
        f"/api/agent/runs/{waiting_import.id}/actions/{action.id}",
        json={"decision": "submit", "answers": {"documentType": "resume"}, "expectedRevision": 1},
        headers=auth_headers,
    )
    assert response.status_code == 202
    assert response.json() == {"runId": waiting_import.id, "status": "queued"}
```

- [ ] **Step 3: Run the confirmation tests and observe missing action behavior**

Run: `pytest -q backend/tests/test_document_import_tasks.py -k ambiguous backend/tests/test_agent_run_routes.py -k document_type`

Expected: failures because no document-type action is created or consumed.

- [ ] **Step 4: Implement one stable action and consume its validated answer**

```python
DOCUMENT_TYPE_INTERRUPT_ID = "document-type"


def pause_for_document_type(db, run: AgentRun, epoch: int,
                            classification: DocumentClassification) -> None:
    action = db.scalar(select(AgentAction).where(
        AgentAction.run_id == run.id,
        AgentAction.interrupt_id == DOCUMENT_TYPE_INTERRUPT_ID))
    if action is None:
        action = AgentAction(run_id=run.id, interrupt_id=DOCUMENT_TYPE_INTERRUPT_ID,
            kind="input", payload={
                "question": "这份文件属于哪一类？",
                "filename": run.input_json["filename"],
                "reason": classification.reason,
                "choices": [
                    {"value": "resume", "label": "简历"},
                    {"value": "jd", "label": "岗位"},
                ],
            })
        db.add(action); db.flush()
        append_event(db, run.id, "action.required", {"action_id": action.id, "kind": "input"})
    finish_run(db, run.id, epoch, RunStatus.WAITING_INPUT)


def answered_document_type(db, run: AgentRun) -> Literal["resume", "jd"] | None:
    action = db.scalar(select(AgentAction).where(
        AgentAction.run_id == run.id,
        AgentAction.interrupt_id == DOCUMENT_TYPE_INTERRUPT_ID,
        AgentAction.status == "answered"))
    value = (action.response or {}).get("answers", {}).get("documentType") if action else None
    if value not in ("resume", "jd"):
        return None
    return value
```

At the start of resumed execution, use `answered_document_type` before extracting/classifying again. An answered type is user authority and proceeds directly to `adopt_import` with the existing source path.

- [ ] **Step 5: Validate the document-type action answer in `answer_action`**

Before marking this specific action answered, reject values outside `resume` and `jd` with `RunError(422, "invalid_action_answer", "请选择简历或岗位")`. Leave generic action behavior unchanged.

- [ ] **Step 6: Write and implement cleanup tests**

```python
def test_cancelling_unadopted_import_deletes_original(career_db, waiting_import, tmp_path):
    source = tmp_path / "staged.txt"; source.write_text("content")
    waiting_import.input_json = {**waiting_import.input_json, "sourcePath": str(source)}
    career_db.commit()
    cancel_run(career_db, waiting_import.user_id, waiting_import.id)
    assert not source.exists()


def test_cancelling_adopted_import_keeps_document_original(career_db, waiting_import, resume, tmp_path):
    source = tmp_path / "owned.txt"; source.write_text("content")
    resume.file_path = str(source)
    waiting_import.input_json = {**waiting_import.input_json,
        "sourcePath": str(source), "documentId": f"resume:{resume.id}"}
    career_db.commit()
    cancel_run(career_db, waiting_import.user_id, waiting_import.id)
    assert source.exists()
```

Add `cleanup_unadopted_import(run)` in `document_imports.py`. Call it after a queued/waiting import is committed cancelled, when an import reaches unrecoverable failure without `documentId`, and during stale-run recovery that resolves to failed/cancelled. A running task that loses its fence performs the same cleanup in its handler only when no typed row adopted the original.

- [ ] **Step 7: Run lifecycle tests**

Run: `pytest -q backend/tests/test_document_import_tasks.py backend/tests/test_agent_run_routes.py backend/tests/test_long_task_core.py`

Expected: confirmation, continuation, cancellation, recovery, and existing action tests all pass.

- [ ] **Step 8: Commit the confirmation lifecycle**

```bash
git add backend/services/document_imports.py backend/services/agent_runs.py backend/tests/test_document_import_tasks.py backend/tests/test_agent_run_routes.py
git commit -m "feat: confirm ambiguous document imports"
```

---

### Task 5: Frontend Import API and Run State Composable

**Files:**
- Create: `frontend/src/api/documentImports.ts`
- Create: `frontend/src/composables/useDocumentImport.ts`
- Create: `frontend/src/composables/useDocumentImport.spec.ts`

**Interfaces:**
- Consumes: `/api/documents/import`, `subscribeRun`, `fetchAgentRun`, `answerRunAction`, `DocumentRecord`, and a chat-specific session-storage key.
- Produces: `startImport(file)`, `resumeImport(runId)`, `confirmDocumentType(type)`, `resetImport()`, and readonly `state`, `pendingAction`, `resultDocument`, `error` refs.

- [ ] **Step 1: Write API/composable tests for success and waiting confirmation**

```typescript
it('returns the parsed document when the import run succeeds', async () => {
  postImport.mockResolvedValue({ runId: 'import-1', status: 'queued' })
  const flow = useDocumentImport('chat:session-1')
  await flow.startImport(new File(['content'], 'neutral.txt'))
  streams[0].onSnapshot?.(queuedSnapshot)
  streams[0].onEvent(succeededEvent)
  fetchAgentRun.mockResolvedValue({ ...succeededSnapshot, result: { documents: [resumeDocument] } })
  await flushPromises()
  expect(flow.resultDocument.value).toEqual(resumeDocument)
  expect(sessionStorage.getItem('resumate:document-import:chat:session-1')).toBeNull()
})

it('exposes choices and answers the existing run action', async () => {
  const flow = useDocumentImport('chat:session-1')
  await beginWaitingImport(flow, waitingSnapshotWithDocumentTypeAction)
  expect(flow.pendingAction.value?.payload.question).toBe('这份文件属于哪一类？')
  await flow.confirmDocumentType('jd')
  expect(answerRunAction).toHaveBeenCalledWith('import-1', 'action-1', {
    decision: 'submit', answers: { documentType: 'jd' }, expectedRevision: 1,
  })
})

it('recovers a non-terminal import when the chat is reopened', async () => {
  sessionStorage.setItem('resumate:document-import:chat:session-1', 'import-1')
  fetchAgentRun.mockResolvedValue(waitingSnapshotWithDocumentTypeAction)
  const flow = useDocumentImport('chat:session-1')
  await flushPromises()
  expect(flow.state.value).toBe('waiting_input')
  expect(streams[0].runId).toBe('import-1')
})
```

- [ ] **Step 2: Run the composable tests and confirm the modules are missing**

Run: `npm --prefix frontend run test:unit -- src/composables/useDocumentImport.spec.ts`

Expected: module resolution fails for `useDocumentImport`.

- [ ] **Step 3: Implement the import API**

```typescript
// frontend/src/api/documentImports.ts
import { buildAuthHeaders } from '../services/authToken'
import { answerRunAction } from './agentRuns'
import type { RunStatus } from '../services/agentStream'

export interface DocumentImportAccepted { runId: string; status: RunStatus }

export async function importLocalDocument(file: File, requestId: string): Promise<DocumentImportAccepted> {
  const body = new FormData()
  body.append('file', file)
  body.append('requestId', requestId)
  const response = await fetch('/api/documents/import', {
    method: 'POST', headers: buildAuthHeaders(), body,
  })
  const data = await response.json()
  if (!response.ok) throw new Error(data.detail || '文件导入失败')
  return data as DocumentImportAccepted
}

export const confirmImportedDocumentType = (runId: string, actionId: string,
  documentType: 'resume' | 'jd', revision: number) => answerRunAction(runId, actionId, {
    decision: 'submit', answers: { documentType }, expectedRevision: revision,
  })
```

- [ ] **Step 4: Implement the composable as a single subscription state machine**

```typescript
export type ImportState = 'idle' | 'uploading' | 'processing' | 'waiting_input' | 'succeeded' | 'failed'

export function useDocumentImport(storageScope: MaybeRefOrGetter<string>) {
  const state = ref<ImportState>('idle')
  const pendingAction = ref<RunAction | null>(null)
  const resultDocument = ref<DocumentRecord | null>(null)
  const error = ref('')
  let subscription: RunSubscription | undefined
  let runId = ''
  const savedRunKey = computed(() => `resumate:document-import:${toValue(storageScope)}`)

  async function refresh() {
    const snapshot = await fetchAgentRun(runId)
    state.value = snapshot.status === 'waiting_input' ? 'waiting_input' :
      snapshot.status === 'succeeded' ? 'succeeded' :
      snapshot.status === 'failed' || snapshot.status === 'cancelled' ? 'failed' : 'processing'
    pendingAction.value = snapshot.actions.find(action =>
      Array.isArray(action.payload.choices) && action.payload.question === '这份文件属于哪一类？') || null
    if (snapshot.status === 'succeeded') {
      resultDocument.value = (snapshot.result?.documents as DocumentRecord[] | undefined)?.[0] || null
      sessionStorage.removeItem(savedRunKey.value)
    }
    if (snapshot.status === 'failed' || snapshot.status === 'cancelled') {
      error.value = snapshot.errorCode || '文件导入失败'
      sessionStorage.removeItem(savedRunKey.value)
    }
  }

  async function resumeImport(savedRunId: string) {
    runId = savedRunId
    await refresh()
    if (state.value === 'succeeded' || state.value === 'failed') return
    subscription = subscribeRun({ runId, onEvent: refresh, onSnapshot: applySnapshot,
      onReset: applySnapshot, onError: value => { error.value = value.message } })
  }

  async function startImport(file: File) {
    resetImport(); state.value = 'uploading'
    const accepted = await importLocalDocument(file, crypto.randomUUID())
    runId = accepted.runId; state.value = 'processing'
    sessionStorage.setItem(savedRunKey.value, runId)
    subscription = subscribeRun({ runId, onEvent: refresh, onSnapshot: snapshot => applySnapshot(snapshot),
      onReset: snapshot => applySnapshot(snapshot), onError: value => { error.value = value.message } })
  }

  async function confirmDocumentType(type: 'resume' | 'jd') {
    const action = pendingAction.value
    if (!action) return
    await confirmImportedDocumentType(runId, action.actionId, type, action.revision)
    pendingAction.value = null; state.value = 'processing'
  }

  function resetImport() { subscription?.close(); subscription = undefined; sessionStorage.removeItem(savedRunKey.value);
    runId = ''; state.value = 'idle';
    pendingAction.value = null; resultDocument.value = null; error.value = '' }

  watch(savedRunKey, key => {
    subscription?.close(); subscription = undefined
    runId = ''; state.value = 'idle'; pendingAction.value = null
    resultDocument.value = null; error.value = ''
    const savedRunId = sessionStorage.getItem(key)
    if (savedRunId) void resumeImport(savedRunId)
  }, { immediate: true })
  onUnmounted(() => subscription?.close())
  return { state: readonly(state), pendingAction: readonly(pendingAction),
    resultDocument: readonly(resultDocument), error: readonly(error),
    startImport, resumeImport, confirmDocumentType, resetImport }
}
```

Use one `applySnapshot(snapshot)` helper in the final code so initial snapshots and refreshed snapshots share exactly the same transitions. Refresh only after run/action/status events; do not poll in parallel with `subscribeRun`. `resetImport()` is for an explicit new import and clears the saved run id; component unmount only closes the stream so returning to the same chat can recover the durable Run.

- [ ] **Step 5: Run the composable tests and typecheck**

Run: `npm --prefix frontend run test:unit -- src/composables/useDocumentImport.spec.ts && npm --prefix frontend run lint`

Expected: composable tests and Vue TypeScript checking pass.

- [ ] **Step 6: Commit the frontend import state flow**

```bash
git add frontend/src/api/documentImports.ts frontend/src/composables/useDocumentImport.ts frontend/src/composables/useDocumentImport.spec.ts
git commit -m "feat: track document imports in chat"
```

---

### Task 6: Floating Chat Material Picker

**Files:**
- Create: `frontend/src/components/chat/ChatMaterialPicker.vue`
- Create: `frontend/src/components/chat/ChatMaterialPicker.spec.ts`

**Interfaces:**
- Consumes props: `resumes: DocumentRecord[]`, `jobs: DocumentRecord[]`, `resumeId: string`, `jobId: string`, `importState: ImportState`, `pendingAction: RunAction | null`, `importError: string`.
- Emits: `update:resumeId`, `update:jobId`, `local-file`, and `confirm-type`.
- Produces the icon button, floating panel, selected chips, and all keyboard/outside-dismiss behavior.

- [ ] **Step 1: Write component tests for the three choices, chips, and selection events**

```typescript
it('opens an icon-only picker and emits saved document selections', async () => {
  const wrapper = mountPicker()
  const trigger = wrapper.get('[aria-label="添加材料"]')
  expect(trigger.text()).toBe('')
  await trigger.trigger('click')
  expect(wrapper.get('[role="dialog"][aria-label="添加材料"]')).toBeTruthy()
  expect(wrapper.getAll('[data-source-option]')).toHaveLength(3)
  expect(wrapper.find('select').exists()).toBe(false)
  await wrapper.get('[data-source="resume"]').trigger('click')
  await wrapper.get('[data-resume-id="resume:3"]').trigger('click')
  expect(wrapper.emitted('update:resumeId')?.[0]).toEqual(['resume:3'])
})

it('shows type-icon filename chips and removes one selection', async () => {
  const wrapper = mountPicker({ resumeId: 'resume:3', jobId: 'jd:4' })
  expect(wrapper.get('[title="我的简历.pdf"]').text()).toContain('我的简历.pdf')
  expect(wrapper.get('[title="产品经理.txt"]').text()).toContain('产品经理.txt')
  await wrapper.get('[aria-label="移除简历 我的简历.pdf"]').trigger('click')
  expect(wrapper.emitted('update:resumeId')?.at(-1)).toEqual([''])
})

it('emits a local file and shows content-type confirmation choices', async () => {
  const wrapper = mountPicker({ importState: 'waiting_input', pendingAction })
  const input = wrapper.get('input[type="file"]')
  Object.defineProperty(input.element, 'files', { value: [new File(['body'], 'neutral.txt')] })
  await input.trigger('change')
  expect(wrapper.emitted('local-file')?.[0]?.[0]).toBeInstanceOf(File)
  await wrapper.get('button[data-document-type="resume"]').trigger('click')
  expect(wrapper.emitted('confirm-type')?.[0]).toEqual(['resume'])
})
```

- [ ] **Step 2: Add dismissal tests before implementation**

```typescript
it('closes on outside pointerdown and Escape', async () => {
  const wrapper = mountPicker({ attachTo: document.body })
  await wrapper.get('[aria-label="添加材料"]').trigger('click')
  document.body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }))
  await nextTick()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  await wrapper.get('[aria-label="添加材料"]').trigger('click')
  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
  await nextTick()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
})

it('keeps the panel open for pointer interactions inside it', async () => {
  const wrapper = mountPicker({ attachTo: document.body })
  await wrapper.get('[aria-label="添加材料"]').trigger('click')
  await wrapper.get('[role="dialog"]').trigger('pointerdown')
  expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
})
```

- [ ] **Step 3: Run the component tests and confirm the component is absent**

Run: `npm --prefix frontend run test:unit -- src/components/chat/ChatMaterialPicker.spec.ts`

Expected: module resolution fails for `ChatMaterialPicker.vue`.

- [ ] **Step 4: Implement the picker markup and behavior**

Use this structural contract:

```vue
<template>
  <div ref="root" class="material-picker">
    <div v-if="selectedResume || selectedJob" class="material-chips">
      <button v-if="selectedResume" class="material-chip" :title="selectedResume.filename" :aria-label="`移除简历 ${selectedResume.filename}`"
              @click="$emit('update:resumeId', '')"><FileUser :size="15" />{{ selectedResume.filename }}<X :size="13" /></button>
      <button v-if="selectedJob" class="material-chip" :title="selectedJob.filename" :aria-label="`移除岗位 ${selectedJob.filename}`"
              @click="$emit('update:jobId', '')"><BriefcaseBusiness :size="15" />{{ selectedJob.filename }}<X :size="13" /></button>
    </div>
    <Transition name="material-pop">
      <section v-if="open" class="material-panel" role="dialog" aria-label="添加材料">
        <div class="source-actions">
          <button data-source-option data-source="resume" @click="section = 'resume'"><FileUser />选择数据库中的简历</button>
          <button data-source-option data-source="job" @click="section = 'job'"><BriefcaseBusiness />选择数据库中的岗位</button>
          <button data-source-option data-source="local" @click="localInput?.click()"><FileUp />选择本地文件</button>
        </div>
        <div v-if="section === 'resume'" class="saved-materials">
          <button v-for="item in resumes" :key="item.id" :data-resume-id="item.id"
                  @click="chooseResume(item.id)">{{ item.filename }}</button>
        </div>
        <div v-if="section === 'job'" class="saved-materials">
          <button v-for="item in jobs" :key="item.id" :data-job-id="item.id"
                  @click="chooseJob(item.id)">{{ item.parsedContent?.title || item.filename }}</button>
        </div>
        <div v-if="pendingAction" class="type-confirmation">
          <p>{{ pendingAction.payload.reason }}</p>
          <button data-document-type="resume" @click="$emit('confirm-type', 'resume')">这是简历</button>
          <button data-document-type="jd" @click="$emit('confirm-type', 'jd')">这是岗位</button>
        </div>
        <p v-if="importState === 'uploading' || importState === 'processing'" role="status">正在识别文件内容…</p>
        <p v-if="importError" role="alert">{{ importError }}</p>
      </section>
    </Transition>
    <input ref="localInput" class="visually-hidden" type="file" accept=".pdf,.docx,.txt,.md" @change="pickLocalFile">
    <button class="material-trigger" type="button" aria-label="添加材料" :aria-expanded="open"
            @click="open = !open"><Paperclip :size="18" /></button>
  </div>
</template>
```

Watch `open`: register document-level `pointerdown` and `keydown` listeners only while it is true, and remove them when it becomes false or on unmount. Ignore pointer events whose composed path contains `root`. Reset the file input value after emitting so choosing the same file again triggers `change`. Watch `importState`: close the panel when it becomes `succeeded`; when it becomes `failed`, return `section` to `root` while leaving the inline error visible for the next open.

- [ ] **Step 5: Implement placement, visual language, and motion**

```css
.material-picker { position: relative; display: flex; align-items: center; }
.material-trigger { width: 38px; height: 38px; border: 0; border-radius: 999px; color: var(--ink-muted);
  background: transparent; display: grid; place-items: center; transition: color 160ms ease, background 160ms ease, transform 160ms ease; }
.material-trigger:hover, .material-trigger:focus-visible { color: var(--ink); background: color-mix(in srgb, var(--paper) 72%, transparent); transform: translateY(-1px); }
.material-panel { position: absolute; z-index: 20; left: 50%; bottom: calc(100% + 8px); transform: translateX(-50%);
  width: min(360px, calc(100vw - 32px)); padding: 12px; border: 1px solid var(--line-soft); border-radius: 20px;
  background: color-mix(in srgb, var(--paper) 88%, transparent); box-shadow: 0 18px 48px rgba(91, 66, 43, .16);
  backdrop-filter: blur(22px) saturate(1.08); }
.material-pop-enter-active { transition: opacity 180ms ease, transform 180ms cubic-bezier(.2,.8,.2,1); }
.material-pop-leave-active { transition: opacity 140ms ease, transform 140ms ease; }
.material-pop-enter-from, .material-pop-leave-to { opacity: 0; transform: translate(-50%, 6px) scale(.96); }
@media (prefers-reduced-motion: reduce) {
  .material-pop-enter-active, .material-pop-leave-active { transition: opacity 100ms linear; }
  .material-pop-enter-from, .material-pop-leave-to { transform: translateX(-50%); }
}
```

Use the actual existing ChatView custom properties in the final stylesheet; if the component is scoped, provide its own fallbacks so it renders correctly in isolation.

- [ ] **Step 6: Run component tests and frontend typecheck**

Run: `npm --prefix frontend run test:unit -- src/components/chat/ChatMaterialPicker.spec.ts && npm --prefix frontend run lint`

Expected: all picker tests and typechecking pass.

- [ ] **Step 7: Commit the picker**

```bash
git add frontend/src/components/chat/ChatMaterialPicker.vue frontend/src/components/chat/ChatMaterialPicker.spec.ts
git commit -m "feat: add floating chat material picker"
```

---

### Task 7: Integrate the Picker into Chat and Verify the User Flow

**Files:**
- Modify: `frontend/src/views/ChatView.vue`
- Modify: `frontend/src/views/ChatView.spec.ts`
- Modify: `tests/e2e/chat.spec.ts`

**Interfaces:**
- Consumes: `ChatMaterialPicker`, `useDocumentImport`, document store `upsertDocuments`, existing `resumeId`/`jdId`, and existing chat send/restore logic.
- Produces: the final composer interaction with no exposed selects or old upload details panel.

- [ ] **Step 1: Replace view tests that depend on selects with picker behavior**

```typescript
it('sends the Resume and Job selected through the material picker', async () => {
  const { wrapper } = await open()
  await wrapper.get('[aria-label="添加材料"]').trigger('click')
  await wrapper.get('[data-source="resume"]').trigger('click')
  await wrapper.get('[data-resume-id="resume:3"]').trigger('click')
  await wrapper.get('[aria-label="添加材料"]').trigger('click')
  await wrapper.get('[data-source="job"]').trigger('click')
  await wrapper.get('[data-job-id="jd:4"]').trigger('click')
  await wrapper.get('textarea').setValue('帮我准备这份岗位')
  await wrapper.get('form.chat-composer').trigger('submit'); await flushPromises()
  expect(requests.find(item => item.url.endsWith('/messages'))!.body).toMatchObject({
    resumeId: 3, jdId: 4,
  })
})

it('adds an imported document to the store and selects its typed chip', async () => {
  importedDocument.value = resumeDocument
  await nextTick()
  expect(wrapper.get('[title="新简历.pdf"]').text()).toContain('新简历.pdf')
  await wrapper.get('textarea').setValue('分析新简历')
  await wrapper.get('form.chat-composer').trigger('submit'); await flushPromises()
  expect(requests.find(item => item.url.endsWith('/messages'))!.body.resumeId).toBe(8)
})
```

Update the session-switch test to assert chip presence/removal instead of `HTMLSelectElement.value`.

- [ ] **Step 2: Run ChatView tests and confirm they fail against the old controls**

Run: `npm --prefix frontend run test:unit -- src/views/ChatView.spec.ts`

Expected: new picker selectors are absent.

- [ ] **Step 3: Replace the old composer controls**

Remove `uploadType`, `uploading`, `uploadTaskId`, `uploadFile`, the two `<select>` elements, and `<details class="upload-menu">`. Keep `resumeId` and `jdId` because they remain the canonical chat context.

Create the import flow with a reactive chat scope so route changes recover only the Run belonging to that conversation:

```typescript
const importScope = computed(() => `chat:${String(route.params.sessionId || currentId.value || 'new')}`)
const {
  state: importState,
  pendingAction: pendingImportAction,
  resultDocument: importedDocument,
  error: importError,
  startImport,
  confirmDocumentType,
} = useDocumentImport(importScope)
```

Add:

```vue
<ChatMaterialPicker
  v-model:resume-id="resumeId"
  v-model:job-id="jdId"
  :resumes="documents.parsedResumes"
  :jobs="documents.parsedJds"
  :import-state="importState"
  :pending-action="pendingImportAction"
  :import-error="importError"
  @local-file="startImport"
  @confirm-type="confirmDocumentType"
/>
```

Replace `uploading` in the send button’s disabled expression with `importBusy`, computed as `['uploading', 'processing'].includes(importState.value)`. This preserves the current rule that a first message cannot create a new chat route while its intended material is still being classified. The picker also disables its local-file action while `importBusy` is true.

- [ ] **Step 4: Adopt successful imported documents into chat context**

```typescript
watch(importedDocument, document => {
  if (!document) return
  documents.upsertDocuments([document])
  if (document.type === 'resume') resumeId.value = document.id
  else jdId.value = document.id
})
```

Keep existing `openSession()` restoration from the last turn input and existing send serialization (`resumeId`/`jdId` numeric suffixes) unchanged.

- [ ] **Step 5: Remove obsolete upload-menu CSS and fit chips inside the capsule**

Delete `.upload-menu` rules. Let `.context-controls` wrap on narrow widths, keep the composer’s current floating overlap, and ensure material chips truncate filenames without increasing the default single-line composer height:

```css
.context-controls { min-width: 0; display: flex; align-items: center; gap: 8px; }
:deep(.material-chips) { min-width: 0; display: flex; gap: 6px; }
:deep(.material-chip) { max-width: 190px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 720px) { :deep(.material-chip) { max-width: 132px; } }
```

- [ ] **Step 6: Update the browser test to select saved materials through the picker**

Replace the two `selectOption` calls with:

```typescript
await page.getByRole('button', { name: '添加材料' }).click()
await page.getByRole('button', { name: '选择数据库中的简历' }).click()
await page.getByRole('button', { name: /测试简历/ }).click()
await page.getByRole('button', { name: '添加材料' }).click()
await page.getByRole('button', { name: '选择数据库中的岗位' }).click()
await page.getByRole('button', { name: /大模型算法测试工程师/ }).click()
```

Add assertions that the picker closes after selection, Escape closes it, and the composer still overlaps the conversation by the existing expected fraction.

Before selecting a row, verify alignment and keyboard dismissal with concrete geometry:

```typescript
await page.getByRole('button', { name: '添加材料' }).focus()
await page.keyboard.press('Enter')
const pickerGeometry = await page.evaluate(() => {
  const trigger = document.querySelector('.material-trigger')!.getBoundingClientRect()
  const panel = document.querySelector('.material-panel')!.getBoundingClientRect()
  return {
    centerDelta: Math.abs((trigger.left + trigger.width / 2) - (panel.left + panel.width / 2)),
    gap: trigger.top - panel.bottom,
    insideViewport: panel.left >= 0 && panel.right <= window.innerWidth,
  }
})
expect(pickerGeometry.centerDelta).toBeLessThan(2)
expect(pickerGeometry.gap).toBeGreaterThanOrEqual(7)
expect(pickerGeometry.gap).toBeLessThanOrEqual(9)
expect(pickerGeometry.insideViewport).toBe(true)
await page.keyboard.press('Escape')
await expect(page.getByRole('dialog', { name: '添加材料' })).toBeHidden()
```

After reopening, wait for the panel to be visible before measuring so the assertion checks the motion end state rather than the starting transform. Repeat `insideViewport` after switching to the 390px viewport. Use `Tab` to reach the trigger and assert its accessible name, which covers keyboard access without coupling the test to icon markup.

- [ ] **Step 7: Run focused frontend tests**

Run: `npm --prefix frontend run test:unit -- src/components/chat/ChatMaterialPicker.spec.ts src/composables/useDocumentImport.spec.ts src/views/ChatView.spec.ts`

Expected: all component, flow, and chat tests pass.

- [ ] **Step 8: Run backend import regression tests**

Run: `pytest -q backend/tests/test_document_classifier.py backend/tests/test_document_import_routes.py backend/tests/test_document_import_tasks.py backend/tests/test_document_tasks.py backend/tests/test_agent_run_routes.py`

Expected: all import, lifecycle, and typed document tests pass. A failure would identify a concrete mismatch in classification, persistence, action continuation, cleanup, or the existing typed upload path and must be fixed before browser verification.

- [ ] **Step 9: Run build and the focused browser test**

Run: `npm --prefix frontend run build && npx playwright test tests/e2e/chat.spec.ts`

Expected: the production build succeeds and the chat browser scenario passes at desktop and mobile viewport sizes. A layout assertion failure requires adjusting only picker/composer layout CSS; an API failure requires fixing the import or chat request contract.

- [ ] **Step 10: Commit the integrated flow**

```bash
git add frontend/src/views/ChatView.vue frontend/src/views/ChatView.spec.ts tests/e2e/chat.spec.ts
git commit -m "feat: integrate document picker into chat"
```
