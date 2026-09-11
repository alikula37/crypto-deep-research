# syntax=docker/dockerfile:1

# ---- 1) Web UI derleme ----
FROM node:22-alpine AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci || npm install
COPY web/ ./
RUN npm run build

# ---- 2) Python calisma ortami ----
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    CDR_DATA_DIR=/data \
    HF_HOME=/data/hf \
    FASTEMBED_CACHE_PATH=/data/fastembed

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --no-dev --frozen

# Web UI'i statik olarak sunmak icin derlenmis dosyalari kopyala
COPY --from=web /app/web/dist ./web/dist

RUN mkdir -p /data/reports /data/prompts /data/vectors

EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["/app/.venv/bin/uvicorn", "crypto_deep_research.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
