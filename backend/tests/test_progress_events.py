import pytest
import inspect
from fastapi import HTTPException
from fastapi import UploadFile
from io import BytesIO

from backend.schemas.workflow import AnalyzeResponse, DocumentParseResponse, SseProgressEvent
from backend.routes.documents import reparse_document, upload_documents
from backend.services.progress import TaskProgressHub


@pytest.mark.asyncio
async def test_progress_hub_replays_events_as_sse_lines():
    hub = TaskProgressHub()
    task_id = hub.create_task("parse")
    hub.publish(task_id, stage="upload", status="running", progress=10, message="Uploaded")
    hub.publish(task_id, stage="completed", status="success", progress=100, message="Done")

    stream = hub.stream(task_id)
    heartbeat = await anext(stream)
    assert heartbeat == ": heartbeat\n\n"
    first = await anext(stream)
    second = await anext(stream)

    assert first.startswith("data: ")
    assert '"stage":"upload"' in first
    assert '"progress":10' in first
    assert second.startswith("data: ")
    assert '"status":"success"' in second


def test_workflow_responses_expose_task_id_for_sse_subscription():
    parse_response = DocumentParseResponse(documents=[], task_id="task-parse")
    run_response = AnalyzeResponse(run_id=1, job_title="Backend Engineer", candidates=[], task_id="task-match")

    assert parse_response.task_id == "task-parse"
    assert run_response.task_id == "task-match"


def test_sse_progress_event_uses_frontend_contract_keys():
    event = SseProgressEvent(
        task_id="task-1",
        stage="llm_analyze",
        status="running",
        progress=40,
        overall_progress=40,
        message="LLM analyzing",
        document_id="resume:1",
        filename="resume.pdf",
        data={"document_type": "resume"},
    )

    payload = event.model_dump(by_alias=True)

    assert payload["taskId"] == "task-1"
    assert payload["documentId"] == "resume:1"
    assert payload["overallProgress"] == 40
    assert payload["stage"] == "llm_analyze"
    assert payload["status"] == "running"


def test_progress_hub_keeps_overall_progress_monotonic_and_exposes_page_counts():
    hub = TaskProgressHub()
    task_id = hub.create_task("parse")

    hub.publish(
        task_id,
        stage="extract",
        status="running",
        progress=30,
        stage_progress=50,
        current=1,
        total=2,
        message="Extracting page 1/2",
    )
    hub.publish(task_id, stage="llm_analyze", status="running", progress=25, message="LLM analyzing")

    first, second = hub._history[task_id]
    assert first.overall_progress == 30
    assert first.stage_progress == 50
    assert first.current == 1
    assert first.total == 2
    assert second.overall_progress == 30
    assert second.stage_progress is None


def test_document_parse_routes_are_sync_so_sse_can_flush_during_blocking_work():
    assert not inspect.iscoroutinefunction(upload_documents)
    assert not inspect.iscoroutinefunction(reparse_document)


def test_document_upload_rejects_multi_file_requests_before_sharing_one_task():
    files = [
        UploadFile(filename="one.txt", file=BytesIO(b"Candidate one resume content.")),
        UploadFile(filename="two.txt", file=BytesIO(b"Candidate two resume content.")),
    ]

    with pytest.raises(HTTPException) as exc_info:
        upload_documents(document_type="resume", files=files, task_id="task-shared", current_user=object(), db=object())

    assert exc_info.value.status_code == 422
