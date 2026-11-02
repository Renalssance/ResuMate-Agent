from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from backend.db.database import Base

@pytest.fixture
def settings_db(monkeypatch):
    from backend.services import embedding_settings
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    monkeypatch.setattr(embedding_settings, 'SessionLocal', sessionmaker(engine))
    with Session(engine) as db:
        yield db
    engine.dispose()


def test_saved_key_is_visible_and_blank_keeps_it(settings_db):
    from backend.services.embedding_settings import save_settings, resolve_settings
    from backend.schemas.settings import EmbeddingSettingsUpdate
    result = save_settings(EmbeddingSettingsUpdate(provider='qwen', model='embed-test',
        base_url='https://embed.example/v1', api_key='private-key'), settings_db)
    assert result.has_api_key
    assert result.api_key == 'private-key'
    save_settings(EmbeddingSettingsUpdate(api_key=''), settings_db)
    assert resolve_settings(settings_db)['api_key'] == 'private-key'
    result = save_settings(EmbeddingSettingsUpdate(clear_api_key=True), settings_db)
    assert not result.has_api_key
    assert resolve_settings(settings_db)['api_key'] == ''


def test_rag_store_uses_saved_config_and_changes_without_restart(settings_db, monkeypatch, tmp_path):
    from backend.services.embedding_settings import save_settings
    from backend.schemas.settings import EmbeddingSettingsUpdate
    from backend.rag import get_rag_store
    monkeypatch.setenv('CHROMA_PATH', str(tmp_path / 'chroma'))
    monkeypatch.delenv('CLOUDBASE_ENV_ID', raising=False)
    save_settings(EmbeddingSettingsUpdate(provider='openai', model='first', base_url='https://embed.example/v1', api_key='key-1'), settings_db)
    first = get_rag_store().embedding_client
    assert first.model_name == 'first'
    assert str(first._remote_client().base_url) == 'https://embed.example/v1/'
    assert first._remote_client().api_key == 'key-1'
    save_settings(EmbeddingSettingsUpdate(model='second', api_key='key-2'), settings_db)
    second = get_rag_store().embedding_client
    assert second.model_name == 'second'
    assert second._remote_client().api_key == 'key-2'


from backend.tests.career_fixtures import career_engine, career_db
from backend.tests.test_agent_run_routes import run_client, headers


def test_embedding_routes_return_key_and_probe_only_synthetic_text(run_client, monkeypatch):
    from backend.vector.embedding import EmbeddingService
    response = run_client.put('/api/settings/embedding', headers=headers(), json={
        'provider': 'openai', 'api_key': 'secret-embedding-key',
        'base_url': 'https://embed.example/v1', 'model': 'embedding-model'})
    assert response.status_code == 200
    assert response.json()['api_key'] == 'secret-embedding-key'
    assert run_client.get('/api/settings/embedding', headers=headers()).json()['model'] == 'embedding-model'
    def probe(self, text):
        assert text == 'ResuMate connection test'
        assert self.model_name == 'embedding-model'
        assert self._settings['api_key'] == 'secret-embedding-key'
        return [1.0, 0.0]
    monkeypatch.setattr(EmbeddingService, 'embed', probe)
    response = run_client.post('/api/settings/embedding/test', headers=headers())
    assert response.json() == {'success': True, 'dimensions': 2}
    assert run_client.get('/api/settings/embedding').status_code == 401


def test_probe_failure_does_not_echo_provider_secrets(run_client, monkeypatch):
    from backend.vector.embedding import EmbeddingService
    def fail(*args):
        raise RuntimeError('provider echoed secret-123')
    monkeypatch.setattr(EmbeddingService, 'embed', fail)
    response = run_client.post('/api/settings/embedding/test', headers=headers())
    assert response.status_code == 400
    assert 'secret-123' not in response.text


def test_saved_local_model_is_reused_between_operations(monkeypatch):
    import sys
    from backend.vector.embedding import EmbeddingService
    models = []
    class Model:
        def __init__(self, name, device):
            models.append(self)
        def encode(self, texts, **kwargs):
            return [[1.0, 0.0] for _ in texts]
    monkeypatch.setitem(sys.modules, 'sentence_transformers', SimpleNamespace(SentenceTransformer=Model))
    settings = dict(provider='local', model='fixture-local-model', api_key='', base_url='')
    assert EmbeddingService(settings=settings).embed('first') == [1.0, 0.0]
    assert EmbeddingService(settings=settings).embed('second') == [1.0, 0.0]
    assert len(models) == 1
