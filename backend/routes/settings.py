from time import monotonic
from openai import OpenAI
from backend.model_transport import DefaultHttpxClient
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session, sessionmaker

from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.db.models import User
from backend.schemas.settings import (LlmSettingsResponse, LlmSettingsUpdate, LlmUsageDashboard,
    EmbeddingSettingsResponse, EmbeddingSettingsUpdate)
from backend.services import embedding_settings
from backend.services.llm_settings import (read_llm_settings, save_llm_settings,
    resolve_effective_llm_settings, record_llm_usage, usage_from_response)
from backend.services.dashboard_cache import DashboardCache

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/llm", response_model=LlmSettingsResponse)
def get_llm_settings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return read_llm_settings(current_user.id, db)


@router.put("/llm", response_model=LlmSettingsResponse)
def update_llm_settings(
    request: LlmSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return save_llm_settings(current_user.id, request, db)


@router.get("/usage", response_model=LlmUsageDashboard)
async def get_llm_usage(request: Request, current_user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    resources = getattr(request.app.state, 'redis', None)
    cache = DashboardCache(resources.commands if resources else None,
                           resources.namespace if resources else '')
    user_id = current_user.id
    session_factory = sessionmaker(bind=db.get_bind())
    # Authentication opened a read transaction; release it before Redis waits.
    db.close()
    return await cache.usage_dashboard(user_id, session_factory)


@router.get('/embedding', response_model=EmbeddingSettingsResponse)
def get_embedding_settings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return embedding_settings.read_settings(db)


@router.put('/embedding', response_model=EmbeddingSettingsResponse)
def update_embedding_settings(payload: EmbeddingSettingsUpdate,
                              current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return embedding_settings.save_settings(payload, db)


@router.post('/embedding/test')
def test_embedding_connection(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from backend.vector.embedding import EmbeddingService
    settings = embedding_settings.resolve_settings(db)
    db.close()
    try:
        vector = EmbeddingService(settings=settings).embed('ResuMate connection test')
        return {'success': True, 'dimensions': len(vector)}
    except Exception as exc:
        # Do not echo provider responses or credentials back to the browser.
        raise HTTPException(400, detail='连接测试失败，请检查 Embedding 地址、密钥和模型；本地模式需安装 local-embeddings 依赖。') from exc


@router.post('/llm/test')
def test_llm_connection(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    settings = resolve_effective_llm_settings(current_user.id, db)
    if not all((settings.api_key, settings.base_url, settings.model)):
        raise HTTPException(400, detail='请先保存 API Key、Base URL 和模型名称。')
    user_id = current_user.id
    db.close()
    from backend.services.llm_calls import CallTrace
    request_body = dict(model=settings.model, messages=[{'role': 'user', 'content': 'Reply with OK.'}],
                        max_tokens=min(settings.max_tokens, 64))
    trace = CallTrace(user_id, 'connection_test', settings.base_url,
                      {**request_body, 'timeout': settings.request_timeout_seconds})
    started = monotonic()
    usage, error = {}, None
    try:
        with OpenAI(api_key=settings.api_key, base_url=settings.base_url,
                    timeout=settings.request_timeout_seconds, max_retries=0,
                    http_client=DefaultHttpxClient(follow_redirects=False)) as client:
            response = client.chat.completions.create(**request_body)
            trace.finish(response=response)
            usage = usage_from_response(response)
            if not response.choices:
                raise ValueError('empty_response')
    except Exception as exc:
        error = exc
        trace.finish(error=exc)
    record_llm_usage(user_id=user_id, task='connection_test', model=settings.model,
        base_url=settings.base_url, **usage, success=error is None,
        error_type=type(error).__name__ if error else '',
        elapsed_ms=round((monotonic() - started) * 1000), db=db)
    if error:
        raise HTTPException(400, detail='连接测试失败，请检查已保存的地址、密钥和模型。') from error
    return {'success': True}


@router.get('/calls')
def get_model_calls(offset: int = 0, limit: int = 20,
                    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from backend.services.llm_calls import list_calls
    if offset < 0 or not 1 <= limit <= 100:
        raise HTTPException(422, '分页参数无效')
    return list_calls(db, current_user.id, offset, limit)


@router.get('/calls/{call_id}')
def get_model_call(call_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from backend.services.llm_calls import get_call
    return get_call(db, current_user.id, call_id)
