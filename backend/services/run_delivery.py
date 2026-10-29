"""Best-effort notification AFTER SQL commit; the scanner supplies durable retry."""
import logging
import os
from kombu.exceptions import OperationalError
from backend.worker import app

logger = logging.getLogger(__name__)


def publish_run(run_id: str) -> bool:
    if not os.getenv('REDIS_URL'):
        return False
    try:
        app.send_task('resumate.execute_run', args=[run_id], retry=False)
        return True
    except (OperationalError, OSError):
        logger.warning('Run %s remains queued; broker unavailable', run_id)
        return False
