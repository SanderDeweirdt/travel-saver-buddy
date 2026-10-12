# One image for both Railway services; the start command differs (see railway.*.json).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY config.yaml ./
COPY deploy ./deploy
RUN uv sync --frozen --no-dev

# Default: the dashboard. The scanner service overrides this with `sh deploy/cron.sh`.
CMD ["mmscan", "web"]
