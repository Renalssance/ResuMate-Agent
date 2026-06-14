import pytest
import inspect

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
        message="LLM analyzing",
        data={"document_type": "resume"},
    )

    payload = event.model_dump(by_alias=True)

    assert payload["taskId"] == "task-1"
    assert payload["stage"] == "llm_analyze"
    assert payload["status"] == "running"


def test_document_parse_routes_are_sync_so_sse_can_flush_during_blocking_work():
    assert not inspect.iscoroutinefunction(upload_documents)
    assert not inspect.iscoroutinefunction(reparse_document)
