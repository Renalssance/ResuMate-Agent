import httpx
from backend.tests.career_fixtures import career_engine, career_db
from backend.tests.test_agent_run_routes import run_client, headers


def test_llm_probe_uses_saved_config_and_records_usage(run_client, monkeypatch):
    from backend.routes import settings
    run_client.put('/api/settings/llm', headers=headers(), json={
        'api_key': 'saved-test-key', 'model': 'saved-model', 'base_url': 'https://model.example/v1'})
    requests = []
    def respond(request):
        import json
        requests.append((request, json.loads(request.content)))
        return httpx.Response(200, json={'id': 'test', 'object': 'chat.completion', 'created': 0,
            'model': 'saved-model', 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'OK'}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 8, 'completion_tokens': 2, 'total_tokens': 10}})
    monkeypatch.setattr(settings, 'DefaultHttpxClient', lambda **kwargs:
        httpx.Client(transport=httpx.MockTransport(respond), **kwargs))
    response = run_client.post('/api/settings/llm/test', headers=headers())
    assert response.status_code == 200
    assert response.json()['success'] is True
    request, payload = requests[0]
    assert request.headers['authorization'] == 'Bearer saved-test-key'
    assert str(request.url) == 'https://model.example/v1/chat/completions'
    assert payload['model'] == 'saved-model'
    assert payload['messages'] == [{'role': 'user', 'content': 'Reply with OK.'}]
    dashboard = run_client.get('/api/settings/usage', headers=headers()).json()
    assert dashboard['total_tokens'] == 10
    assert dashboard['recent_calls'][0]['task'] == 'connection_test'
    assert run_client.post('/api/settings/llm/test').status_code == 401


def test_llm_probe_missing_configuration_and_provider_failure(run_client, monkeypatch):
    from backend.routes import settings
    assert run_client.post('/api/settings/llm/test', headers=headers()).status_code == 400
    run_client.put('/api/settings/llm', headers=headers(), json={
        'api_key': 'key', 'model': 'model', 'base_url': 'https://model.example/v1'})
    def fail(**kwargs):
        raise RuntimeError('provider secret')
    monkeypatch.setattr(settings, 'OpenAI', fail)
    response = run_client.post('/api/settings/llm/test', headers=headers())
    assert response.status_code == 400
    assert 'provider secret' not in response.text
