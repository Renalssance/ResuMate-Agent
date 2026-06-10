from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os
import logging
import time

from backend.logging_config import setup_logging
from backend.routes import api as api_module
from backend.db.database import init_db

setup_logging()
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

# CORS 配置：从环境变量读取允许的源列表
# 开发环境使用 "*"，生产环境必须指定具体域名
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")


def create_app() -> FastAPI:
    logger.info("Creating FastAPI app")
    app = FastAPI(title="Resume Interview Engine API")

    @app.on_event("startup")
    async def _startup_init_db():
        logger.info("Startup: initializing database")
        init_db()
        logger.info("Startup: database initialized")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
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
    if FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", 8000)))
