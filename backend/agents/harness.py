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

from backend.logging_config import (
    log_llm_error,
    log_llm_prompt,
    log_llm_request,
    log_llm_response,
    log_llm_validation_error,
)
from backend.services.progress import progress_hub

logger = logging.getLogger(__name__)
SchemaT = TypeVar("SchemaT", bound=BaseModel)

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
MAX_REFLECTIONS = 2
DEFAULT_LLM_MAX_TOKENS = 8192
DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS = 90.0


class AgentHarness:
    """Single entry point for OpenAI-compatible structured LLM calls."""

    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ARK_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("BASE_URL") or None
        self.model = os.getenv("LLM_MODEL") or os.getenv("MODEL")
        self.base_url = base_url or ""
        self.max_tokens = self._env_int("LLM_MAX_TOKENS", DEFAULT_LLM_MAX_TOKENS)
        self.request_timeout = self._env_float(
            "LLM_REQUEST_TIMEOUT_SECONDS",
            DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
        )
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
        example_text = json.dumps(self._schema_json_example(schema_json), ensure_ascii=False, indent=2)
        system_prompt = (
            "Return strict JSON only. No markdown, no commentary. "
            "The response must match this JSON Schema exactly:\n"
            f"{schema_text}\n\n"
            "Example JSON output shape:\n"
            f"{example_text}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        log_llm_prompt(task, f"{system_prompt}\n\n{prompt}", metadata)
        started = time.perf_counter()
        response_format = self._initial_response_format(task, schema.__name__, schema_json)
        self._publish_agent_progress(
            task_id=task_id,
            stage=progress_stage,
            progress=progress,
            task=task,
            schema_name=schema.__name__,
            phase="prompt_uploading",
            attempt=1,
            level="info",
            message="Uploading prompt",
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
                    message=f"Waiting for LLM response, attempt {attempt}",
                )
                try:
                    response = self._create_chat_completion(task, messages, response_format, attempt)
                except Exception as exc:
                    fallback_succeeded = False
                    fallback_response_format = self._fallback_response_format(response_format, exc)
                    if fallback_response_format != response_format:
                        response_format = fallback_response_format
                        logger.warning(
                            "response_format unavailable; retrying with fallback | "
                            "task=%s schema=%s error=%s",
                            task,
                            schema.__name__,
                            exc,
                        )
                        try:
                            response = self._create_chat_completion(task, messages, response_format, attempt)
                        except Exception as fallback_exc:
                            exc = fallback_exc
                        else:
                            fallback_succeeded = True

                    if not fallback_succeeded:
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
                                message=f"LLM call failed: {type(exc).__name__}: {exc}",
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
                            message=f"LLM call failed, retrying attempt {attempt + 1}",
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
                    message=f"Validating structured JSON response, attempt {attempt}",
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
                        message="Analysis completed",
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
                        message=f"Structured validation failed, retrying attempt {attempt + 1}",
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
                message=f"LLM analysis failed: {type(exc).__name__}: {exc}",
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

    @staticmethod
    def _json_schema_response_format(schema_name: str, schema_json: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema_json,
                "strict": True,
            },
        }

    def _initial_response_format(
        self,
        task: str,
        schema_name: str,
        schema_json: dict[str, Any],
    ) -> dict[str, Any] | None:
        if self._should_use_json_object_response_format(task):
            return {"type": "json_object"}
        return self._json_schema_response_format(schema_name, schema_json)

    def _fallback_response_format(
        self,
        response_format: dict[str, Any] | None,
        exc: Exception,
    ) -> dict[str, Any] | None:
        if response_format is None or not self._is_response_format_type_unavailable(exc):
            return response_format
        if response_format.get("type") == "json_schema":
            return {"type": "json_object"}
        if response_format.get("type") == "json_object":
            return None
        return response_format

    def _should_use_json_object_response_format(self, task: str) -> bool:
        return self._is_deepseek() and task in {"document.parse_jd", "document.parse_resume"}

    @staticmethod
    def _is_json_schema_response_format(response_format: dict[str, Any] | None) -> bool:
        if response_format is None:
            return False
        return response_format.get("type") == "json_schema"

    @staticmethod
    def _is_response_format_type_unavailable(exc: Exception) -> bool:
        message = str(exc).lower()
        return "response_format" in message and (
            "unavailable" in message
            or "unsupported" in message
            or "invalid_request_error" in message
        )

    def _create_chat_completion(
        self,
        task: str,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None,
        attempt: int,
    ):
        max_tokens = getattr(self, "max_tokens", DEFAULT_LLM_MAX_TOKENS)
        request_timeout = getattr(self, "request_timeout", DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS)
        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": max_tokens,
            "timeout": request_timeout,
        }
        if response_format is not None:
            request_kwargs["response_format"] = response_format
        if self._should_disable_thinking(task):
            request_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        log_llm_request(
            task,
            {
                "model": self.model,
                "attempt": attempt,
                "response_format": response_format,
                "max_tokens": max_tokens,
                "timeout_seconds": request_timeout,
                "extra_body": request_kwargs.get("extra_body"),
            },
        )
        return self.client.chat.completions.create(**request_kwargs)

    def _should_disable_thinking(self, task: str) -> bool:
        return self._is_deepseek() and task in {"document.parse_jd", "document.parse_resume"}

    def _is_deepseek(self) -> bool:
        base_url = getattr(self, "base_url", "")
        return "deepseek.com" in base_url.lower() or str(self.model).lower().startswith("deepseek-")

    @staticmethod
    def _schema_json_example(schema_json: dict[str, Any]) -> Any:
        return AgentHarness._schema_node_example(schema_json, schema_json.get("$defs", {}), depth=0)

    @staticmethod
    def _schema_node_example(node: dict[str, Any], defs: dict[str, Any], *, depth: int) -> Any:
        if depth > 8:
            return None
        if "$ref" in node:
            ref_name = str(node["$ref"]).split("/")[-1]
            return AgentHarness._schema_node_example(defs.get(ref_name, {}), defs, depth=depth + 1)
        if "enum" in node:
            values = node.get("enum") or []
            return values[0] if values else ""
        for union_key in ("anyOf", "oneOf"):
            options = [option for option in node.get(union_key, []) if option.get("type") != "null"]
            if options:
                return AgentHarness._schema_node_example(options[0], defs, depth=depth + 1)
        node_type = node.get("type")
        if node_type == "object" or "properties" in node:
            return {
                key: AgentHarness._schema_node_example(value, defs, depth=depth + 1)
                for key, value in node.get("properties", {}).items()
            }
        if node_type == "array":
            return [AgentHarness._schema_node_example(node.get("items", {}), defs, depth=depth + 1)]
        if node_type == "number":
            return 0
        if node_type == "integer":
            return 0
        if node_type == "boolean":
            return False
        return ""

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        raw = os.getenv(name)
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            logger.warning("Invalid integer env var %s=%r; using default %s", name, raw, default)
            return default

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        raw = os.getenv(name)
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            logger.warning("Invalid float env var %s=%r; using default %s", name, raw, default)
            return default

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
