import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "log"
DEFAULT_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def _build_file_handler(path: Path, level: int, formatter: logging.Formatter) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(formatter)
    handler._mewagent_handler = True  # type: ignore[attr-defined]
    return handler


def setup_logging() -> None:
    """Write application logs to stdout and rotating files under ./log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    formatter = logging.Formatter(DEFAULT_FORMAT)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if not any(getattr(handler, "_resumate_console", False) for handler in root_logger.handlers):
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(level)
        console.setFormatter(formatter)
        console._resumate_console = True  # type: ignore[attr-defined]
        root_logger.addHandler(console)

    existing_paths = {
        str(getattr(handler, "baseFilename", ""))
        for handler in root_logger.handlers
        if getattr(handler, "_mewagent_handler", False)
    }

    backend_log_path = str(LOG_DIR / "backend.log")
    if backend_log_path not in existing_paths:
        root_logger.addHandler(_build_file_handler(LOG_DIR / "backend.log", level, formatter))

    error_log_path = str(LOG_DIR / "error.log")
    if error_log_path not in existing_paths:
        root_logger.addHandler(_build_file_handler(LOG_DIR / "error.log", logging.WARNING, formatter))

    llm_logger = logging.getLogger("backend.llm")
    llm_logger.setLevel(logging.DEBUG)
    llm_existing_paths = {
        str(getattr(handler, "baseFilename", ""))
        for handler in llm_logger.handlers
        if getattr(handler, "_mewagent_handler", False)
    }
    llm_log_path = str(LOG_DIR / "llm.log")
    if llm_log_path not in llm_existing_paths:
        llm_logger.addHandler(_build_file_handler(LOG_DIR / "llm.log", logging.DEBUG, formatter))
    llm_logger.propagate = False


# Keep operational metadata; prompts, filenames, provider bodies and schemas can
# contain private source material. The business record remains its own source.
_LOG_METADATA_KEYS = frozenset({
    "task", "model", "schema", "user_id", "session_id", "resume_id", "jd_id",
    "attempt", "elapsed_ms", "finish_reason", "max_tokens", "timeout_seconds",
    "message_count", "prompt_chars", "response_chars", "raw_text_chars",
    "answer_chars", "question_chars", "validation_error_count",
})


def _format_metadata(metadata: dict[str, Any] | None) -> str:
    return json.dumps({key: value for key, value in (metadata or {}).items()
                       if key in _LOG_METADATA_KEYS}, ensure_ascii=False, default=str)


def log_llm_prompt(task: str, prompt: str, metadata: dict[str, Any] | None = None) -> None:
    logging.getLogger("backend.llm").info(
        "LLM prompt | task=%s | chars=%s | metadata=%s", task, len(prompt), _format_metadata(metadata))


def log_llm_request(task: str, metadata: dict[str, Any] | None = None) -> None:
    logging.getLogger("backend.llm").info(
        "LLM request start | task=%s | metadata=%s", task, _format_metadata(metadata))


def log_llm_response(task: str, response: str, metadata: dict[str, Any] | None = None) -> None:
    logging.getLogger("backend.llm").info(
        "LLM response | task=%s | chars=%s | metadata=%s", task, len(response), _format_metadata(metadata))


def log_llm_error(task: str, error: Exception, metadata: dict[str, Any] | None = None) -> None:
    logging.getLogger("backend.llm").warning(
        "LLM error | task=%s | metadata=%s | error_type=%s | status=%s",
        task, _format_metadata(metadata), type(error).__name__, getattr(error, "status_code", None))


def log_llm_validation_error(task: str, errors: Any, metadata: dict[str, Any] | None = None) -> None:
    logging.getLogger("backend.llm").warning(
        "LLM validation error | task=%s | metadata=%s | count=%s",
        task, _format_metadata(metadata), len(errors) if isinstance(errors, list) else 1)
