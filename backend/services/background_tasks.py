"""Durable submission and bounded synchronous compatibility for long tasks."""
from time import monotonic, sleep

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from backend.schemas.agent_runs import RunCreate, RunStatus
from backend.services import agent_runs
from backend.services.run_delivery import publish_run


def submit_task(db, user_id: int, request: RunCreate, prefer: str = '') -> JSONResponse:
    try:
        run = agent_runs.create_run(db, user_id, request)
    except agent_runs.RunError as error:
        raise HTTPException(status_code=error.status, detail=error.message) from error
    run_id, status = run.id, run.status
    session_factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    db.close()
    if status == RunStatus.QUEUED:
        publish_run(run_id)
    headers = {'Location': f'/api/agent/runs/{run_id}', 'X-Task-Id': run_id}
    if 'respond-async' in prefer:
        return JSONResponse(status_code=202, content={'taskId': run_id},
                            headers={**headers, 'Preference-Applied': 'respond-async'})
    deadline = monotonic() + 45
    while True:
        with session_factory() as reader:
            saved = agent_runs.get_run(reader, user_id, run_id)
            status, result, error_code = saved.status, saved.result_json, saved.error_code
        if status == RunStatus.SUCCEEDED:
            return JSONResponse(content=result, headers=headers)
        if status in (RunStatus.FAILED, RunStatus.CANCELLED):
            message = '任务已取消' if status == RunStatus.CANCELLED else error_code or '任务执行失败'
            raise HTTPException(status_code=400, detail=message, headers=headers)
        if monotonic() >= deadline:
            return JSONResponse(status_code=202, content={
                'taskId': run_id, 'status': status, 'code': 'task_pending'}, headers=headers)
        sleep(min(0.25, max(0, deadline - monotonic())))
