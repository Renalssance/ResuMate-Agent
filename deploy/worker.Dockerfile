FROM public.ecr.aws/docker/library/python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PATH="/app/.venv/bin:$PATH"
RUN pip install --no-cache-dir uv==0.12.5
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/ ./backend/
RUN mkdir -p /app/data/agent
CMD ["celery", "-A", "backend.worker:app", "worker", "--loglevel=INFO", "--concurrency=1"]
