from backend.app import app as canonical_app
from backend.main import app as container_app
from fastapi.testclient import TestClient


def test_container_entrypoint_uses_the_canonical_application():
    assert container_app is canonical_app
    assert container_app.title == "Resume Interview Engine API"

    paths = {route.path for route in container_app.routes}
    assert "/auth/login" in paths
    assert "/api/documents" in paths
    assert "/api/runs" in paths
    assert "/api/followups/analyze" in paths


def test_public_config_exposes_llm_model(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "qwen3.7-plus")

    response = TestClient(canonical_app).get("/api/config")

    assert response.status_code == 200
    assert response.json() == {"llm_model": "qwen3.7-plus"}


def test_public_config_returns_empty_llm_model_when_unconfigured(monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)

    response = TestClient(canonical_app).get("/api/config")

    assert response.status_code == 200
    assert response.json() == {"llm_model": ""}
