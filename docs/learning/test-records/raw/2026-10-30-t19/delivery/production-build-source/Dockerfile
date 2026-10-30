FROM node:24-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.12.5 AS uv

FROM python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8000
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-cache --locked --no-dev --no-install-project --extra ocr \
    && python -c "from rapidocr_onnxruntime import RapidOCR" \
    && python -m playwright install --with-deps chromium \
    && apt-get install -y --no-install-recommends fonts-noto-cjk=1:20220127+repack1-1 \
    && rm -rf /var/lib/apt/lists/*
COPY backend/ ./backend/
COPY --from=frontend /build/frontend/dist/ ./frontend/dist/
RUN mkdir -p /app/data/documents /app/data/exports /app/log
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ['PORT'] + '/healthz', timeout=3)"
# SQL persists Run progress/events; durable execution requires the separate worker.
CMD ["sh", "-c", "exec uvicorn backend.app:app --host 0.0.0.0 --port \"$PORT\" --workers 1"]
