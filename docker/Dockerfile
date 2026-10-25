# syntax=docker/dockerfile:1

# --- web: static export ------------------------------------------------------
FROM node:24-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- api ---------------------------------------------------------------------
FROM python:3.14-slim AS app
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY api/alembic.ini ./
COPY api/alembic/ ./alembic/
COPY api/app/ ./app/
COPY --from=web /web/out ./static
RUN useradd --system --uid 10001 vectana
USER vectana
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
