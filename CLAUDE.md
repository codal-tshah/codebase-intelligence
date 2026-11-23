# Claude Code — Codebase Intelligence

Local-first indexer: parsers and adapters build a SQLite knowledge graph per project; FastAPI, Typer CLI (`ci`), MCP, and a React dashboard read it. Optional LiteLLM chat uses `ci_security` redaction.

## Where things live

| Area | Path |
| --- | --- |
| Workspace root | `backend/pyproject.toml`, `backend/uv.lock` |
| Core graph | `backend/packages/core/src/ci_core/` (`insights.py`, `graph_algo.py`, `views/`, `db.py`) |
| Parsers / adapters | `backend/packages/parsers/`, `adapters/django/`, `adapters/typescript/` |
| Indexer | `backend/packages/indexer/` |
| AI tools | `backend/packages/ai/`, `backend/packages/security/` |
| API / CLI / MCP | `backend/apps/api/`, `apps/cli/`, `apps/mcp/` |
| UI | `frontend/src/` (Vite dev server `:5173`, `API = "/api"`) |
| Agent docs | `docs/ai/`, `.cursor/rules/` |

## Commands (verify with `--help`)

```bash
cd backend && uv sync --all-packages --group dev && cd ../frontend && npm ci
uv run ci analyze <path|url>    # index; private GitHub needs CI_GITHUB_TOKEN
uv run ci serve [--ui ../frontend/dist]   # :8000 — restart after backend edits
cd frontend && npm run dev      # :5173, proxies /api
```

Quality gates (same as [CONTRIBUTING.md](CONTRIBUTING.md)):

```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q
cd frontend && npm run lint && npm run format:check && npm run typecheck && npm test && npm run build
python scripts/check_ai_docs.py
```

Claude plugin/MCP: [integrations/README.md](integrations/README.md) (`uv run ci mcp`).

## Pitfalls

Do not restart a user's running `ci serve`. Indexing never mutates source repos. Concurrent index uses `projects/<id>/index.lock` (do not bypass). `TYPE_CHECKING` / lazy imports affect cycle suggestions after re-index (Django `ADAPTER_VERSION`).

## Documentation Maintenance Protocol:

- Docs are part of the change. A task that modifies behaviour is not done until the matching docs are updated in the same diff.
- Before finishing any task, run the change-to-doc map below, open each mapped file, and update every statement that your change made false. If nothing needs updating, say so explicitly in your final message ("docs checked: <files>, no change needed").
- Never document from memory. Re-read the code you changed and copy names, paths, signatures and commands from it.
- Add a line to `CHANGELOG.md` for user-visible changes, and to `docs/DECISIONS.md` for new dependencies or architectural decisions (one line of justification).
- If a doc and the code disagree, the code wins: fix the doc, and mention it.
- Do not create new top-level docs when an existing file owns the topic.

### Change-to-doc map

| If you change... | Update... |
| --- | --- |
| HTTP routes, request/response shapes, error format, auth | `docs/ai/api-reference.md`, `.cursor/rules/11-api-routes.mdc` if conventions change, `docs/user-guide.md` if user-visible |
| CLI commands or flags, MCP tools | `docs/ai/api-reference.md`, `README.md` quickstart, `integrations/README.md` mention only if it lists them |
| `NodeType`/`EdgeType`, node/edge `properties`, DB tables/columns, ids | `docs/ai/data-model.md`, `docs/architecture.md`, and bump the analyzer/adapter version (forces re-index) |
| Analyzer/parser/framework detection, role or layer rules | `docs/ai/indexing-pipeline.md`, `docs/architecture.md`, regression fixture + `docs/GAPS.md` if a limit remains |
| Views, Explore levels, graph algorithms, suggestions | `docs/ai/architecture-map.md`, `docs/ai/frontend-guide.md` if the UI changes, `docs/graph-architecture-research.md` status |
| Frontend components, state, hash params, shortcuts | `docs/ai/frontend-guide.md`, `docs/user-guide.md`, `docs/DESIGN.md` for visual rules |
| Env vars or settings (`ci_core/settings.py`), data dir layout | `README.md`/`docs/onboarding.md` env table, `docs/ai/runbook.md`, `.env.example` |
| Dependencies, lint/type/test/CI config, pre-commit | `CONTRIBUTING.md`, `docs/ai/testing-and-quality.md`, `docs/DECISIONS.md` |
| Security, redaction, token or clone handling | `docs/SECURITY.md`, `docs/private-repos.md`, `.cursor/rules/40-security-privacy.mdc` |
| Bug fix with a non-obvious cause | `CHANGELOG.md`; add the pitfall to `CLAUDE.md`/`AGENTS.md` only if agents could repeat it |
| New feature or user-visible change | `CHANGELOG.md`, `docs/user-guide.md`, `docs/GAPS.md` (remove the gap if closed) |

Full agent rules: [AGENTS.md](AGENTS.md). Depth: [docs/ai/README.md](docs/ai/README.md).
