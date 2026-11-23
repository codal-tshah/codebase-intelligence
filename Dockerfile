# Dashboard + API in one container.
#   docker build -t codebase-intelligence .
#   docker run -p 8000:8000 -v ci-data:/data -v "$PWD":/repos/app:ro codebase-intelligence
#   docker exec <container> ci analyze /repos/app        # or use the dashboard's "Add a repository"
# Local mode is for one trusted user. For shared hosts set CI_MODE=server, CI_API_KEY and
# CI_PROJECT_ROOTS (see .env.example and docs/SECURITY.md).

# ---- dashboard build ---------------------------------------------------------------------------
FROM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- runtime -----------------------------------------------------------------------------------
FROM python:3.12-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ripgrep ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# Pinned (not :latest) so builds are reproducible; bump together with backend/uv.lock.
COPY --from=ghcr.io/astral-sh/uv:0.11.22 /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1
WORKDIR /app/backend
# 1) Third-party dependencies from the lockfile + workspace manifests only, so this (slow) layer
#    is reused across code changes. 2) Then the workspace sources and the workspace packages.
COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/packages/core/pyproject.toml packages/core/
COPY backend/packages/parsers/pyproject.toml packages/parsers/
COPY backend/packages/adapters/django/pyproject.toml packages/adapters/django/
COPY backend/packages/adapters/typescript/pyproject.toml packages/adapters/typescript/
COPY backend/packages/indexer/pyproject.toml packages/indexer/
COPY backend/packages/ai/pyproject.toml packages/ai/
COPY backend/packages/security/pyproject.toml packages/security/
COPY backend/apps/cli/pyproject.toml apps/cli/
COPY backend/apps/api/pyproject.toml apps/api/
COPY backend/apps/mcp/pyproject.toml apps/mcp/
RUN uv sync --all-packages --no-dev --frozen --no-install-workspace
COPY backend/packages/ ./packages/
COPY backend/apps/ ./apps/
RUN uv sync --all-packages --no-dev --frozen

COPY --from=ui /ui/dist /app/ui

# Unprivileged user; /data holds the SQLite stores and git clones.
RUN useradd --create-home --uid 10001 ci && mkdir -p /data && chown ci:ci /data
USER ci
ENV CI_DATA_DIR=/data \
    PATH="/app/backend/.venv/bin:$PATH"
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"
CMD ["ci", "serve", "--host", "0.0.0.0", "--port", "8000", "--ui", "/app/ui"]
