FROM public.ecr.aws/docker/library/python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PATH="/app/.venv/bin:$PATH"
RUN pip install --no-cache-dir uv==0.12.5
COPY pyproject.toml uv.lock README.md ./
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources
RUN uv sync --locked --no-dev --no-install-project \
    && python -m playwright install --with-deps chromium \
    && apt-get install -y --no-install-recommends fonts-noto-cjk=1:20220127+repack1-1 \
    && rm -rf /var/lib/apt/lists/*
COPY backend/ ./backend/
RUN mkdir -p /app/data/agent /app/data/exports
CMD ["celery", "-A", "backend.worker:app", "worker", "--loglevel=INFO", "--concurrency=1"]
