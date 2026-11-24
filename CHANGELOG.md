# Changelog

All notable changes. Dates are when the work landed on a branch; versions are not tagged yet.

## Unreleased: parsing research (2026-11-23)

### Added
- **Static extraction evaluation:** Comprehensive research and evaluation of `tree-sitter`, `ast-grep`, `Semgrep`, `SCIP`, `PyCG`, `Joern`, and `Code Property Graphs (CPG)` answering rubric items for adoption in codebase intelligence.
- **Research report:** `research_notes/Code intelligence market evaluation 2026/parsing-and-graphs.md`.

## Unreleased: research and product roadmap (2026-11-23)

### Added
- **Research deliverables:** [reports/Code intelligence market evaluation 2026.md](reports/Code%20intelligence%20market%20evaluation%202026.md), [docs/product-improvement-roadmap-2026.md](docs/product-improvement-roadmap-2026.md), and `research_notes/Code intelligence market evaluation 2026/`.

## Unreleased: indexing (2026-11-23)

### Added
- **`.gitignore` in file discovery:** Python/TypeScript walks honour the repository root `.gitignore` (in addition to built-in skips and `.ciignore`).

## Unreleased: dashboard views (2026-11-20)

### Added
- **`include_tests` on graph views:** integrations, call-graph, architecture, and explore hide test-scoped nodes by default (`GET .../graph/{view}?include_tests=true`). Response may include `metadata.hidden_tests`. Dashboard hash `t=1` and toolbar **Tests hidden / Tests shown** toggle.
- **Namespace packages:** top-level folders without `__init__.py` (≥2 modules) become `Package` nodes with `properties.namespace` (e.g. `ETL/`, `scripts/`).
- **FastAPI DI aliases:** module-level `FooDep = Annotated[..., Depends(fn)]` produces **INJECTS** edges (API flow guard column).
- **ER view:** up to 12 fields per model in the diagram; `properties.field_count` on models for “+N more”. Wider ER cards (280px) with ellipsis on long type names.

### Changed
- **Explore test filter:** with **Tests hidden**, the explore tree omits test-scoped packages and modules (not only budget ranking).
- **Django/FastAPI adapter version 6:** SQLAlchemy `Mapped[...]` field types normalized; per-model ER cap is view-only (full fields remain in the index).

### Fixed
- **Explore vs toolbar:** **Tests hidden** now matches integrations, call-graph, and architecture (explore had only deprioritized tests under node budget).
- **API flow layout:** focused pipeline columns use `column_rank` sub-columns; same-file private `_*` helpers folded out of focused chains.

## Unreleased: agent documentation (2026-11-20)

### Added
- **`AGENTS.md` / `CLAUDE.md` / `docs/ai/*`:** self-maintaining agent instructions, API map, runbooks, and Cursor rules (`.cursor/rules/`).
- **`scripts/check_ai_docs.py`:** validates path references, rule frontmatter, and line budgets; run in CI and pre-commit.

## Unreleased: code quality baseline (2026-11-19)

### Added
- **Ruff:** expanded lint set, isort, format (`line-length` 120); documented per-rule ignores in `backend/pyproject.toml`.
- **Mypy:** strict on `ci_core` + `ci_parsers` (`ci_core.db` excluded until SQLAlchemy plugin); `py.typed` markers.
- **Frontend:** type-aware ESLint, Prettier, `format:check` / `typecheck` scripts; CI + `.editorconfig` + `.pre-commit-config.yaml` + VS Code settings.

## Unreleased: graph analytics P0 (2026-11-19)

### Added
- **`ci_core.graph_algo`:** SCC and dependency-cycle detection on the loaded graph (`rustworkx`, `networkx` fallback).
- **Import-cycle suggestions:** multi-module SCC cycles (not just pairs); package `__init__.py` re-export hubs, `TYPE_CHECKING`, and function-local imports excluded from the cycle subgraph; clearer titles (`N modules are tied in import cycles, e.g. a → b → a`).
- **Python parser:** tags `type_only` / `lazy` imports on `ImportInfo`; Django adapter stores `import_kind` on `IMPORTS` edges; merged edges keep `has_runtime_import` when any load-time import contributed.
- **Git clone auth:** stripping inherited git config keys is limited to `GIT_CONFIG_COUNT` / `KEY_n` / `VALUE_n` / `PARAMETERS` so global proxy/CA settings remain.
- **Re-index on refresh:** Django analyzer version **5** re-tags `import_kind` on existing projects automatically on the next full index or refresh (no manual step).
- **`backend/scripts/benchmark_graph.py`:** read-only timings for load, path, impact, neighborhood, SCC.
- **Docs:** [graph-architecture-research.md](docs/graph-architecture-research.md); dependency note in [DECISIONS.md](docs/DECISIONS.md).

## Unreleased: selection, dropdowns, API flow, validation, project management (2026-11-16)

### Added
- **Trace the selection** in every view: upstream ("in", amber) vs downstream ("out", blue), 1–10 hops or all, with in/out badges, a legend entry and counts. Unrelated nodes fade to ~0.2 and come back on hover. Esc or an empty-canvas click clears the selection.
- **Explore levels:** "Open to level" offers 1…max depth (from the real tree, plus All) for the whole tree or inside the selected package. "Collapse to" uses the same levels. The server opens levels within the node budget and says when a level only partly fits.
- **One popover for all dropdowns** (`components/Popover.tsx`): portalled, flips and shifts inside the viewport, Esc/outside-click close, arrow keys, focus returns to the trigger. Covers depth, collapse, trace depth, export, the project switcher, saved views, search results and impact depth.
- **API flow pipeline:** an endpoint list (grouped by router file, method badges, filter) and one endpoint's chain at a time in columns: Client/UI → Endpoint → Guards → Handler → Services → Data access → Models/External. Inferred links stay dashed and labelled.
- **Project management:** project switcher with search and stats; Projects page (search, sort, re-index changed / full, rename, ignore patterns, auto-refresh, remove); a remove dialog that states exactly what is deleted (the source folder is never touched); Activity (audit log) and Status tabs; saved views. API: `DELETE/PATCH /projects/{ref}`, `/projects/overview`, `/removal-plan`, `/settings`, `/saved-views`, `/index-jobs`, `/audit`, `/status`. CLI: `ci projects remove|rename`.
- **Stay current after `git pull`:** `ci hook install` now covers post-commit, post-merge (pull), post-checkout (branch switch) and post-rewrite (rebase). Optional server auto-refresh per project (`CI_AUTO_REFRESH_SECONDS`, default 60). The dashboard polls freshness and reloads itself when the index changes.
- Gzip on API responses (graph payloads are about 8× smaller); one error shape `{detail, request_id}`; `main.py` split into routers (URLs unchanged).

### Fixed (found by validating against a large private FastAPI repo)
- Python 3.14 `except A, B:` (PEP 758) made 31 files unparseable, so their routes and calls were missing. They now parse, with exact line numbers.
- `@router.get("")` (the router prefix itself) was dropped: 12 routes were missing. Endpoint count now matches the source (211/211).
- Typed dependencies (`svc: Annotated[Svc, Depends()]` aliases, `self.repo` set in `__init__`) now resolve. Handlers with resolved calls went from about 40 to 202 of 211, and chains reach models.
- Explore was flat (367 modules under `app`): sub-directories are now nested packages. Architecture opens a dominant `app/` into its layers.
- FastAPI folder roles (`routers/`, `api/`, `schemas/`, `repositories/`, `dependencies/`, `db/`, `workers/`) and Alembic migrations were all labelled "service".
- Generated `htmlcov/`/`coverage/` output was indexed as frontend code.
- Edges drew over group boxes (React Flow z-index). Parallel edges are now bundled into one line with a breakdown. Large graphs draw edges as faint context.
- The Ask graph-only answer appended an all-models dump after an endpoint trace.

## Enterprise-readiness pass (2026-11-14)

### Added
- **Improve tab:** optimization and reuse suggestions in the dashboard, filterable by kind, with nodes that open on click. The backend now balances the list across kinds (on NetBox it was 100% hotspots).
- **MCP `index_project`** accepts a GitHub URL (local mode; server mode rejects it, as the API does).
- **`/summary` cached** per project until the index changes (it took ~0.8–1s per call on 18k nodes).
- **Docker:** `uv` image pinned, non-root user, `HEALTHCHECK`, dependency layer cached, test and screenshot folders excluded from the build context.
- **Export the current view** as SVG, PNG, Mermaid, Markdown or JSON, client-side, from the toolbar's export menu. *Full graph as JSON* also works in server mode.
- **Server-mode sign-in:** the dashboard asks for the API key on a 401 and keeps it for the tab session only.
- **Semantic zoom:** names only when zoomed out, full cards when zoomed in. Edge labels and arrowheads are hidden at far zoom.
- **Focus mode toggle:** choose whether selection fades unrelated nodes.
- **Node-type tints** with an icon, type and layer label on every card. Jobs are tinted rose; inferred nodes are dashed and labelled.
- **Edge legend** (solid, dashed, inferred, HTTP).
- **Keyboard:** Enter on a focused graph node opens it; the code view is scrollable by keyboard.
- **Deep links** pasted into an open tab now navigate (`hashchange`).
- **Inspector:** packages list their children, and empty files say so.
- **Docs:** RESEARCH, GAPS, DESIGN (with contrast tables), DECISIONS, SECURITY, LICENSES, REPORT, user guide, contributing guide, and before/after UI screenshots.
- **Tooling:**
  - ESLint
  - Playwright E2E with axe (WCAG 2.2 A/AA) and an offline check, in CI
  - `scripts/check_licenses.py`
  - `e2e/capture-screens.mjs` and `e2e/perf.mjs`

### Changed
- **Explore:** expanded groups have a single-row title, so the name no longer hides under children (4-level layout test). Breadcrumbs moved onto the canvas, and the toolbar is always one row (including at 1280px).
- **Selection** uses an accent-soft fill, a 2px accent border and an accent bar, so it isn't colour-only. Dimmed nodes fade to 0.45 (was 0.32).
- **Tokens:** `--text-3` and `--warning` darkened to pass AA on every surface. Layer labels use a darkened mix.
- **Icons:** Explore (compass) and Jobs (timer) have their own icons. Emoji glyphs replaced with Lucide icons.
- **Explore layout and camera code** moved from `App.tsx` to `explore/useExploreLayout.ts` (no behaviour change).

### Fixed
- Fonts loaded from Google Fonts. They are now bundled, and the UI works offline.

### Security
- Bounded graph, source and node parameters (422 on oversized input).
- `/source` hides `abs_path` in server mode.
- `filelock` 4.2.10 (pip-audit: 13 CVEs → 0).
- `npm audit fix` for non-breaking dev advisories.

## 2026-11-13: FR-2 (`0ab829c`, `279ea56`)
- Jobs view, optimization suggestions, Mermaid docs (`ci docs`), Claude Code and Cursor integrations, private GitHub token cloning, trackpad pan and pinch, code-review fixes.

## Earlier
- See `git log` (Explore hierarchy, neighbourhood API, ELK layout, graph UX, server mode, impact `--base`).
