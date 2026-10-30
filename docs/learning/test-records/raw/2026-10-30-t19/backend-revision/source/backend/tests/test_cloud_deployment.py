import logging

from fastapi.testclient import TestClient

from backend.app import app
from backend import logging_config


def test_health_probe_returns_json_without_auth_or_runtime_secrets(monkeypatch):
    monkeypatch.setenv("CLOUDBASE_APIKEY", "private-cloudbase-key")

    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_application_logs_reach_stdout_once_after_repeated_setup(tmp_path, monkeypatch, capsys):
    root = logging.getLogger()
    llm = logging.getLogger("backend.llm")
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(llm, "handlers", [])
    monkeypatch.setattr(logging_config, "LOG_DIR", tmp_path)
    try:
        logging_config.setup_logging()
        logging_config.setup_logging()
        logging.getLogger("backend.cloud_deployment").info("cloud-log-probe")

        assert capsys.readouterr().out.count("cloud-log-probe") == 1
        assert "cloud-log-probe" in (tmp_path / "backend.log").read_text()
    finally:
        for handler in root.handlers + llm.handlers:
            handler.close()
