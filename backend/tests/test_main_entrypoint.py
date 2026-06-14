from backend.app import app as canonical_app
from backend.main import app as container_app


def test_container_entrypoint_uses_the_canonical_application():
    assert container_app is canonical_app
    assert container_app.title == "Resume Interview Engine API"

    paths = {route.path for route in container_app.routes}
    assert "/auth/login" in paths
    assert "/api/documents" in paths
    assert "/api/runs" in paths
    assert "/api/followups/analyze" in paths
