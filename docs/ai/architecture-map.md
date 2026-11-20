# Architecture map (agent view)

*Last verified against code: `docs/architecture.md`, `backend/packages/core/src/ci_core/`, `backend/packages/indexer/`, `backend/apps/api/src/ci_api/main.py`.*

Canonical narrative: [docs/architecture.md](../architecture.md). This file adds agent-oriented wiring only.

## Packages (dependency direction)

```
parsers, adapters ──► indexer ──► core (db, insights, views)
                              │
                              ▼
                         ai, security
                              │
         apps/api, apps/cli, apps/mcp ◄── consumers
```

| Package | Responsibility |
| --- | --- |
| `ci_parsers` | File discovery, Python `ast` parse, git clone/head, `stable_node_id` |
| `ci_adapters_django` / `typescript` | Framework-specific nodes/edges |
| `ci_indexer` | `analyze_project`, pipeline, jobs, fingerprints, `index.lock` |
| `ci_core` | Models, SQLite, `GraphIndex`, views, suggestions, audit, settings |
| `ci_ai` | Agent, `GraphTools`, `toolspec`, LiteLLM (optional) |
| `ci_security` | Secret redaction |
| `ci_api` | HTTP surface |
| `ci_cli` | Typer `ci` |
| `ci_mcp` | MCP tool wrappers + `generate_docs` |

## Runtime data flow

1. **Index:** analyzers produce nodes/edges → `ci_core.analysis.merge_results` / `link_http_calls` → `GraphStore` persists SQLite at `{CI_DATA_DIR}/projects/<id>/index.db`.
2. **Read:** `GraphStore.load_index()` builds in-memory `GraphIndex` (cached by DB mtime).
3. **Serve:** API/CLI/MCP call `insights.*`, `views.build_view`, or `GraphTools`.
4. **UI:** `frontend` fetches `/api/projects/...` (proxied in dev).

## Request lifecycle (HTTP)

1. `request_context` middleware assigns `request_id`; server mode checks API key except `GET /health`.
2. Router resolves `project_ref` via `ci_core.projects.resolve_project`.
3. Handler reads/writes `GraphStore` or registry; mutating project actions append `audit.jsonl`.
4. Errors return `{"detail", "request_id"}`; validation errors use 422 with `detail` as a list of `{loc, msg, type}`.

## View modules (built-in ids)

Registered in `ci_core.views` (sidebar order): `explore`, `layers`, `architecture`, `api-flow`, `call-graph`, `components`, `er`, `integrations`, `jobs` — see `register_view` in each module under `ci_core/views/`. Plugins: entry point group `codebase_intelligence.views`.

## Graph analytics

`ci_core.graph_algo` (SCC/cycles) runs on `GraphIndex` only; optional `rustworkx` with `networkx` fallback — not used during extraction.
