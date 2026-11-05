# Codebase Intelligence Platform

Local-first codebase analysis that turns a repository into an explorable knowledge graph: architecture, API flows, call graphs, data models, UI component trees and third-party integrations, with frontend → backend HTTP calls linked to the routes they hit. A grounded assistant answers questions about the graph with clickable citations. The same graph is available from a web dashboard, a CLI, and an MCP server for AI agents.

| Stack | Detected |
|-------|----------|
| Python | Django (URLs, views, DRF, models, signals, middleware, admin), FastAPI / Flask / django-ninja (decorator routes, router prefixes, `Depends` injection), SQLAlchemy / SQLModel (tables, columns, foreign keys, session reads/writes) |
| TypeScript / JavaScript | React (components, hooks, JSX render tree, React Router pages), Next.js (pages/app router pages and API routes), Express (routes, `app.use` mount prefixes, middleware), NestJS (controllers, guards, constructor injection) |
| Cross-stack | `fetch` / axios / `getJson`-style calls matched to backend endpoints from any analyzer; absolute URLs become external services; known SDKs (Stripe, AWS, Redis, OpenAI, …) become integrations |

New languages and frameworks plug in as separate packages; see [docs/architecture.md](docs/architecture.md#extending).

## Quickstart

```bash
cd backend
uv sync --all-packages --group dev
uv run ci analyze /path/to/your/repo          # or a GitHub URL; "." for the current directory

# Dashboard: API + built UI in one process
(cd ../frontend && npm install && npm run build)
uv run ci serve --ui ../frontend/dist          # http://127.0.0.1:8000

# …or hot-reload development (two terminals)
uv run ci serve                                # API on :8000
cd ../frontend && npm run dev                  # UI on :5173, proxies /api
```

## Dashboard

- **Diagrams**: the sidebar lists the modules the server reports (`/projects/{id}/views`). Modules with nothing to show for the project are disabled.
  - Overview: Layers, Architecture
  - Backend: API flow, Call graph
  - Frontend: Components
  - Data: Data model
  - Integrations
- **End-to-end flows**: focus an endpoint in *API flow* and the diagram runs from UI component → hook → API client → route → handler → services → models/external services.
- **API explorer** (`API` tab): every route with method, handler, guards and dependencies, models read or written, and the client code that calls it. *Trace flow* opens the end-to-end view.
- **Inspector**:
  - summary, layer, confidence, relations, and outgoing HTTP calls linked to their endpoints
  - source with line numbers and the symbol highlighted, plus *open in editor* (VS Code)
  - *Explain ✦* asks the assistant about the selected node
- **Assistant** (`Ask` tab):
  - streams answers that show their grounding steps
  - `[Name](node:…)` links jump to the node in the right diagram, and `file:line` links open the source
  - citation chips; *show all on graph* highlights everything cited
- **Tour, impact, path**:
  - a guided reading order
  - blast radius of a node or of your uncommitted changes
  - the shortest dependency path between two nodes
- **Deep links**: the URL hash keeps project, view, focus and selection (*Copy link*). Press `/` to search and `Esc` to clear overlays.

## CLI

PROJECT can be an id, a name, or any path inside the repo. The default is the current directory. Add `--json` for scripting.

```bash
ci analyze [PATH|URL] [--incremental]     # index (incremental skips unchanged work)
ci projects | ci analyzers                # what's indexed / which analyzers are installed
ci status [PROJECT]                       # freshness: fresh | dirty | stale
ci search QUERY [-p PROJECT] [--types Endpoint,Model]
ci endpoints [-p PROJECT] [-f FILTER]     # routes → handler, models, UI callers
ci trace ROUTE [-X METHOD]                # what happens when this API is called
ci models                                 # tables, relations, who reads/writes
ci tour [PROJECT]
ci impact [FILES...] [--base REF] [--depth 3] [--fail-on high]   # default: working tree; exit 2 on risk ≥ level
ci ask "How does authentication work?"    # assistant in the terminal
ci export -o graph.json
ci serve [--ui ../frontend/dist]
ci mcp [--project PATH]                   # MCP server (stdio by default)
```

**PR gate in CI:** after `ci analyze .`, run `ci impact --base origin/main --fail-on high`. It exits with code 2 when a change reaches high risk (for example a model used by many endpoints).

## MCP (AI agents)

```bash
claude mcp add codebase-intel -- uv run --directory /path/to/codebase-intelligence/backend ci mcp --project /path/to/repo
```

Tools:
- Project management: `list_projects`, `index_project`, `index_status`
- Exploration: `project_overview`, `search_nodes`, `get_node`, `list_endpoints`, `trace_endpoint`, `get_callers`, `get_callees`, `find_path`, `list_models`
- Change analysis: `impact_analysis`, `impact_of_working_tree`
- Source access: `read_source`, `search_code`

Every tool takes an optional `project` (id, name or path). An unindexed path is indexed on first use (`--no-auto-index` turns that off). The in-app assistant uses the same tool definitions (`ci_ai.toolspec`).

## API

| Endpoint | Purpose |
|----------|---------|
| `GET /health`, `/layers`, `/analyzers`, `/views` | Liveness and catalogs |
| `GET /projects`, `POST /projects/analyze` | List projects; clone or index a repo (`{"path"}` or `{"git_url"}`) and return its summary |
| `GET /projects/{id}/summary`, `/freshness` | Stats, tech stack, patterns, hotspots; index freshness |
| `POST /projects/{id}/index`, `GET /projects/{id}/jobs/{job}` | Start or poll (incremental) index jobs |
| `GET /projects/{id}/views` | Diagram modules with availability and counts |
| `GET /projects/{id}/graph/{view}?focus_node_id=` | Graph for a view (404 for unknown views) |
| `GET /projects/{id}/endpoints?q=`, `/models` | API explorer, data models |
| `GET /projects/{id}/search`, `/path`, `/tour`, `POST /impact` | Graph insights |
| `GET /projects/{id}/nodes/{node}`, `/source` | Node detail; source window (indexed files only) |
| `GET /projects/{id}/export` | Full graph JSON |
| `POST /projects/{id}/chat` | SSE events: `message`, `tool`, `citations`, `done`, `error` |

## Configuration

Every variable is validated at startup by `ci_core.settings`; copy [.env.example](.env.example) for the full list.

| Variable | Purpose |
|----------|---------|
| `CI_MODE` | `local` (default, trusted single user) or `server`. Server mode requires `CI_API_KEY` and `CI_PROJECT_ROOTS` and fails fast without them |
| `CI_API_KEY` | Server mode: clients send `X-API-Key` or `Authorization: Bearer`. `/health` stays open |
| `CI_PROJECT_ROOTS` | Server mode: only these directories may be indexed (API and MCP) |
| `CI_DATA_DIR` | Data directory (default `~/.codebase-intelligence`) |
| `CI_CORS_ORIGINS` | Comma-separated allowed origins (default: localhost dev origins, no credentials) |
| `CI_ANALYZERS` | Restrict analyzers, e.g. `python` |
| `CI_LOG_LEVEL`, `CI_LOG_JSON` | Logging; every API response carries `X-Request-ID` and logs include it |
| `ALLOW_LLM` | `true` to enable the agentic assistant and LLM summaries |
| `LLM_MODEL`, `LLM_API_KEY`, `LLM_API_BASE` | Any LiteLLM model; a self-hosted base URL keeps code on-prem |

**Deployment:** `docker build -t codebase-intelligence . && docker run -p 8000:8000 -v ci-data:/data codebase-intelligence` serves the dashboard and API. Run a **single worker**: the graph cache and database engines are per process, and indexing runs in-process. In server mode the dashboard does not send an API key, so put it behind your own auth proxy, or use the API and MCP only.

Without an LLM, the assistant answers deterministically from graph tools, in the same linked format. Add a `.ciignore` (gitignore syntax) at the project root to exclude files.

## Tests

```bash
cd backend && uv run pytest                     # analyzers, linker, views, pipeline, API, agent loop, MCP, CLI
uv run python benchmarks/score_benchmark.py --fixture benchmarks/fixtures/synthetic_django
cd ../frontend && npm run build                 # type-check + production build
```

The fixtures are `benchmarks/fixtures/synthetic_django` (Django and DRF) and `benchmarks/fixtures/fullstack_app` (FastAPI, SQLAlchemy, React, Express and NestJS).

## Layout

- `backend/packages/core`: graph model, analyzer contract and HTTP linker (`analysis.py`), SQLite store with caching, insights (search, path, impact, tour, endpoints), and `views/`, one module per diagram
- `backend/packages/parsers`: Python AST parser, file discovery, git helpers
- `backend/packages/adapters/django`: Python analyzer (Django, FastAPI, Flask, SQLAlchemy)
- `backend/packages/adapters/typescript`: TypeScript/JavaScript analyzer (tree-sitter)
- `backend/packages/indexer`: analyzer registry, pipeline, change classification, freshness
- `backend/packages/ai`: tool specs, agent, chunking and embeddings, summaries, LLM config
- `backend/packages/security`: secret redaction
- `backend/apps/{api,cli,mcp}`: FastAPI server, `ci` CLI, MCP server
- `frontend/src`: React Flow dashboard

Design ideas were borrowed from [Understand-Anything](https://github.com/Egonex-AI/Understand-Anything) and [nancy-kataria/codebase-intelligence](https://github.com/nancy-kataria/codebase-intelligence).
