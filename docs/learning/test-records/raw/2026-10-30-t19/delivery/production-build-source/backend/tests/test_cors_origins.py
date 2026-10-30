import pytest
from fastapi.testclient import TestClient
from backend.app import create_app


@pytest.mark.parametrize('setting,origin,allowed', [
    (None, 'http://localhost:5173', True), (None, 'http://127.0.0.1:5173', True),
    (None, 'https://untrusted.example', False),
    (' https://resumate.example , http://localhost:5173 ', 'https://resumate.example', True),
    ('https://resumate.example', 'https://untrusted.example', False),
])
def test_explicit_cors_preflight(setting, origin, allowed, monkeypatch):
    monkeypatch.delenv('CORS_ORIGINS', raising=False)
    if setting is not None:
        monkeypatch.setenv('CORS_ORIGINS', setting)
    client = TestClient(create_app())
    response = client.options('/api/documents', headers={'origin': origin,
        'access-control-request-method': 'POST', 'access-control-request-headers': 'authorization,content-type'})
    assert response.status_code == (200 if allowed else 400)
    assert response.headers.get('access-control-allow-origin') == (origin if allowed else None)
    assert 'access-control-allow-credentials' not in response.headers
    client.close()


def test_wildcard_is_rejected_with_actionable_configuration_error(monkeypatch):
    monkeypatch.setenv('CORS_ORIGINS', '*')
    with pytest.raises(ValueError, match='CORS_ORIGINS'):
        create_app()
