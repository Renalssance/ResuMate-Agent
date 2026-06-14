from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, TypeVar

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from backend.logging_config import log_llm_error, log_llm_prompt, log_llm_response, log_llm_validation_error

logger = logging.getLogger(__name__)
SchemaT = TypeVar("SchemaT", bound=BaseModel)

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"


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
        try:
            for attempt in range(1, 3):
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
                content = response.choices[0].message.content or ""
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                attempt_metadata = {**metadata, "attempt": attempt, "elapsed_ms": elapsed_ms}
                log_llm_response(task, content, attempt_metadata)
                try:
                    return schema.model_validate_json(content)
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
                    if attempt == 2:
                        raise
                    logger.warning(
                        "Structured LLM response failed validation; retrying | task=%s schema=%s",
                        task,
                        schema.__name__,
                    )
                    messages = [
                        *messages,
                        {"role": "assistant", "content": content},
                        {
                            "role": "user",
                            "content": (
                                "Your previous JSON failed schema validation. "
                                "Return a corrected JSON object only, matching the schema exactly.\n\n"
                                f"Validation errors:\n{exc}"
                            ),
                        },
                    ]
            raise RuntimeError("structured LLM call exhausted without a result")
        except Exception as exc:
            log_llm_error(task, exc, metadata)
            raise
