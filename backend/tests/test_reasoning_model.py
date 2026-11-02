import json
import httpx
from backend.agent_runtime.reasoning_model import ReasoningChatOpenAI as ChatOpenAI


def test_provider_reasoning_survives_stream_conversion():
    chunks = [
        {'choices': [{'index': 0, 'delta': {'role': 'assistant', 'reasoning_content': '先统计'}, 'finish_reason': None}]},
        {'choices': [{'index': 0, 'delta': {'reasoning_content': '再分析'}, 'finish_reason': None}]},
        {'choices': [{'index': 0, 'delta': {'content': '岗位倾向'}, 'finish_reason': None}]},
        {'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]},
    ]
    def respond(request):
        return httpx.Response(200, headers={'content-type': 'text/event-stream'},
            text=''.join('data: ' + json.dumps(chunk) + '\n\n' for chunk in chunks) + 'data: [DONE]\n\n')
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        model = ChatOpenAI(model='deepseek-v4.1-flash', api_key='test', http_client=client)
        output = list(model.stream('分析投递'))
    assert ''.join(chunk.additional_kwargs.get('reasoning_content', '') for chunk in output) == '先统计再分析'
    assert ''.join(chunk.content for chunk in output) == '岗位倾向'
