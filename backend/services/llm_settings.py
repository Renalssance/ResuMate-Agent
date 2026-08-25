from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.db.database import SessionLocal
from backend.db.models import LlmUsageEvent, UserLlmSettings
from backend.schemas.settings import LlmSettingsResponse, LlmSettingsUpdate, LlmUsageDashboard

DEFAULT_LLM_MAX_TOKENS = 8192
DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS = 300.0


@dataclass(frozen=True)
class EffectiveLlmSettings:
    api_key: str
    base_url: str
    model: str
    max_tokens: int
    request_timeout_seconds: float


def env_llm_settings() -> EffectiveLlmSettings:
    return EffectiveLlmSettings(
        api_key=(os.getenv("OPENAI_API_KEY") or os.getenv("ARK_API_KEY") or "").strip(),
        base_url=(os.getenv("OPENAI_BASE_URL") or os.getenv("BASE_URL") or "").strip(),
        model=(os.getenv("LLM_MODEL") or os.getenv("MODEL") or "").strip(),
        max_tokens=_env_int("LLM_MAX_TOKENS", DEFAULT_LLM_MAX_TOKENS),
        request_timeout_seconds=_env_float("LLM_REQUEST_TIMEOUT_SECONDS", DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS),
    )


def resolve_effective_llm_settings(user_id: int | None, db: Session | None = None) -> EffectiveLlmSettings:
    env = env_llm_settings()
    if not user_id:
        return env
    close_db = db is None
    db = db or SessionLocal()
    try:
        saved = db.query(UserLlmSettings).filter(UserLlmSettings.user_id == user_id).first()
        if not saved:
            return env
        return EffectiveLlmSettings(
            api_key=(saved.api_key or env.api_key).strip(),
            base_url=(saved.base_url or env.base_url).strip(),
            model=(saved.model or env.model).strip(),
            max_tokens=saved.max_tokens or env.max_tokens,
            request_timeout_seconds=saved.request_timeout_seconds or env.request_timeout_seconds,
        )
    finally:
        if close_db:
            db.close()


def read_llm_settings(user_id: int, db: Session) -> LlmSettingsResponse:
    settings = resolve_effective_llm_settings(user_id, db)
    return LlmSettingsResponse(
        has_api_key=bool(settings.api_key),
        api_key_hint=settings.api_key[-4:] if settings.api_key else "",
        base_url=settings.base_url,
        model=settings.model,
        max_tokens=settings.max_tokens,
        request_timeout_seconds=settings.request_timeout_seconds,
    )


def save_llm_settings(user_id: int, payload: LlmSettingsUpdate, db: Session) -> LlmSettingsResponse:
    row = db.query(UserLlmSettings).filter(UserLlmSettings.user_id == user_id).first()
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


def usage_dashboard(user_id: int, db: Session) -> LlmUsageDashboard:
    rows = (
        db.query(LlmUsageEvent)
        .filter(LlmUsageEvent.user_id == user_id)
        .order_by(LlmUsageEvent.called_at.desc())
        .all()
    )
    total_calls = len(rows)
    successful_calls = sum(1 for row in rows if row.success)
    total_tokens = sum(row.total_tokens for row in rows)
    prompt_tokens = sum(row.prompt_tokens for row in rows)
    completion_tokens = sum(row.completion_tokens for row in rows)
    daily: dict[str, dict[str, int]] = {}
    by_task: dict[str, dict[str, int]] = {}
    for row in rows:
        day = row.called_at.date().isoformat()
        daily.setdefault(day, {"calls": 0, "total_tokens": 0})
        daily[day]["calls"] += 1
        daily[day]["total_tokens"] += row.total_tokens
        task = row.task or "unknown"
        by_task.setdefault(task, {"calls": 0, "total_tokens": 0})
        by_task[task]["calls"] += 1
        by_task[task]["total_tokens"] += row.total_tokens

    return LlmUsageDashboard(
        total_calls=total_calls,
        successful_calls=successful_calls,
        failed_calls=total_calls - successful_calls,
        success_rate=round(successful_calls / total_calls * 100) if total_calls else 0,
        total_tokens=total_tokens,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        last_called_at=rows[0].called_at if rows else None,
        daily=[
            {"date": day, "calls": values["calls"], "total_tokens": values["total_tokens"]}
            for day, values in sorted(daily.items())
        ],
        by_task=[
            {"task": task, "calls": values["calls"], "total_tokens": values["total_tokens"]}
            for task, values in sorted(by_task.items(), key=lambda item: item[1]["total_tokens"], reverse=True)
        ],
        recent_calls=rows[:12],
    )


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
