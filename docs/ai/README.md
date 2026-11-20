# AI-facing documentation index

*Last verified against code: `AGENTS.md`, `backend/apps/api/src/ci_api/routers/`, `backend/apps/cli/src/ci_cli/main.py`, `backend/apps/mcp/src/ci_mcp/server.py`, `backend/packages/core/src/ci_core/` (2026-11-20).*

## Who reads what

| Reader | Start here |
| --- | --- |
| Any coding agent | [AGENTS.md](../../AGENTS.md) |
| Claude Code | [CLAUDE.md](../../CLAUDE.md) then this index |
| Cursor (in-repo) | [.cursor/rules/](../../.cursor/rules/) |
| Humans extending the product | [docs/onboarding.md](../onboarding.md), [docs/architecture.md](../architecture.md) |

## Module docs

| File | Contents |
| --- | --- |
| [architecture-map.md](architecture-map.md) | Packages, data flow, request lifecycle (see also [docs/architecture.md](../architecture.md)) |
| [data-model.md](data-model.md) | Nodes, edges, SQLite, `GraphIndex` |
| [api-reference.md](api-reference.md) | HTTP, CLI, MCP |
| [indexing-pipeline.md](indexing-pipeline.md) | Analyze, incremental, hooks, jobs |
| [frontend-guide.md](frontend-guide.md) | UI state, views, layout, tests |
| [testing-and-quality.md](testing-and-quality.md) | Gates, fixtures, CI parity |
| [runbook.md](runbook.md) | Local run, data dir, failures |
| [change-playbooks.md](change-playbooks.md) | Checklists for common changes |

## Change-to-doc map

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

## Doc freshness (re-verify from these paths)

| Doc | Primary source paths in repo |
| --- | --- |
| architecture-map.md | `backend/packages/*`, `docs/architecture.md` |
| data-model.md | `ci_core/models.py`, `ci_core/db.py`, `ci_core/insights.py`, `ci_parsers/python_parser.py` |
| api-reference.md | `ci_api/routers/`, `ci_cli/main.py`, `ci_mcp/server.py`, `ci_ai/toolspec.py` |
| indexing-pipeline.md | `ci_indexer/pipeline.py`, `changes.py`, `analyzers.py`, `ci_core/analysis.py` |
| frontend-guide.md | `frontend/src/App.tsx`, `flow.ts`, `explore/*`, `api.ts` |
| testing-and-quality.md | `CONTRIBUTING.md`, `.github/workflows/ci.yml`, `.pre-commit-config.yaml` |
| runbook.md | `ci_core/settings.py`, `.env.example`, `CONTRIBUTING.md` |
| change-playbooks.md | Same as above + `docs/DECISIONS.md` |

Run `python scripts/check_ai_docs.py` after editing agent docs.
