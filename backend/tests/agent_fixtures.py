"""Deterministic model fixtures; never imported by the production worker."""
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class DraftModel(BaseChatModel):
    model_name: str = 'openai:resumate-contract'
    ask: bool = False
    bad_fact: bool = False
    repeat: bool = False

    @property
    def _llm_type(self):
        return 'resumate-test'

    def bind_tools(self, tools, **kwargs):
        names = {t.name if hasattr(t, 'name') else t['function']['name'] for t in tools}
        assert 'execute' not in names and 'task' not in names
        return self

    def _generate(self, messages, **kwargs):
        replies = [m for m in messages if isinstance(m, ToolMessage)]
        names = [m.name for m in replies]
        if 'get_application_context' not in names:
            name, args = 'get_application_context', {}
        elif self.ask and 'ask_applicant' not in names:
            name, args = 'ask_applicant', {'question': '你负责什么工作？'}
        elif names.count('create_resume_draft') < (2 if self.repeat else 1):
            name, args = 'create_resume_draft', {'content': {'summary': 'API development'},
                                               'fact_refs': ['missing'] if self.bad_fact else []}
        else:
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content='请审阅草稿'))])
        message = AIMessage(content='', tool_calls=[{'name': name, 'args': args,
                                                      'id': f'call-{len(replies)}', 'type': 'tool_call'}])
        return ChatResult(generations=[ChatGeneration(message=message)])
