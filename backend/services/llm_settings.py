from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from backend.db.database import SessionLocal
from backend.db.models import LlmUsageEvent, UserLlmSettings
from backend.schemas.settings import LlmSettingsResponse, LlmSettingsUpdate, LlmUsageDashboard, LlmUsageSummary

DEFAULT_LLM_MAX_TOKENS = 8192
DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS = 300.0


@dataclass(frozen=True)
class EffectiveLlmSettings:
    api_key: str
    base_url: str
    model: str
    max_tokens: int
    request_timeout_seconds: float
    context_window_tokens: int | None = None


def env_llm_settings() -> EffectiveLlmSettings:
    return EffectiveLlmSettings(
        api_key=(os.getenv("OPENAI_API_KEY") or os.getenv("ARK_API_KEY") or "").strip(),
        base_url=(os.getenv("OPENAI_BASE_URL") or os.getenv("BASE_URL") or "").strip(),
        model=(os.getenv("LLM_MODEL") or os.getenv("MODEL") or "").strip(),
        context_window_tokens=_env_int("LLM_CONTEXT_WINDOW_TOKENS", 0) or None,
        max_tokens=_env_int("LLM_MAX_TOKENS", DEFAULT_LLM_MAX_TOKENS),
        request_timeout_seconds=_env_float("LLM_REQUEST_TIMEOUT_SECONDS", DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS),
    )


def resolve_effective_llm_settings(user_id: int | None, db: Session | None = None) -> EffectiveLlmSettings:
    if not user_id:
        return env_llm_settings()
    close_db = db is None
    db = db or SessionLocal()
    try:
        saved = db.query(UserLlmSettings).filter(UserLlmSettings.user_id == user_id).first()
        if not saved:
            return EffectiveLlmSettings("", "", "", DEFAULT_LLM_MAX_TOKENS, DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS)
        return EffectiveLlmSettings(
            api_key=(saved.api_key or "").strip(),
            base_url=(saved.base_url or "").strip(),
            model=(saved.model or "").strip(),
            context_window_tokens=saved.context_window_tokens,
            max_tokens=saved.max_tokens or DEFAULT_LLM_MAX_TOKENS,
            request_timeout_seconds=saved.request_timeout_seconds or DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
        )
    finally:
        if close_db:
            db.close()


def read_llm_settings(user_id: int, db: Session) -> LlmSettingsResponse:
    settings = resolve_effective_llm_settings(user_id, db)
    return LlmSettingsResponse(
        api_key=settings.api_key,
        has_api_key=bool(settings.api_key),
        api_key_hint=settings.api_key[-4:] if settings.api_key else "",
        base_url=settings.base_url,
        model=settings.model,
        max_tokens=settings.max_tokens,
        context_window_tokens=settings.context_window_tokens,
        request_timeout_seconds=settings.request_timeout_seconds,
    )


def save_llm_settings(user_id: int, payload: LlmSettingsUpdate, db: Session) -> LlmSettingsResponse:
    row = db.query(UserLlmSettings).filter(UserLlmSettings.user_id == user_id).first()
    capacity = (payload.context_window_tokens if 'context_window_tokens' in payload.model_fields_set
                else row.context_window_tokens if row else None)
    output_limit = payload.max_tokens or (row.max_tokens if row else None) or DEFAULT_LLM_MAX_TOKENS
    if capacity is not None and capacity <= output_limit:
        raise HTTPException(status_code=422, detail='上下文容量必须大于输出 Token 上限')
    now = datetime.now(timezone.utc)
    if not row:
        row = UserLlmSettings(user_id=user_id, created_at=now, updated_at=now)
        db.add(row)

    if payload.clear_api_key:
        row.api_key = ""
    elif payload.api_key is not None and payload.api_key.strip():
        row.api_key = payload.api_key.strip()
    if payload.base_url is not None:
        row.base_url = payload.base_url.strip()
    if payload.model is not None:
        row.model = payload.model.strip()
    if 'context_window_tokens' in payload.model_fields_set:
        row.context_window_tokens = payload.context_window_tokens
    if payload.max_tokens is not None:
        row.max_tokens = payload.max_tokens
    if payload.request_timeout_seconds is not None:
        row.request_timeout_seconds = payload.request_timeout_seconds
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return read_llm_settings(user_id, db)


def record_llm_usage(
    *,
    user_id: int | None,
    task: str,
    model: str,
    base_url: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    success: bool = True,
    error_type: str = "",
    elapsed_ms: int = 0,
    db: Session | None = None,
) -> None:
    if not user_id:
        return
    close_db = db is None
    db = db or SessionLocal()
    try:
        db.add(
            LlmUsageEvent(
                user_id=user_id,
                task=task,
                model=model or "",
                base_url=base_url or "",
                prompt_tokens=max(0, int(prompt_tokens or 0)),
                completion_tokens=max(0, int(completion_tokens or 0)),
                total_tokens=max(0, int(total_tokens or prompt_tokens + completion_tokens or 0)),
                success=success,
                error_type=error_type or "",
                elapsed_ms=max(0, int(elapsed_ms or 0)),
                called_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        from backend.services.dashboard_cache import invalidate_usage_summary
        invalidate_usage_summary(user_id)
    finally:
        if close_db:
            db.close()


def usage_from_response(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if not usage:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    return {
        "prompt_tokens": _usage_int(usage, "prompt_tokens", "input_tokens"),
        "completion_tokens": _usage_int(usage, "completion_tokens", "output_tokens"),
        "total_tokens": _usage_int(usage, "total_tokens"),
    }


def load_usage_summary(db: Session, user_id: int) -> LlmUsageSummary:
    owned = LlmUsageEvent.user_id == user_id
    totals = db.query(
        func.count(LlmUsageEvent.id),
        func.coalesce(func.sum(case((LlmUsageEvent.success.is_(True), 1), else_=0)), 0),
        func.coalesce(func.sum(LlmUsageEvent.total_tokens), 0),
        func.coalesce(func.sum(LlmUsageEvent.prompt_tokens), 0),
        func.coalesce(func.sum(LlmUsageEvent.completion_tokens), 0),
        func.max(LlmUsageEvent.called_at),
    ).filter(owned).one()
    total, successful, tokens, prompt, completion, last = totals
    day = func.date(LlmUsageEvent.called_at)
    daily = db.query(day, func.count(LlmUsageEvent.id), func.sum(LlmUsageEvent.total_tokens)).filter(
        owned).group_by(day).order_by(day).all()
    task = func.coalesce(func.nullif(LlmUsageEvent.task, ''), 'unknown')
    task_tokens = func.sum(LlmUsageEvent.total_tokens)
    by_task = db.query(task, func.count(LlmUsageEvent.id), task_tokens).filter(
        owned).group_by(task).order_by(task_tokens.desc(), task).all()
    return LlmUsageSummary(
        total_calls=total, successful_calls=successful, failed_calls=total-successful,
        success_rate=round(successful / total * 100) if total else 0,
        total_tokens=tokens, prompt_tokens=prompt, completion_tokens=completion,
        last_called_at=last,
        daily=[{'date': str(date), 'calls': calls, 'total_tokens': value} for date, calls, value in daily],
        by_task=[{'task': name, 'calls': calls, 'total_tokens': value} for name, calls, value in by_task],
    )


def load_recent_usage(db: Session, user_id: int, limit: int = 12):
    return (db.query(LlmUsageEvent).filter(LlmUsageEvent.user_id == user_id)
            .order_by(LlmUsageEvent.called_at.desc(), LlmUsageEvent.id.desc()).limit(limit).all())


def usage_dashboard(user_id: int, db: Session) -> LlmUsageDashboard:
    return LlmUsageDashboard(**load_usage_summary(db, user_id).model_dump(),
                             recent_calls=load_recent_usage(db, user_id))


def _usage_int(usage: Any, *names: str) -> int:
    for name in names:
        value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        if value is not None:
            return int(value)
    return 0


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default
