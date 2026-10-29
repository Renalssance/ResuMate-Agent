from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session, sessionmaker

from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.db.models import User
from backend.schemas.agent_runs import ActionResponse, RunAccepted, RunCreate
from backend.services import agent_runs, run_events
from backend.services.run_delivery import publish_run


class RunRoute(APIRoute):
    """Apply the new error contract only to Run routes, including auth/validation."""
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def route(request):
            request_id = str(uuid4())
            try:
                return await handler(request)
            except agent_runs.RunError as error:
                return JSONResponse(status_code=error.status, content={
                    'code': error.code, 'message': error.message, 'requestId': request_id})
            except RequestValidationError:
                return JSONResponse(status_code=422, content={
                    'code': 'invalid_request', 'message': '请求字段无效', 'requestId': request_id})
            except HTTPException as error:
                code = {401: 'unauthorized', 403: 'forbidden', 429: 'rate_limited'}.get(error.status_code, 'request_failed')
                return JSONResponse(status_code=error.status_code, headers=error.headers, content={
                    'code': code, 'message': str(error.detail), 'requestId': request_id})
        return route


router = APIRouter(prefix='/api/agent/runs', tags=['agent-runs'], route_class=RunRoute)


@router.post('', status_code=202, response_model=RunAccepted)
def create(request: RunCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = agent_runs.create_run(db, user.id, request)
    if run.status == "queued":
        publish_run(run.id)
    return RunAccepted(run_id=run.id, status=run.status)


@router.get('')
def list_runs(limit: int = Query(default=20, ge=1, le=50), offset: int = Query(default=0, ge=0),
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return agent_runs.list_runs(db, user.id, limit=limit, offset=offset)


@router.get('/{run_id}/artifacts')
def artifacts(run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return agent_runs.run_artifacts(db, user.id, run_id)


@router.get('/{run_id}/download')
def download(run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from backend.services.resume_export import download_file
    path, filename = download_file(db, user.id, run_id)
    return FileResponse(path, media_type='application/pdf', filename=filename)


@router.get('/{run_id}')
def snapshot(run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return agent_runs.run_snapshot(db, user.id, run_id)


@router.post('/{run_id}/cancel', status_code=202, response_model=RunAccepted)
def cancel(run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = agent_runs.cancel_run(db, user.id, run_id)
    return RunAccepted(run_id=run.id, status=run.status)


@router.post('/{run_id}/retry', status_code=202, response_model=RunAccepted)
def retry(run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = agent_runs.retry_run(db, user.id, run_id)
    if run.status == "queued":
        publish_run(run.id)
    return RunAccepted(run_id=run.id, status=run.status)


@router.post('/{run_id}/actions/{action_id}', status_code=202, response_model=RunAccepted)
def answer(run_id: str, action_id: str, response: ActionResponse,
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = agent_runs.answer_action(db, user.id, run_id, action_id, response)
    if run.status == "queued":
        publish_run(run.id)
    return RunAccepted(run_id=run.id, status=run.status)


@router.get('/{run_id}/events')
def events(run_id: str, after: int = Query(default=0, ge=0),
           last_event_id: int | None = Header(default=None, ge=0),
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cursor = max(after, last_event_id or 0)
    user_id = user.id
    # Validate ownership and cursor before HTTP headers are sent.
    run_events.read_page(db, user_id, run_id, cursor)
    session_factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    db.close()
    return StreamingResponse(run_events.stream_events(session_factory, user_id, run_id, cursor),
                             media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
