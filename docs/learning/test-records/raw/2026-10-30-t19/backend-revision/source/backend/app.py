from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from anyio import to_thread
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from pathlib import Path
import os
import logging
import time

from backend.logging_config import setup_logging
from backend.routes import api as api_module
from backend.db.database import engine, init_db
from backend.infrastructure import redis_client
from backend.middleware.rate_limit import RedisRateLimiter
from backend.services import realtime_bus

setup_logging()
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
FRONTEND_STATIC_DIR = FRONTEND_DIR / "dist" if (FRONTEND_DIR / "dist").exists() else FRONTEND_DIR

# Bearer-token clients do not require credentialed cookies.
DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404 and scope["method"] in {"GET", "HEAD"} and not Path(path).suffix:
                return await super().get_response("index.html", scope)
            raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Startup: initializing database")
    init_db()
    resources = redis_client.create_async_redis_resources()
    try:
        redis_client.init_sync_redis()
        app.state.redis = resources
        app.state.rate_limiter = RedisRateLimiter(resources.commands, resources.namespace)
        hints = realtime_bus.InterviewHints(resources.commands, resources.notifications, resources.namespace)
        app.state.interview_hints = hints
        try:
            await hints.start()
            logger.info("Startup: database and Redis resources initialized")
            yield
        finally:
            await hints.aclose()
    finally:
        try:
            await resources.aclose()
        finally:
            redis_client.close_sync_redis()


def create_app() -> FastAPI:
    logger.info("Creating FastAPI app")
    app = FastAPI(title="Resume Interview Engine API", lifespan=lifespan)

    @app.get("/healthz", include_in_schema=False)
    async def health():
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def ready():
        def check_sql():
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        try:
            await to_thread.run_sync(check_sql)
            await app.state.redis.commands.ping()
        except Exception:
            return JSONResponse({"status": "not_ready"}, status_code=503)
        return {"status": "ready"}

    origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",") if origin.strip()]
    if "*" in origins:
        raise ValueError("CORS_ORIGINS must list explicit origins, not *")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # No-cache middleware for development
    @app.middleware("http")
    async def _request_logging_and_no_cache(request, call_next):
        start_time = time.perf_counter()
        path = request.url.path or ""
        logger.info(
            "Request start | method=%s path=%s client=%s",
            request.method,
            path,
            request.client.host if request.client else "",
        )
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.exception("Request failed | method=%s path=%s duration_ms=%s", request.method, path, duration_ms)
            raise
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        logger.info(
            "Request end | method=%s path=%s status=%s duration_ms=%s",
            request.method,
            path,
            response.status_code,
            duration_ms,
        )
        path = request.url.path or ""
        if path == "/" or path.endswith((".html", ".js", ".css")):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    app.include_router(api_module.router)

    # serve frontend static files at root
    if FRONTEND_STATIC_DIR.exists():
        app.mount("/", SPAStaticFiles(directory=str(FRONTEND_STATIC_DIR), html=True), name="static")

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", 8000)))
