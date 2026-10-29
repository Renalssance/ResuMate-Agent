"""Deterministic model fixtures; never imported by the production worker."""
import json

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
        elif self.ask and names.count('get_application_context') == 1:
            # Re-read the same fixed input plus this Run's newly persisted answer ID.
            name, args = 'get_application_context', {}
        elif names.count('create_resume_draft') < (2 if self.repeat else 1):
            context = json.loads(next(m.content for m in reversed(replies) if m.name == 'get_application_context'))
            name, args = 'create_resume_draft', {'changes': self.draft_changes(context)}
        else:
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content='请审阅草稿'))])
        message = AIMessage(content='', tool_calls=[{'name': name, 'args': args,
                                                      'id': f'call-{len(replies)}', 'type': 'tool_call'}])
        return ChatResult(generations=[ChatGeneration(message=message)])

    def draft_changes(self, context):
        resume = context['resume']
        structured = resume['structured']
        field = 'self_summary' if 'self_summary' in structured else 'summary'
        refs = [{'kind': 'resume', 'resumeId': resume['id'],
                 'inputVersion': resume['inputVersion'], 'section': '/' + field,
                 'sourceRefs': structured.get('source_refs', [])}]
        if self.bad_fact:
            refs = [{'kind': 'profile_fact', 'factId': 'missing', 'revision': 1}]
        elif context.get('applicantAnswers'):
            refs.append({'kind': 'applicant_answer', 'actionId': context['applicantAnswers'][-1]['actionId']})
        return [{'section': '/' + field, 'before': structured[field],
                 'after': structured[field] + '。负责 API 和数据库设计。',
                 'reason': '突出原简历中的接口开发经历，具体内容仍需本人核对。',
                 'fact_refs': refs, 'requires_input': False}]
