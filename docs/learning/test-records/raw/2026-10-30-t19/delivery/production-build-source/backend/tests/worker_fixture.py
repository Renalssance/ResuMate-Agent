"""Compose-test worker only: deterministic model + crash window AFTER SQL commit."""
from pathlib import Path
import os
import time
from backend.worker import app
from backend.agent_runtime import factory, tools
from backend.tests.agent_fixtures import DraftModel

factory.model_for_user = lambda user_id: DraftModel()
_save_draft = tools.save_draft


def save_then_pause(*args, **kwargs):
    version_id = _save_draft(*args, **kwargs)
    root = Path(os.environ['AGENT_STATE_DIR'])
    if (root / 'pause_after_commit').exists():
        (root / 'artifact_committed').touch()
        deadline = time.monotonic() + 120
        while (root / 'pause_after_commit').exists() and time.monotonic() < deadline:
            time.sleep(0.1)
    return version_id


tools.save_draft = save_then_pause
