"""Deterministic external model; execution, SQL, Redis and checkpoints are real."""
from backend.agent_runtime import factory
from backend.tests.agent_fixtures import DraftModel
from backend.worker import app

factory.model_for_user = lambda user_id: DraftModel()


@app.task(name='redis_test.record_usage')
def record_usage(user_id):
    from backend.services.llm_settings import record_llm_usage
    record_llm_usage(user_id=user_id, task='real-worker-fixture', model='deterministic',
                     base_url='', prompt_tokens=20, completion_tokens=5, total_tokens=25)
