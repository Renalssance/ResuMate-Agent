"""Browser-test API entrypoint: only the external LLM HTTP transport is replaced."""
import json
from collections import defaultdict

import httpx
from openai import OpenAI
from backend.agents import harness

calls = defaultdict(int)


def model_response(request: httpx.Request) -> httpx.Response:
    if request.method != 'POST' or not request.url.path.endswith('/chat/completions'):
        raise AssertionError(f'Unexpected external model request: {request.method} {request.url.path}')
    payload = json.loads(request.content)
    prompt = payload['messages'][1]['content']
    calls[prompt] += 1
    # One complete harness call fails, allowing the real page's retry to be exercised.
    if 'E2E_RETRY_PARSE' in prompt and calls[prompt] <= 3:
        return httpx.Response(503, json={'error': {'message': 'Synthetic model temporarily unavailable', 'type': 'server_error'}})
    content = {
        'job_title': 'API 工程师', 'summary': '负责 API 与数据库设计。',
        'responsibilities': ['实现接口与数据模型'],
        'criteria': [{'criterion_id': 'api', 'name': 'API 设计', 'description': '具备接口开发经历',
                      'importance': 'must', 'weight': 100, 'evidence_query': 'API 数据库 设计'}],
        'interview_focus': ['接口设计'],
    }
    return httpx.Response(200, json={
        'id': 'browser-parse', 'object': 'chat.completion', 'created': 1,
        'model': payload['model'],
        'choices': [{'index': 0, 'finish_reason': 'stop',
                     'message': {'role': 'assistant', 'content': json.dumps(content, ensure_ascii=False)}}],
        'usage': {'prompt_tokens': 25, 'completion_tokens': 30, 'total_tokens': 55},
    })


def fixture_client(**kwargs):
    return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(model_response)))


harness.OpenAI = fixture_client

from backend.app import app  # noqa: E402,F401
