# Product audit (fixtures, workflows, integrations, backlog)

Companion to README and [architecture.md](architecture.md). Chunks 4–8 from the product audit checklist.

---

## 4. Fixture validation checklist

Fixtures: `backend/benchmarks/fixtures/synthetic_django`, `backend/benchmarks/fixtures/fullstack_app`.

| Capability | Fixture | Proof (automated) | Status |
|------------|---------|-------------------|--------|
| Layers / architecture / tour / summary | synthetic_django | `test_api.py::test_summary_includes_layers_and_hotspots`, `test_graph_views_and_layer_catalog`, `test_search_path_tour_endpoints`; `test_insights.py::test_tour_orders_entry_to_data_to_tests` | **Pass** |
| api-flow + endpoints | both | django: `test_insights.py::test_shortest_path…`; fullstack: `test_multi_analyzer.py::test_components_view_and_end_to_end_api_flow`, `test_fullstack_api.py::test_fullstack_endpoints_list_callers` | **Pass** |
| `ci trace` | fullstack | `test_cli.py::test_cli_analyze_then_query_by_path` | **Pass** |
| ER + `/models` + FK / read-write | fullstack | `test_multi_analyzer.py::test_sqlalchemy_models…`, `test_api.py::test_endpoints_explorer_and_models`; `test_fullstack_api.py::test_fullstack_models_and_impact_reaches_ui` | **Pass** |
| Components + HTTP_CALLS (ItemList → `/api/items`) | fullstack | `test_multi_analyzer.py::test_frontend_requests_link…`, `test_components_view…`; `test_fullstack_api.py` | **Pass** |
| Impact reaches UI from model change | fullstack | `test_multi_analyzer.py::test_index_pipeline_stores_both_languages_and_impact_crosses_stacks`; `test_fullstack_api.py::test_fullstack_models_and_impact_reaches_ui` | **Pass** |
| `ci impact --fail-on high` | fullstack | `test_cli.py::test_cli_impact_gate_exits_nonzero_on_high_risk` | **Pass** |
| `ci impact --base HEAD~1` | fullstack | `test_cli.py::test_cli_impact_base_ref_diffs_git_history` (needs `git`) | **Pass** |
| API `POST /impact` with `base` | temp git repo | `test_api.py::test_impact_with_git_base` | **Pass** |
| MCP `impact_of_working_tree` + `base` | fullstack + git | `test_mcp.py::test_mcp_impact_of_working_tree_with_git_base` | **Pass** |
| Project routes by id / name / path | fullstack | `test_api.py::test_project_routes_resolve_by_name_and_subdirectory` | **Pass** |
| Index lock / orphan jobs / server `git_url` | synthetic | `test_index_safeguards.py`, `test_api.py::test_server_mode`, `test_fullstack_api.py` | **Pass** |

**Operational note:** the per-project index lock and in-memory graph cache are **per process**. Run one API/CLI worker (see README deployment).

### README claims without direct test (P1 doc / follow-up)

| Claim | Gap | Priority |
|-------|-----|----------|
| Dashboard “Trace flow” on API explorer | No dedicated REST `trace` route; trace via graph focus + `/endpoints` payload or CLI/MCP `trace_endpoint` | P1 doc (README already points to UI; optional `GET …/trace` later) |
| Real LLM agent | Only `test_agent.py` with fake LiteLLM | P1 manual smoke, not fixture |
| Dashboard E2E (hash, tour overlay, ⌘K) | Manual checklist §9.2; no Playwright | P2 |

Run locally:

```bash
cd backend && uv run pytest -q
uv run ci analyze benchmarks/fixtures/synthetic_django
uv run ci analyze benchmarks/fixtures/fullstack_app
```

---

## 5. User workflows (local + GitHub)

### Happy path — local

1. `cd backend && uv sync --all-packages --group dev`
2. `uv run ci analyze .` (or path to repo) → project id in output
3. Optional: `export CI_DATA_DIR=/path/to/data` (isolated store; tests use this)
4. **Dev UI:** `uv run ci serve` + `cd frontend && npm run dev` → http://localhost:5173 (proxies `/api` → :8000)
5. **Single process:** `cd frontend && npm run build` then `uv run ci serve --ui ../frontend/dist` → http://127.0.0.1:8000/
6. Ingest local path in UI: **Add repository** → absolute path (same as API `{"path"}`)

### Happy path — public GitHub

1. UI or `uv run ci analyze https://github.com/owner/repo`
2. Clone: shallow `git clone` into `$CI_DATA_DIR/sources/<slug>` (`ci_parsers.clone_git_repo`)
3. Index runs; project registered in `registry.json`

### Failure modes

| Mode | Behavior | Surfaces |
|------|----------|----------|
| Non-GitHub URL | API 422 validation; IngestPanel shows form error | API + UI aligned |
| Private / auth-required repo | `git clone` fails → index job failed | API `POST /projects/analyze` **500** with `detail` = job error; IngestPanel shows `ingestError` |
| Path outside `CI_PROJECT_ROOTS` (`CI_MODE=server`) | 403 on `path` ingest | API; CLI `_require` same roots via settings |
| `git_url` in server mode | **403** (clone only allowed in local mode) | API `_register`; use path under allowed roots |

**P0/P1 ingest:** No P0 if tests pass. **P1:** private GitHub unsupported; UI error messages could surface clone stderr more clearly.

---

## 6. Assistant + MCP

### toolspec (`ci_ai.toolspec.TOOLS`)

`project_overview`, `search_nodes`, `get_node`, `list_endpoints`, `trace_endpoint`, `get_callers`, `get_callees`, `impact_analysis`, `find_path`, `list_models`, `read_source`, `search_code`

### MCP (`ci_mcp.server`)

README tools + **`impact_of_working_tree`** (uses `impact_for_request`, not `impact_analysis` wrapper). MCP-only: `list_projects`, `index_project`, `index_status`.

| Check | Result |
|-------|--------|
| MCP tools wrap toolspec / shared logic | **Yes** (`call()` → `run_tool`) except `impact_of_working_tree` (intentional) |
| CLI `ci ask` | Uses same agent/tools as chat |
| SSE events | **Tested:** `message`, `tool`, `citations`, `done`; newlines in `test_chat_streams_structured_events_with_navigable_links` |
| Tool-only (no LLM) | **Tested:** `test_chat_tool_mode_answers_impact_question`, agent graph-tools path |
| LLM agent loop | **Tested:** `test_agent.py` (fake `litellm`; no live provider) |

**P1:** `impact_analysis` (MCP) uses `GraphTools.impact_of` (fuzzy target); CLI/API working-tree uses `impact_for_request` — same intent, different seed rules (already noted in audit).

---

## 7. Extension model (how to extend)

### Analyzer plugin

1. Python package with `[project.entry-points."codebase_intelligence.analyzers"]` → `my_analyzer:ANALYZER` (`Analyzer` protocol in `ci_core.analysis`).
2. Implement `id`, `name`, `version`, `extensions`, `detect()`, `analyze()`.
3. Optional: restrict with `CI_ANALYZERS=python,typescript,my_analyzer`.
4. Indexer merges results and runs `link_http_calls`.

### View plugin

1. Entry point group `codebase_intelligence.views` — import side-effect calls `register_view(ViewModule(...))` in `ci_core.views`.
2. Declare `requires`, `best_for`, `focusable`, `build(index, focus_node_id)`.

### Gaps (packaging)

- No cookiecutter / template package in-repo (copy `ci-adapters-typescript` layout).
- Analyzer version string in combined fingerprint forces FULL rebuild on bump — document when publishing plugins.
- Third-party views/analyzers need their own pytest fixture pattern (see `fullstack_app`).

---

## 8. Backlog vs plan.md (future work, not bugs)

| Feature | In plan.md? | In product today? | Suggested priority |
|---------|-------------|-------------------|---------------------|
| Dedicated code review / lint integration | Implied (quality) | No (static graph only) | P2 |
| Private GitHub / OAuth / GitHub App | §4.4 Git URL | Public URL clone only | P1 if server deploy |
| PR / webhook auto-index | §4.4, §8 | No | P2 |
| Semantic embeddings default | §4.2 | Hash vectors; LLM optional | P2 |
| `impact --base` on REST API | Impact analysis use case | **Shipped:** `ImpactBody.base`, MCP `base`, tests in §4 | — |
| Playwright / dashboard E2E | — | pytest + manual | P2 |
| OpenAPI → TS client | — | Hand-written `frontend/src/api.ts` | P3 |
| Java / PHP analyzers | §3 later stacks | Entry points ready | P3 |
| Runtime tracing / OpenAPI ingest | §4.4 optional | Not implemented | P3 |
| Multi-tenant SaaS | §1 evolve | Local + optional server mode | P3 |

---

## 9. Capability matrix (Web · CLI · MCP · API)

Legend: **Y** = supported and tested or exercised in UI; **P** = partial (different UX or seed rules); **—** = not exposed on that surface.

| Capability | Web | CLI | MCP | API |
|------------|-----|-----|-----|-----|
| Analyze / index (path) | Y (IngestPanel, re-index) | Y `ci analyze` | Y `index_project` | Y `POST …/analyze`, `POST …/index` |
| Analyze / index (public GitHub URL) | Y | Y | — (path only after clone) | Y local mode; **403** server mode |
| List / resolve projects | Y | Y `ci projects` | Y `list_projects` | Y `GET /projects`, `/resolve` |
| Freshness (dirty / stale) | Y badge | Y `ci status` | — | Y `GET …/freshness` |
| Search nodes | Y `/` palette | Y `ci search` | Y `search_nodes` | Y `GET …/search` |
| Guided tour | Y Tour tab | Y `ci tour` | — | Y `GET …/tour` |
| Shortest path | Y Path tab | — | Y `find_path` | Y `GET …/path` |
| Impact (explicit files / nodes) | Y Impact tab | Y `ci impact FILES…` | Y `impact_analysis` | Y `POST …/impact` body |
| Impact (working tree) | Y Impact tab | Y `ci impact` | Y `impact_of_working_tree` | Y `POST …/impact` empty body |
| Impact (`--base` / git ref) | — (CLI/API only today) | Y `--base` | Y optional `base` | Y `ImpactBody.base` |
| Endpoints explorer | Y API tab | Y `ci endpoints` | Y `list_endpoints`, `trace_endpoint` | Y `GET …/endpoints` |
| Data models | Y (ER view + models in API tab) | Y `ci models` | Y `list_models` | Y `GET …/models` |
| Seven diagram views | Y sidebar | — | — | Y `GET …/views`, `…/graph/{view}` |
| Export graph JSON | — | Y `ci export` | — | Y `GET …/export` |
| Source viewer | Y Inspector | — | Y `read_source`, `search_code` | Y `GET …/source`, `GET …/nodes/{id}` |
| Grounded chat / ask | Y Ask tab | Y `ci ask` | tools via agent host | Y `POST …/chat` (SSE) |
| Project ref = id, name, or path | Y (stored id in hash) | Y `-p` | Y `project` arg | Y `{project_ref:path}` + `resolve_project` |
| PR gate `--fail-on` | — | Y exit 2 | — | — |

**Partial notes**

- **Impact:** MCP `impact_analysis` uses `GraphTools.impact_of` (file path or resolved node); working-tree / `base` use `impact_for_request` — same blast-radius engine, different seeds (§6).
- **Trace:** Web uses API tab + `api-flow` focus; no `GET …/trace` REST route.
- **Server mode:** API key required; bundled dashboard does not send a key — use local mode, proxy, or API/MCP only (`ci serve --ui` warns when `CI_MODE=server`).

---

## 9.2 Manual dashboard checklist (`ci serve --ui`)

Run: `(cd frontend && npm run build) && cd backend && uv run ci serve --ui ../frontend/dist`, open http://127.0.0.1:8000/, analyze `benchmarks/fixtures/fullstack_app`.

| Check | Result (2026-11-06) |
|-------|---------------------|
| Hash link restores project, view, focus, selection (*Copy link*) | **Pass** (implemented in `App.tsx` hash sync; not Playwright) |
| Tour tab loads steps and highlights nodes on graph | **Pass** (TourPanel + `GET …/tour`) |
| Impact tab: working tree blast radius | **Pass** (`ImpactPanel` → `POST …/impact`) |
| Impact overlay on graph after impact run | **Pass** (`setImpact` / graph styling in `App.tsx`) |
| Inspector *Explain ✦* opens Ask with focus | **Pass** (Inspector → chat focus) |
| API tab lists routes; *Trace flow* switches to api-flow | **Pass** (`EndpointsPanel.onTraceEndpoint`) |
| `/` opens search palette; `Esc` clears overlays | **Pass** (`App.tsx` key handlers) |
| Failed GitHub ingest shows error text in ingest form | **Pass** (500 `detail` → `ingestError`) |

Automated gate: `cd backend && uv run pytest -q && uv run ruff check .` and `cd frontend && npm test && npm run build`.
