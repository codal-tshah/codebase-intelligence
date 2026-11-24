# API reference (HTTP, CLI, MCP)

*Last verified against code: `backend/apps/api/src/ci_api/routers/`, `backend/apps/cli/src/ci_cli/main.py`, `backend/apps/mcp/src/ci_mcp/server.py`, `backend/packages/ai/src/ci_ai/toolspec.py`.*

Mounting: standalone `ci serve` serves routes at path root; `ci serve --ui` mounts API at `/api` (dashboard at `/`). Dev UI uses `API = "/api"` with Vite proxy.

Errors: `{"detail": <string|list>, "request_id": "<id>"}`; header `X-Request-ID`.

## HTTP routes

### System (`system.py`)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness `{"status":"ok"}` (no auth in server mode) |
| GET | `/status` | Version, mode, projects, active jobs, analyzers |
| GET | `/layers` | Layer taxonomy catalog |
| GET | `/analyzers` | Analyzer plugins list |
| GET | `/views` | View module catalog (no project) |
| GET | `/git/check?url=` | GitHub clone preflight (disabled in server mode for ingest) |
| GET | `/audit` | `audit.jsonl` entries (filters: limit, project_id, action) |

### Projects (`projects.py`)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/projects` | Registry list |
| GET | `/projects/overview` | Overview cards for dashboard |
| GET | `/projects/resolve?ref=` | Resolve id/name/path |
| POST | `/projects` | Register path or git URL (body: `CreateProjectBody`) |
| POST | `/projects/analyze` | Register + index (body: `AnalyzeBody`) |
| GET | `/projects/{ref}/removal-plan` | What delete would remove |
| GET/PUT | `/projects/{ref}/settings` | Project settings (e.g. `auto_refresh`, ignore patterns) |
| GET/POST | `/projects/{ref}/saved-views` | Saved views CRUD |
| DELETE | `/projects/{ref}/saved-views/{view_id}` | Remove saved view |
| GET | `/projects/{ref}/views` | View catalog with availability |
| GET | `/projects/{ref}/summary` | Project summary |
| GET | `/projects/{ref}/freshness` | Index vs working tree |
| POST | `/projects/{ref}/index` | Start index job (`incremental` query) |
| GET | `/projects/{ref}/jobs/{job_id}` | Job status |
| GET | `/projects/{ref}/index-jobs` | Recent jobs |
| GET | `/projects/{ref}/docs` | Generated docs metadata |
| DELETE | `/projects/{ref}` | Remove project (not source) |
| PATCH | `/projects/{ref}` | Rename |

### Graph (`graph.py`)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/projects/{ref}/endpoints` | Endpoint list (`q` filter) |
| GET | `/projects/{ref}/models` | Model catalog |
| GET | `/projects/{ref}/background-jobs` | Jobs view data |
| GET | `/projects/{ref}/suggestions` | Improvement suggestions |
| GET | `/projects/{ref}/graph/neighborhood` | Local subgraph; lifted `edges[]` include `extractor` and `evidence` |
| GET | `/projects/{ref}/graph/edges` | Explore underlying edges (`expanded`, `extra_child_offsets`, `include_tests` — same as explore canvas); each edge may include `evidence` |
| GET | `/projects/{ref}/graph/{view}` | View payload (explore: `expanded`, `extra_child_offsets`, `expand_to_level`, `level_root`; tests: `include_tests=true` → keep test-layer nodes; default omits them on integrations / call-graph / architecture / explore) |
| GET | `/projects/{ref}/export` | Full graph JSON download (edges include computed `evidence`) |
| GET | `/projects/{ref}/tour` | Guided tour steps |
| GET | `/projects/{ref}/search` | Node search |
| GET | `/projects/{ref}/path` | Shortest path (`source`, `target`, `max_hops`); `edges[]` include `confidence`, `extractor`, and `evidence` |
| POST | `/projects/{ref}/impact` | Impact analysis (body: `ImpactBody`) |
| GET | `/projects/{ref}/nodes/{node_id}` | Node detail + edges (each edge includes optional `evidence`; `node.evidence`; `properties.http_calls[]` entries may include `evidence`) |
| GET | `/projects/{ref}/source` | Source snippet (`path`, `start`, `end`) |

### Chat (`chat.py`)

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/projects/{ref}/chat` | SSE stream (`ChatBody`: message, history, optional `focus_node_id`) |

## CLI (`ci --help`)

| Command | Role |
| --- | --- |
| `analyze` | Index path or git URL (`--incremental`) |
| `projects` | List; subcommands `remove`, `rename` |
| `analyzers` | List analyzers |
| `status` | Counts + freshness |
| `search` | Symbol search |
| `endpoints` | Route list |
| `trace` | Endpoint trace |
| `models` | Models |
| `hook` | `install` / `uninstall` / `status` (git hooks) |
| `jobs` | Background jobs |
| `suggest` | Suggestions |
| `docs` | Write Markdown + Mermaid; `-o` output dir (default name per `ci docs --help`) |
| `tour` | Tour steps |
| `impact` | Blast radius |
| `ask` | Chat (tools or LLM) |
| `export` | Graph JSON |
| `serve` | API (+ optional `--ui`) |
| `mcp` | MCP server stdio |

Global: `--project` / `-p`, `--json`. Verify flags: `uv run ci <cmd> --help`.

## MCP tools (`ci mcp`)

From `ci_mcp.server.build_server` (wrap `toolspec` unless noted):

`list_projects`, `index_project`, `index_status`, `project_overview`, `search_nodes`, `get_node` (edges include `confidence`, `extractor`, source line, and `evidence`), `list_endpoints`, `trace_endpoint` (chain hops after the endpoint include `evidence` on traversed edges), `get_callers`, `get_callees`, `impact_analysis`, `impact_of_working_tree`, `find_path`, `list_models`, `build_context` (optional `token_budget`: caps source snippet **characters** ≈ `4 × token_budget` across primary + `related_source`; echoes `snippet_chars_used` / `snippet_char_budget`; `missing_evidence` lists truncation, omission, and absent source; nested `node` from `get_node`; `callers` / `callees` / `models` include per-hop `evidence`), `find_references` (each reference includes `evidence`), `list_jobs`, `suggest_optimizations`, `generate_docs`, `read_source`, `search_code`.

## Verify

```bash
cd backend && uv run ci --help
rg '@router\\.' backend/apps/api/src/ci_api/routers
```
