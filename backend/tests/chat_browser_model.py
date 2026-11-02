"""Deterministic browser model; exercises real chat tools, never production imports."""
import json
import re
import time

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from backend.tests.agent_fixtures import DraftModel


class BrowserCareerModel(DraftModel):
    def _generate(self, messages, **kwargs):
        time.sleep(.3)
        start = next(i for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], HumanMessage))
        prompt = messages[start].content
        replies = [message for message in messages[start:] if isinstance(message, ToolMessage)]
        task = re.search(r'任务 ([0-9a-f-]{36})', prompt)
        if not replies:
            if task:
                name, args = 'get_task', {'task_id': task.group(1)}
            else:
                selected = json.loads(prompt.split('当前所选资料：')[-1])
                name, args = 'start_task', {'kind': 'tailoring', 'resume_id': selected['resumeId'], 'jd_id': selected['jdId']}
        elif len(replies) == 1 and task and '补充：' in prompt:
            snapshot = json.loads(replies[-1].content)
            if snapshot.get('actions'):
                name, args = 'answer_task', {'task_id': task.group(1), 'action_id': snapshot['actions'][0]['actionId'],
                    'answers': {'answer': prompt.split('补充：')[1].split('\n\n当前所选资料：')[0]}}
            else:
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content='任务当前没有待补充问题。'))])
        else:
            result = json.loads(replies[-1].content)
            text = result.get('error') or ('任务已受理，可以在卡片中查看进度。' if result.get('status') == 'queued' else '已读取任务结果。')
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content='', tool_calls=[{
            'name': name, 'args': args, 'id': f'browser-{len(messages)}', 'type': 'tool_call'}]))])
