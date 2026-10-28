"""CloudBase deployment requirements; local development keeps its existing setup."""
import os

from sqlalchemy.engine import make_url


def validate_runtime(database_url: str) -> None:
    if not os.getenv("CLOUDBASE_ENV_ID"):
        return
    if make_url(database_url).get_backend_name() != "mysql":
        raise RuntimeError("CloudBase deployment requires MySQL; container SQLite is not persistent")
    for name in ("CLOUDBASE_APIKEY", "JWT_SECRET_KEY"):
        if not os.getenv(name, "").strip():
            raise RuntimeError(f"CloudBase requires {name}")
