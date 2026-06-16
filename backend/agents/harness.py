from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from backend.logging_config import log_llm_error, log_llm_prompt, log_llm_response, log_llm_validation_error
from backend.services.progress import progress_hub

logger = logging.getLogger(__name__)
SchemaT = TypeVar("SchemaT", bound=BaseModel)

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
MAX_REFLECTIONS = 2


class AgentHarness:
    """Single entry point for OpenAI-compatible structured LLM calls."""

    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ARK_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("BASE_URL") or None
        self.model = os.getenv("LLM_MODEL") or os.getenv("MODEL")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for AgentHarness")
        if not self.model:
            raise RuntimeError("LLM_MODEL is required for AgentHarness")
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.progress_hub = progress_hub

    @staticmethod
    def load_prompt(name: str) -> str:
        path = PROMPT_DIR / f"{name}.md"
        return path.read_text(encoding="utf-8")

    @staticmethod
    def render_prompt(template: str, variables: dict[str, Any]) -> str:
        prompt = template
        for key, value in variables.items():
            if not isinstance(value, str):
                value = json.dumps(value, ensure_ascii=False)
            prompt = prompt.replace("{{" + key + "}}", value)
        return prompt

    def run_schema(
        self,
        *,
        task: str,
        prompt_name: str,
        schema: type[SchemaT],
        variables: dict[str, Any],
        task_id: str | None = None,
        progress_stage: str | None = None,
        progress: int | None = None,
    ) -> SchemaT:
        prompt = self.render_prompt(self.load_prompt(prompt_name), variables)
        schema_json = schema.model_json_schema()
        metadata = {"task": task, "model": self.model, "schema": schema.__name__}
        schema_text = json.dumps(schema_json, ensure_ascii=False)
        system_prompt = (
            "Return strict JSON only. No markdown, no commentary. "
            "The response must match this JSON Schema exactly:\n"
            f"{schema_text}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        log_llm_prompt(task, f"{system_prompt}\n\n{prompt}", metadata)
        started = time.perf_counter()
        self._publish_agent_progress(
            task_id=task_id,
            stage=progress_stage,
            progress=progress,
            task=task,
            schema_name=schema.__name__,
            phase="prompt_uploading",
            attempt=1,
            level="info",
            message="上传Prompt中",
        )
        try:
            for attempt in range(1, MAX_REFLECTIONS + 2):
                attempt_metadata = metadata
                self._publish_agent_progress(
                    task_id=task_id,
                    stage=progress_stage,
                    progress=progress,
                    task=task,
                    schema_name=schema.__name__,
                    phase="waiting_response",
                    attempt=attempt,
                    level="info",
                    message=f"等待 LLM 响应，第 {attempt} 次尝试",
                )
                try:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=0.1,
                        response_format={
                            "type": "json_schema",
                            "json_schema": {
                                "name": schema.__name__,
                                "schema": schema_json,
                                "strict": True,
                            },
                        },
                    )
                except Exception as exc:
                    elapsed_ms = int((time.perf_counter() - started) * 1000)
                    attempt_metadata = {**metadata, "attempt": attempt, "elapsed_ms": elapsed_ms}
                    if attempt > MAX_REFLECTIONS:
                        self._publish_agent_progress(
                            task_id=task_id,
                            stage=progress_stage,
                            progress=progress,
                            task=task,
                            schema_name=schema.__name__,
                            phase="failed",
                            attempt=attempt,
                            level="error",
                            message=f"LLM 调用失败: {type(exc).__name__}: {exc}",
                        )
                        raise
                    logger.warning(
                        "Structured LLM call failed; retrying with reflection | task=%s schema=%s error=%s",
                        task,
                        schema.__name__,
                        exc,
                    )
                    self._publish_agent_progress(
                        task_id=task_id,
                        stage=progress_stage,
                        progress=progress,
                        task=task,
                        schema_name=schema.__name__,
                        phase="reflecting",
                        attempt=attempt,
                        level="warning",
                        message=f"LLM 调用失败，第 {attempt + 1} 次尝试",
                    )
                    messages = [
                        *messages,
                        {
                            "role": "user",
                            "content": self._reflection_prompt(
                                reflection_number=attempt,
                                schema_name=schema.__name__,
                                error_text=f"{type(exc).__name__}: {exc}",
                            ),
                        },
                    ]
                    continue
                content = response.choices[0].message.content or ""
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                attempt_metadata = {**metadata, "attempt": attempt, "elapsed_ms": elapsed_ms}
                log_llm_response(task, content, attempt_metadata)
                self._publish_agent_progress(
                    task_id=task_id,
                    stage=progress_stage,
                    progress=progress,
                    task=task,
                    schema_name=schema.__name__,
                    phase="validating_response",
                    attempt=attempt,
                    level="info",
                    message=f"验证结构化 JSON 响应，第 {attempt} 次尝试",
                )
                try:
                    result = schema.model_validate_json(content)
                    self._publish_agent_progress(
                        task_id=task_id,
                        stage=progress_stage,
                        progress=progress,
                        task=task,
                        schema_name=schema.__name__,
                        phase="completed",
                        attempt=attempt,
                        level="success",
                        message="分析成功",
                    )
                    return result
                except ValidationError as exc:
                    error_summary = [
                        {
                            "loc": error.get("loc"),
                            "type": error.get("type"),
                            "msg": error.get("msg"),
                        }
                        for error in exc.errors()
                    ]
                    log_llm_validation_error(
                        task,
                        error_summary,
                        {**attempt_metadata, "validation_error_count": len(error_summary)},
                    )
                    if attempt > MAX_REFLECTIONS:
                        raise
                    logger.warning(
                        "Structured LLM response failed validation; retrying with reflection | task=%s schema=%s",
                        task,
                        schema.__name__,
                    )
                    self._publish_agent_progress(
                        task_id=task_id,
                        stage=progress_stage,
                        progress=progress,
                        task=task,
                        schema_name=schema.__name__,
                        phase="reflecting",
                        attempt=attempt,
                        level="warning",
                        message=f"结构化验证失败，第 {attempt + 1} 次尝试",
                    )
                    messages = [
                        *messages,
                        {"role": "assistant", "content": content},
                        {
                            "role": "user",
                            "content": self._reflection_prompt(
                                reflection_number=attempt,
                                schema_name=schema.__name__,
                                error_text=(
                                    "Validation errors:\n"
                                    f"{json.dumps(error_summary, ensure_ascii=False)}\n\n"
                                    f"Full validation detail:\n{exc}"
                                ),
                            ),
                        },
                    ]
            raise RuntimeError("structured LLM call exhausted without a result")
        except Exception as exc:
            log_llm_error(task, exc, metadata)
            self._publish_agent_progress(
                task_id=task_id,
                stage=progress_stage,
                progress=progress,
                task=task,
                schema_name=schema.__name__,
                phase="failed",
                attempt=MAX_REFLECTIONS + 1,
                level="error",
                message=f"LLM分析失败: {type(exc).__name__}: {exc}",
            )
            raise

    @staticmethod
    def _reflection_prompt(*, reflection_number: int, schema_name: str, error_text: str) -> str:
        return (
            f"Reflection attempt {reflection_number} of {MAX_REFLECTIONS}.\n"
            "Your previous output or model call failed. Reflect on the error, identify the violated requirement, "
            "and return a corrected JSON object only.\n"
            f"The corrected response must match the {schema_name} JSON Schema exactly. "
            "Do not include markdown, explanations, comments, or extra keys.\n\n"
            f"{error_text}"
        )

    def _publish_agent_progress(
        self,
        *,
        task_id: str | None,
        stage: str | None,
        progress: int | None,
        task: str,
        schema_name: str,
        phase: str,
        attempt: int,
        level: str,
        message: str,
    ) -> None:
        if not task_id:
            return
        self.progress_hub.publish(
            task_id,
            stage=stage or "llm_analyze",
            status="running",
            progress=progress if progress is not None else 0,
            message=message,
            data={
                "agent": {
                    "phase": phase,
                    "task": task,
                    "schema": schema_name,
                    "attempt": attempt,
                    "message": message,
                    "level": level,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            },
        )
