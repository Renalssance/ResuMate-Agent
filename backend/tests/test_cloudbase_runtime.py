import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.db.database import Base
from backend.db.models import User, UserLlmSettings
from backend.schemas.settings import LlmSettingsUpdate
from backend.services.llm_settings import env_llm_settings, resolve_effective_llm_settings, save_llm_settings
from backend.vector.embedding import EmbeddingService


@pytest.fixture
def cloud_env(monkeypatch):
    monkeypatch.setenv("CLOUDBASE_ENV_ID", "test-cloud-env")
    monkeypatch.setenv("CLOUDBASE_APIKEY", "cloud-server-key")
    monkeypatch.setenv("LLM_MODEL", "configured-model")
    monkeypatch.setenv("OPENAI_API_KEY", "external-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://external-provider.example/v1")


def test_cloud_deployment_keeps_configured_model_credentials_and_endpoint(cloud_env):
    settings = env_llm_settings()
    assert settings.api_key == "external-key"
    assert settings.base_url == "https://external-provider.example/v1"
    assert settings.model == "configured-model"


def test_cloud_user_can_save_and_use_their_own_model_configuration(cloud_env):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(username="cloud-user", password_hash="unused", role="user")
        db.add(user)
        db.flush()
        db.add(UserLlmSettings(user_id=user.id, api_key="saved-external-key", base_url="https://external.example/v1", model="chosen-model"))
        db.commit()
        settings = resolve_effective_llm_settings(user.id, db)
        assert settings.api_key == "saved-external-key"
        assert settings.base_url == "https://external.example/v1"
        assert settings.model == "chosen-model"
        saved = save_llm_settings(user.id, LlmSettingsUpdate(base_url="https://custom.example/v1", api_key="custom-key", model="custom-model"), db)
        assert saved.base_url == "https://custom.example/v1"
        assert saved.model == "custom-model"
        assert resolve_effective_llm_settings(user.id, db).api_key == "custom-key"
    engine.dispose()


def test_cloud_embedding_preserves_existing_provider_and_model(cloud_env, monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "qwen")
    monkeypatch.setenv("EMBEDDING_MODEL", "external-embedding-model")
    service = EmbeddingService()
    assert service.provider == "qwen"
    assert service.model_name == "external-embedding-model"


def test_chat_interview_tool_uses_configured_model(cloud_env, monkeypatch):
    from backend.agent import interview_tools

    calls = []
    monkeypatch.setattr(interview_tools, "init_chat_model", lambda **kwargs: calls.append(kwargs) or object())
    assert interview_tools._get_llm() is not None
    assert calls[0]["api_key"] == "external-key"
    assert calls[0]["base_url"] == "https://external-provider.example/v1"
    assert calls[0]["model"] == "configured-model"


def test_cloud_chat_stream_calls_configured_endpoint_with_configured_key(cloud_env, monkeypatch):
    import httpx
    from langchain.chat_models import init_chat_model
    from sqlalchemy.orm import sessionmaker
    from backend.agent import agent

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        user = User(username="stream-user", password_hash="unused", role="user")
        db.add(user)
        db.flush()
        db.add(UserLlmSettings(user_id=user.id, api_key="external-key", base_url="https://external-provider.example/v1", model="configured-model"))
        db.commit()
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, text='data: {"id":"x","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"ok"},"finish_reason":null}]}\n\ndata: [DONE]\n\n')

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(agent, "SessionLocal", sessions)
        monkeypatch.setattr(agent, "create_agent", lambda **kwargs: object())
        monkeypatch.setattr(agent, "init_chat_model", lambda **kwargs: init_chat_model(**kwargs, http_client=client))
        _, model, _, _ = agent.create_agent_with_interview_tools("stream-user")
        assert list(model.stream("hello"))
    assert requests[0].headers["authorization"] == "Bearer external-key"
    assert requests[0].url.host == "external-provider.example"
    engine.dispose()


def test_cloud_runtime_rejects_ephemeral_sqlite(cloud_env):
    from backend.cloudbase import validate_runtime

    with pytest.raises(RuntimeError, match="MySQL"):
        validate_runtime("sqlite:///data/resumate.db")


def test_cloud_runtime_requires_its_own_key_instead_of_external_fallback(cloud_env, monkeypatch):
    from backend.cloudbase import validate_runtime

    monkeypatch.delenv("CLOUDBASE_APIKEY")
    with pytest.raises(RuntimeError, match="CLOUDBASE_APIKEY"):
        validate_runtime("mysql://user:password@172.17.0.11:3306/dev-d0g73fv8v22380036")


def test_mysql_connection_string_selects_installed_driver_and_unicode():
    from backend.db.database import build_engine

    engine = build_engine("mysql://user:password@172.17.0.11:3306/dev-d0g73fv8v22380036")
    assert engine.url.drivername == "mysql+pymysql"
    assert engine.url.host == "172.17.0.11"
    assert engine.url.database == "dev-d0g73fv8v22380036"
    assert engine.url.query["charset"] == "utf8mb4"
    engine.dispose()


def test_mysql_schema_supports_long_document_and_chat_text():
    from sqlalchemy.schema import CreateTable
    from sqlalchemy.dialects import mysql
    from backend.db.models import Resume, JobDescription, ChatMessage

    for model in (Resume, JobDescription, ChatMessage):
        ddl = str(CreateTable(model.__table__).compile(dialect=mysql.dialect()))
        assert "LONGTEXT NOT NULL" in ddl
