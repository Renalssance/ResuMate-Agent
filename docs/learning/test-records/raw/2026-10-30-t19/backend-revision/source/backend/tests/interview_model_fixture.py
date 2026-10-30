"""Deterministic provider boundary for the real interview SDK graph, never a handler stub."""
from copy import deepcopy
import json
import re
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


def _unpage(value):
    if isinstance(value, dict):
        if 'textChunks' in value and value.get('join') == '':
            return ''.join(value['textChunks'])
        return {key: _unpage(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_unpage(item) for item in value]
    return value


def _first_text(value, path=''):
    if isinstance(value, str) and value.strip():
        return path, value[:120]
    if isinstance(value, dict):
        for key, item in value.items():
            found = _first_text(item, f'{path}/{key}')
            if found:
                return found
    if isinstance(value, list):
        for index, item in enumerate(value):
            found = _first_text(item, f'{path}/{index}')
            if found:
                return found
    return None


class ScriptedInterviewModel(BaseChatModel):
    model_name: str = 'openai:interview-fixture'
    profile: dict = Field(default_factory=lambda: {'max_input_tokens': 64000})
    max_tokens: int = 4000
    modes: list[str] = Field(default_factory=lambda: ['follow_up', 'follow_up', 'new_topic'])
    long_question: bool = False
    before_generate: Any = None
    transform_step: Any = None
    calls: list[dict] = Field(default_factory=list)
    summaries: list[dict] = Field(default_factory=list)
    bound_tools: list[str] = Field(default_factory=list)
    contexts: dict = Field(default_factory=dict)
    pages: dict = Field(default_factory=dict)

    @property
    def _llm_type(self):
        return 'scripted-interview'

    def bind_tools(self, tools, **kwargs):
        self.bound_tools[:] = [getattr(item, 'name', None) or item['function']['name'] for item in tools]
        assert not {'execute', 'task'} & set(self.bound_tools)
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        system = '\n'.join(message.text for message in messages if message.type == 'system')
        summary = '必保留业务上下文（摘要调用）\n' in system
        marker = '必保留业务上下文（摘要调用）\n' if summary else '必保留业务上下文\n'
        required = json.loads(system.rsplit(marker, 1)[1])
        record = {'required': deepcopy(required), 'messages': [message.model_dump() for message in messages]}
        (self.summaries if summary else self.calls).append(record)
        if self.before_generate is not None:
            self.before_generate(required)
        if summary:
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content='已阅读冻结材料；继续依据原始文件和当前回答。'))])
        run_id = required['runId']
        tool_messages = [message for message in messages if isinstance(message, ToolMessage)]
        for message in tool_messages:
            if message.name == 'get_interview_context':
                value = json.loads(message.content)
                if value.get('format') != 'artifact_manifest':
                    self.contexts[run_id] = value
                else:
                    self.pages.setdefault(run_id, {'manifest': value['artifacts'], 'parts': {}})
        if run_id not in self.contexts and run_id not in self.pages:
            return self._tool('get_interview_context', {})
        if run_id not in self.contexts:
            page = self.pages[run_id]
            # Read all actual StateBackend pages, preserving exact concatenable source text.
            for descriptor in page['manifest']:
                path = descriptor['path']
                chunks = page['parts'].setdefault(path, {})
                for message in tool_messages:
                    if message.name != 'read_file':
                        continue
                    call = next((call for prior in messages if isinstance(prior, AIMessage)
                        for call in prior.tool_calls if call['id'] == message.tool_call_id), None)
                    if call and call['args']['file_path'] == path:
                        # SDK JSON reads retain plain JSON after a range header; any truncation
                        # notice precedes that header and is not a source line.
                        body = re.split(r'^@@ lines [^\n]*@@\n', message.content, maxsplit=1, flags=re.MULTILINE)[1]
                        chunks[call['args'].get('offset', 0)] = body
                offset = sum(len(chunk.splitlines()) for chunk in chunks.values())
                if offset < descriptor['lines']:
                    return self._tool('read_file', {'file_path': path, 'offset': offset, 'limit': 100})
            values = {descriptor['kind']: _unpage(json.loads('\n'.join(
                chunk for _offset, chunk in sorted(page['parts'][descriptor['path']].items()))))
                for descriptor in page['manifest']}
            self.contexts[run_id] = {'interviewId': required['interviewId'], 'expectedTurn': required['expectedTurn'],
                                   'source': values['source'], 'turns': values['turns'], 'memories': required['memories']}
        context = self.contexts[run_id]
        record['context'] = deepcopy(context)
        turn = context['expectedTurn']
        section, quote = _first_text(context['source']['structuredContent']['resume'])
        resume_ref = {'kind': 'resume', 'section': section, 'quote': quote}
        answer = next((row for row in context['turns'] if row['turnIndex'] == turn), None)
        ref = resume_ref if not turn else {'kind': 'answer', 'turnIndex': turn, 'quote': answer['answer'][:120]}
        mode = 'opening' if not turn else self.modes[(turn - 1) % len(self.modes)]
        step = {'feedback': None if not turn else {
            'summary': f'本轮回答提到了：{ref["quote"]}',
            'strengths': [{'text': '回答给出了明确的方法。', 'refs': [ref]}],
            'improvements': [{'text': '补充验证结果与失败处理的具体过程。', 'refs': [ref]}],
            'practiceFocus': '练习说明验证步骤与失败处理，不补造经历。'},
            'question': None if turn == 8 else {
                'text': f'请进一步说明「{ref["quote"]}」的具体过程。' if turn else f'请介绍「{quote}」的具体经历。',
                'mode': mode, 'refs': [ref if mode != 'new_topic' else resume_ref]}}
        if self.long_question and step['question']:
            step['question']['text'] += '请结合真实材料，按背景、行动和结果说明，缺少的数据直接说明尚未记录。' * 15
        if self.transform_step is not None:
            step = self.transform_step(deepcopy(step), deepcopy(context))
        record['step'] = deepcopy(step)
        return self._tool('InterviewStep', step)

    def _tool(self, name, args):
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content='', tool_calls=[
            {'id': f'interview-call-{len(self.calls)}', 'type': 'tool_call', 'name': name, 'args': args}]))])
