# Dashboard + API in one container:  docker build -t codebase-intelligence . && docker run -p 8000:8000 -v ci-data:/data codebase-intelligence
FROM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ripgrep && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY backend/ ./backend/
RUN cd backend && uv sync --all-packages --no-dev --frozen
COPY --from=ui /ui/dist ./ui
ENV CI_DATA_DIR=/data PATH="/app/backend/.venv/bin:$PATH"
VOLUME /data
EXPOSE 8000
# Local mode is for one trusted user. For shared hosts set CI_MODE=server, CI_API_KEY and CI_PROJECT_ROOTS (see .env.example).
CMD ["ci", "serve", "--host", "0.0.0.0", "--port", "8000", "--ui", "/app/ui"]
