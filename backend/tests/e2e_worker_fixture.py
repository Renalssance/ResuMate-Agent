"""Browser-test worker entrypoint; only the model is replaced, never the graph/tools."""
import time

from backend.agent_runtime import factory
from backend.tests.agent_fixtures import DraftModel
from backend.worker import app  # Celery imports this entrypoint in an independent process.


class BrowserDraftModel(DraftModel):
    ask: bool = True

    def _generate(self, messages, **kwargs):
        # A short deterministic call window makes cancellation while running observable.
        time.sleep(0.7)
        result = super()._generate(messages, **kwargs)
        message = result.generations[0].message
        for call in message.tool_calls:
            if call['name'] == 'create_resume_draft':
                call['args']['content'] = {
                    'summary': 'API development。' + '负责示例项目中的 API 和数据库设计，与团队核对接口需求并维护数据结构。' * 8,
                    'work_experience': [{'company': '示例团队', 'title': 'API 工程师',
                                         'description': '将实际项目职责整理为待本人核对的草稿。' * 8}],
                }
        return result


factory.model_for_user = lambda user_id: BrowserDraftModel()
