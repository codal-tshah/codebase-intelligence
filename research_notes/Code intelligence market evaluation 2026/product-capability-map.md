# Product capability map (promised vs implemented)

**Audit date:** 2026-11-23  
**Sources:** [README.md](../../README.md), [docs/onboarding.md](../../docs/onboarding.md), [docs/GAPS.md](../../docs/GAPS.md)  
**Method:** Map each marketed capability to implementation paths and automated test evidence. Status: **implemented** (code + meaningful tests), **partial** (works with documented limits), **missing** (not present), **unverified** (code exists; promised scope not covered by tests or real-repo validation).

## Summary

| Area | Overall |
|------|---------|
| Framework detection | Implemented for stacks covered by fixtures; Next.js and some job schedulers are partial |
| Parsing | Implemented (Python AST + tree-sitter TS/JS) |
| HTTP linking | Implemented (cross-stack on `fullstack_app`) |
| Views | Implemented in API + dashboard; Explore has no CLI/MCP equivalent |
| Incremental index | Implemented |
| CLI | Implemented (README commands covered by `test_cli.py`; not every flag isolated) |
| MCP tools | Implemented (20 tools; parity gaps vs Explore/neighborhood) |
| Chat citations | Implemented (SSE + deterministic fallback) |
| Impact / path | Implemented (API, CLI, MCP, UI) |
| Monorepos | Partial (import roots + workspace packages; no dedicated regression) |
| Jobs | Partial (Celery/APScheduler/Nest/Django mgmt; beat dicts & APScheduler `add_job` calls missing) |
| Integrations | Partial (graph + editor packaging; marketplace publish & some SDK granularity gaps) |

## Capability table

| Capability | Status | Evidence (file / test) | Gap link |
|------------|--------|------------------------|----------|
| **Framework detection — Python (Django)** | implemented | `ci_adapters_django/adapter.py` (`detect_django`, URL/model extraction); `backend/packages/adapters/django/tests/test_adapter.py::test_detect_django_fixture` | — |
| **Framework detection — FastAPI / Flask / Starlette / django-ninja** | implemented | Decorator routing in `adapter.py` (`WEB_APP_FACTORIES`, `Depends` → `INJECTS`); `test_multi_analyzer.py::test_fastapi_routes_prefixes_and_dependency_injection`; `test_layered_fastapi.py` (realistic FastAPI fixture) | [GAPS FR-3 P1: FK ~91%](docs/GAPS.md#fr-3-status-2026-11-16) |
| **Framework detection — SQLAlchemy / SQLModel** | implemented | Model/table/FK extraction in `adapter.py`; `test_multi_analyzer.py::test_sqlalchemy_models_fields_and_foreign_keys` | [GAPS FR-3 P1: FK resolution](docs/GAPS.md#fr-3-status-2026-11-16) |
| **Framework detection — React / React Router** | implemented | `ci_adapters_typescript/analyzer.py`; `test_ts_analyzer.py::test_components_hooks_and_roles`, `test_react_router_routes_mark_pages` | — |
| **Framework detection — Express / NestJS** | implemented | `analyzer.py` (routes, guards, DI); `test_ts_analyzer.py::test_express_routes_with_mount_prefix_middleware_and_inline_handler`, `test_nest_controller_routes_guards_and_constructor_injection` | — |
| **Framework detection — Next.js (pages/app API routes)** | partial | `_next_routes()` in `analyzer.py` (`framework="nextjs"`); no fixture test in `test_ts_analyzer.py` (fullstack fixture is React+Vite, not Next) | — |
| **Framework detection — DRF** | implemented | Covered by `synthetic_django` fixture; `test_adapter.py` (URLs, class views, methods) | — |
| **Parsing — Python AST** | implemented | `ci_parsers/python_parser.py`; `test_import_kinds.py`, `test_py314_syntax.py` | — |
| **Parsing — TypeScript/JavaScript (tree-sitter)** | implemented | `ci_adapters_typescript/analyzer.py`; `test_ts_analyzer.py` (calls, JSX, HTTP collection, fingerprints) | — |
| **Parsing — file discovery / git helpers** | implemented | `ci_parsers/files.py` (root `.gitignore` via `pathspec`), `ci_indexer/pipeline.py`; `test_gitignore_discovery.py`, `test_git_clone.py`, `test_index_safeguards.py` | — |
| **HTTP linking — match client calls to backend endpoints** | implemented | `ci_core/analysis.py` (`link_http_calls`, `match_endpoint`); pipeline `ci_indexer/analyzers.py`; `test_analysis.py` (matcher unit); `test_multi_analyzer.py::test_frontend_requests_link_to_backend_endpoints` | [GAPS FR-3 P1: external services at module level](docs/GAPS.md#fr-3-status-2026-11-16) |
| **HTTP linking — absolute URLs → external services** | implemented | `link_http_calls` DEPENDS_ON host nodes; `test_multi_analyzer.py` (host edges) | Same as above |
| **HTTP linking — dev proxy prefix / tie-break by path** | implemented | `match_endpoint` + `test_analysis.py::test_match_prefers_literals_methods_and_proxy_prefix`, `test_match_tie_breaks_on_nearest_service` | — |
| **Views — catalog (Explore, Layers, Architecture, API flow, Jobs, Call graph, Components, ER, Integrations)** | implemented | `ci_core/views/*.py`, `view_catalog` in `insights.py`; `test_insights.py::test_every_view_builds_consistent_payload`; API `test_fullstack_api.py::test_fullstack_summary_and_views` | — |
| **Views — Explore (expand, lift, budget, edge drill-down)** | implemented | `views/explore.py`, `explore_edges.py`; `test_explore.py`; API explore endpoints in `apps/api/routers/graph.py` | [onboarding: no CLI/MCP Explore](docs/onboarding.md#integration-status) |
| **Views — API flow end-to-end (UI → handler → models)** | implemented | `views/api_flow.py`; `test_insights.py::test_api_flow_focus_follows_one_request`; `test_multi_analyzer.py::test_components_view_and_end_to_end_api_flow` | — |
| **Views — Jobs diagram** | implemented | `views/jobs.py`; `test_jobs.py::test_jobs_detected_and_traced_to_model_writes` | [onboarding: scheduler gaps](docs/onboarding.md#integration-status) |
| **Views — Integrations diagram** | implemented | `views/integrations.py`; SDK detection `test_ts_analyzer.py::test_sdk_imports_become_external_services`; Django integrations `test_adapter.py::test_signals_middleware_admin_and_integrations` | [GAPS FR-3 P1: per-function external links](docs/GAPS.md#fr-3-status-2026-11-16) |
| **Views — neighbourhood / aggregated edge drill-down (API)** | implemented | `insights.py` (`neighborhood_subgraph`); `test_explore.py::test_neighborhood_depth`, `test_underlying_between_matches_aggregate`; README routes `/graph/neighborhood`, `/graph/edges` | [onboarding: MCP only get_callers/callees](docs/onboarding.md#integration-status) |
| **Incremental index — fingerprints & skip unchanged files** | implemented | `ci_indexer/pipeline.py`, `changes.py`, `ci_core/fingerprints.py`; `test_pipeline.py` (full/skip/partial/architecture, freshness, adapter version bump) | — |
| **Incremental index — CLI `--incremental` & post-commit hook** | implemented | `ci_cli/main.py` (`analyze`, `hook`); `test_cli.py` (hook idempotency, pull/checkout/rebase) | — |
| **Incremental index — API `POST …/index` & job polling** | implemented | `apps/api/routers/projects.py`; `test_api.py` (index job flow) | — |
| **Incremental index — freshness (fresh/dirty/stale)** | implemented | `ci_indexer` freshness; `test_pipeline.py::test_freshness_transitions`; MCP `index_status` in `ci_mcp/server.py` | — |
| **CLI — analyze, projects, search, endpoints, trace, models, tour, jobs, suggest, docs, export, impact, ask, serve, mcp** | implemented | `backend/apps/cli/src/ci_cli/main.py`; `test_cli.py` (analyze→query, impact gate, jobs/suggest/docs, impact `--base`, hook, projects admin) | README lists more flags than isolated tests (e.g. `status`, `analyzers`) — behaviour via shared `ci_core` / API |
| **CLI — impact exit code 2 on high risk** | implemented | `ci_cli/main.py` impact command; `test_cli.py::test_cli_impact_gate_exits_nonzero_on_high_risk` | [GAPS P2: GitHub Action packaging](docs/GAPS.md#p2-roadmap) |
| **MCP — project tools (`list_projects`, `index_project`, `index_status`)** | implemented | `ci_mcp/server.py`; `test_mcp.py::test_mcp_lists_tools_and_answers_against_path`, `test_mcp_index_project_accepts_github_url` | [onboarding: private GitHub not exercised on real repo](docs/onboarding.md#integration-status) |
| **MCP — exploration tools (overview, search, get_node, endpoints, trace, callers/callees, path, models, build_context, find_references, read_source, search_code)** | implemented | `ci_mcp/server.py` + `ci_ai/toolspec.py`; `test_mcp.py` (tool name subset asserted) | Explore graph state not exposed |
| **MCP — change analysis (`impact_analysis`, `impact_of_working_tree`)** | implemented | `server.py`; `test_mcp.py::test_mcp_impact_of_working_tree_with_git_base` | — |
| **MCP — jobs & review (`list_jobs`, `suggest_optimizations`, `generate_docs`)** | implemented | `server.py`; `test_mcp.py` (generate_docs, list_jobs in tool set) | Job detection gaps (below) |
| **MCP — auto-index on unknown path** | implemented | `ProjectResolver.resolve` in `server.py`; exercised by `test_mcp.py` overview call | `--no-auto-index` not separately tested |
| **Chat / assistant — grounded tool loop + SSE** | implemented | `ci_ai/agent.py`, `apps/api/routers/chat.py`; `test_agent.py`; `test_api.py::test_chat_tool_mode_answers_impact_question` | [GAPS P2: real-LLM smoke test](docs/GAPS.md#p2-roadmap) |
| **Chat citations — `node:` / `source:` links & citation chips** | implemented | `ci_ai/agent.py`, `toolspec.py` (`collect_refs`); `test_api.py::test_chat_streams_structured_events_with_navigable_links`; UI `frontend/src/components/ChatPanel.tsx`, `MarkdownContent.tsx` | — |
| **Chat — CLI `ci ask` with citations JSON** | implemented | `ci_cli/main.py` ask command; shares agent with API (no dedicated `test_cli` for ask — covered by agent/API tests) | unverified at CLI boundary |
| **Impact analysis — by files, working tree, git `base` ref** | implemented | `ci_core/insights.py` (`impact_for_request`, `compute_impact`); `test_api.py::test_impact_by_files_and_by_working_tree`, `test_impact_with_git_base`; CLI/MCP tests above | — |
| **Path — shortest dependency path between nodes** | implemented | `insights.find_path`; `test_insights.py` (path tests); `test_api.py::test_search_path_tour_endpoints`; MCP `find_path` | — |
| **Tour — guided reading order** | implemented | `insights.build_tour`; `test_insights.py::test_tour_orders_entry_to_data_to_tests`; API in `test_search_path_tour_endpoints` | — |
| **Monorepos — Python `src/` & `pyproject` import roots** | partial | Documented in [docs/architecture.md](../../docs/architecture.md); `adapter.py` import roots; `layered_fastapi` fixture regression | No explicit “monorepo” test name; multi-root edge cases unverified |
| **Monorepos — TS workspace packages & tsconfig paths** | partial | `analyzer.py` (`workspace_names`, path mapping); fullstack is multi-package but not a classic pnpm/yarn workspace fixture | unverified against large workspace layouts |
| **Jobs — Celery `@shared_task` / crontab schedules** | implemented | `adapter.py` job tagging; `test_jobs.py`, `test_cli.py::test_cli_jobs_text_output_lists_detected_jobs` | [onboarding: Celery beat dicts not detected](docs/onboarding.md#integration-status) |
| **Jobs — APScheduler `@scheduled_job`** | implemented | `test_jobs.py::test_jobs_detected_and_traced_to_model_writes` (`nightly_report`) | [onboarding: `scheduler.add_job(...)` calls not detected](docs/onboarding.md#integration-status) |
| **Jobs — NestJS `@Cron` / Bull `@Process`** | partial | Nest cron in `test_jobs.py`; Bull mentioned in README/onboarding — detection in `analyzer.py` (not asserted in `test_jobs.py`) | [onboarding: node-cron not detected](docs/onboarding.md#integration-status) |
| **Jobs — Django management commands** | implemented | `test_jobs.py` (`Command.handle`); Jobs view + `ci jobs` / MCP `list_jobs` | — |
| **Integrations (graph) — known SDK imports → ExternalService nodes** | implemented | Python + TS adapters; `test_ts_analyzer.py::test_sdk_imports_become_external_services` | [GAPS FR-3 P1: module-level only](docs/GAPS.md#fr-3-status-2026-11-16) |
| **Integrations (editor) — Claude Code plugin + Cursor MCP/rule** | partial | `integrations/` (`install.sh`, `claude-code/`, `cursor/`); onboarding cites `claude plugin validate` | [onboarding: not published to shared marketplace](docs/onboarding.md#integration-status); [competitive-notes P0 marketplace](docs/competitive-notes.md) |
| **Integrations (CI) — packaged GitHub Action for impact/docs** | missing | CLI supports `ci impact --fail-on` (README); no Action in `.github/` product packaging | [GAPS #28](docs/GAPS.md#p2-roadmap) |

## Test coverage map (by package)

| Package / app | Primary tests | Fixtures |
|---------------|-----------------|----------|
| `ci_adapters_django` | `test_adapter.py`, `test_layered_fastapi.py`, `test_insights.py` | `synthetic_django`, `layered_fastapi` |
| `ci_adapters_typescript` | `test_ts_analyzer.py` | `fullstack_app/web` |
| `ci_core` | `test_analysis.py`, `test_explore.py`, `test_graph_algo.py`, `test_insights.py` (via django tests) | built in tests |
| `ci_indexer` | `test_pipeline.py`, `test_multi_analyzer.py`, `test_jobs.py`, `test_git_clone.py` | `fullstack_app`, synthetic copies |
| `ci_ai` | `test_agent.py` | in-memory project |
| `ci_api` | `test_api.py`, `test_fullstack_api.py`, `test_projects_admin.py` | indexed projects |
| `ci_cli` | `test_cli.py` | `fullstack_copy`, `project_copy` |
| `ci_mcp` | `test_mcp.py` | `fullstack_copy` |
| `ci_parsers` | `test_import_kinds.py`, `test_py314_syntax.py` | inline snippets |
| Frontend | `npm test`, `e2e/dashboard.spec.ts`, `e2e/projects.spec.ts` | E2E indexes `fullstack_app` |

## Notes aligned with [docs/onboarding.md § Integration status](docs/onboarding.md#integration-status)

- **Explore via agents:** Dashboard and HTTP API only; no `ci explore` or MCP tool to expand packages — status **partial** for agent workflows.
- **Private GitHub:** Token path implemented (`CI_GITHUB_TOKEN`, `test_git_clone.py`); end-to-end against a real private repo marked **unverified** in onboarding.
- **Optimization suggestions:** Implemented with documented limits (cycles, no N+1 rules) — see onboarding row and `test_graph_algo.py`.

## Doc sync

This file is research notes only; product docs checked for claims: `README.md`, `docs/onboarding.md`, `docs/GAPS.md` (no product-doc edits required for this audit).
