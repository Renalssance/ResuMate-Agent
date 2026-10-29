"""One prefork execution slot; SQL is authoritative, Redis only delivers IDs."""
import os
from celery import Celery
from celery.signals import worker_process_init

app = Celery('resumate', broker=os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/0'),
             include=['backend.worker_tasks'])
app.conf.update(
    task_serializer='json', accept_content=['json'], task_ignore_result=True,
    task_acks_late=True, task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1, worker_concurrency=1,
    broker_connection_timeout=2, task_publish_retry=False,
    broker_transport_options={'visibility_timeout': 3600, 'socket_timeout': 2,
                              'socket_connect_timeout': 2, 'retry_on_timeout': False},
    visibility_timeout=3600,
    beat_schedule={'recover-runs': {'task': 'resumate.recover_runs', 'schedule': 15.0}},
)


@worker_process_init.connect
def reset_connection_pool(**kwargs):
    from backend.db.database import engine
    engine.dispose(close=False)
