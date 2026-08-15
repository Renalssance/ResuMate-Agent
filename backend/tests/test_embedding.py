from types import SimpleNamespace

import pytest

from backend.vector.embedding import EmbeddingService


class FakeEmbeddingsApi:
    def __init__(self):
        self.calls = []

    def create(self, *, model, input):
        self.calls.append({"model": model, "input": input})
        return SimpleNamespace(
            data=[
                SimpleNamespace(index=1, embedding=[0.0, 1.0]),
                SimpleNamespace(index=0, embedding=[1.0, 0.0]),
            ]
        )


def test_remote_embedding_batches_and_restores_response_order(monkeypatch):
    api = FakeEmbeddingsApi()
    client = SimpleNamespace(embeddings=api)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("EMBEDDING_MODEL", "embed-model")
    service = EmbeddingService(client=client)

    assert service.embed_many(["first", "second"]) == [[1.0, 0.0], [0.0, 1.0]]
    assert api.calls == [{"model": "embed-model", "input": ["first", "second"]}]


def test_remote_embedding_requires_an_api_key_without_injected_client(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="EMBEDDING_API_KEY or OPENAI_API_KEY"):
        EmbeddingService().embed("text")


def test_local_embedding_reports_optional_install_command(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    service = EmbeddingService()
    monkeypatch.setattr(service, "_load_local_model", lambda: (_ for _ in ()).throw(ImportError()))
    with pytest.raises(RuntimeError, match="uv sync --extra local-embeddings"):
        service.embed("text")
