# Runbook

*Last verified against code: `backend/packages/core/src/ci_core/settings.py`, `.env.example`, `CONTRIBUTING.md`, `backend/packages/core/src/ci_core/config.py`, `CHANGELOG.md`.*

## Install

```bash
cd backend && uv sync --all-packages --group dev
cd ../frontend && npm ci
```

## Run

| Mode | Command | URLs |
| --- | --- | --- |
| API only | `uv run ci serve` | API `http://127.0.0.1:8000` |
| API + built UI | `uv run ci serve --ui ../frontend/dist` | Combined `:8000` |
| Dev UI | `uv run ci serve` + `npm run dev` | UI `:5173`, API `:8000` |

Restart `ci serve` after backend code changes (no auto-reload). Frontend HMR does not reload the API.

## Index a project

```bash
uv run ci analyze /path/to/repo
# or POST /projects/analyze from dashboard
```

Data directory: `CI_DATA_DIR` (default `~/.codebase-intelligence`).

Layout:

```
{CI_DATA_DIR}/
  audit.jsonl
  projects/{project_id}/
    index.db
    index.lock
    settings.json
    saved-views.json
    fingerprints.json
    ...
```

## Environment variables

See `.env.example` and `get_settings()` in `ci_core/settings.py`:

- `CI_MODE`, `CI_DATA_DIR`, `CI_API_KEY`, `CI_PROJECT_ROOTS`, `CI_CORS_ORIGINS`
- `CI_GITHUB_TOKEN` / `GITHUB_TOKEN` (private clone)
- `CI_ANALYZERS`, `CI_LOG_LEVEL`, `CI_LOG_JSON`
- `CI_AUTO_REFRESH_SECONDS` (API auto-refresh interval)
- `ALLOW_LLM`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_API_BASE`

## Re-index

Dashboard "Re-index", `POST /projects/{ref}/index`, or `ci analyze` with `--incremental` when fingerprints allow. Git hooks: `ci hook install`.

## Common failures

| Symptom | Check |
| --- | --- |
| 401 on API | Server mode: set `X-API-Key` / `CI_API_KEY` |
| Stale graph after code change | Re-index; restart API if handlers changed |
| Index refused | Another process holds `index.lock` |
| Private GitHub clone fails | `CI_GITHUB_TOKEN`; see `docs/private-repos.md` |
| Explore empty | View availability in `GET .../views`; need nodes of required types |

## Quality smoke

```bash
cd backend && uv run ruff check . && uv run mypy && uv run pytest -q
cd frontend && npm run typecheck
```
