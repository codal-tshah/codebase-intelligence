# Agent instructions (tool-neutral)

Codebase Intelligence indexes Python and TypeScript repositories into a local knowledge graph (CLI, FastAPI, MCP, React dashboard). All work stays on the analyst machine unless the operator enables optional LLM keys.

## Setup and gates

```bash
cd backend && uv sync --all-packages --group dev
cd ../frontend && npm ci
```

Run: `uv run ci serve` (API `:8000`, restart after backend edits) and `npm run dev` (UI `:5173`, proxies `/api`). Before finishing:

```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q
cd frontend && npm run lint && npm run format:check && npm run typecheck && npm test && npm run build
```

Optional: `uv tool run pre-commit install` at repo root. Details: [CONTRIBUTING.md](CONTRIBUTING.md).

## Boundaries (do not touch without explicit request)

- Application runtime logic under `backend/packages`, `backend/apps`, `frontend/src` (unless the task is a feature fix).
- `backend/benchmarks/fixtures/**`, `integrations/**` (product integration packaging), `docs/ui-review/**`, `.claude-plugin/**`.
- Lockfiles, CI workflows, and dependencies unless the task is tooling.
- Never write into indexed source trees; data lives under `CI_DATA_DIR` (default `~/.codebase-intelligence`).

## Definition of done

Behaviour change ships with tests where appropriate, matching doc updates (protocol below), and passing quality gates. Restart `ci serve` after backend changes; do not assume a running server reloads.

## Hard rules (summary)

Local-first and read-only on sources; API errors use `{"detail", "request_id"}`; new analyzers/views via entry points; graph analytics libraries are in-process only (rustworkx/networkx); respect `index.lock`; no blanket lint/type suppressions. Depth: [docs/SECURITY.md](docs/SECURITY.md), [docs/DESIGN.md](docs/DESIGN.md), [docs/architecture.md](docs/architecture.md).

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

## Depth

- [CLAUDE.md](CLAUDE.md) — Claude Code entry (same protocol; Claude-specific notes).
- [docs/ai/README.md](docs/ai/README.md) — index, doc freshness, playbooks.
