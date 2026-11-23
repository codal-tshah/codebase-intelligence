# Enterprise-readiness report (2026-11-14)

What changed in this pass, how each item was verified, and what is still open. Everything is **uncommitted** on branch `FR-2` for review.

## Follow-up review (same day)

After the main pass I reviewed the repo and docs again. Found and fixed:

| # | Finding | Fix | Verified by |
|---|---|---|---|
| 1 | **Docker image was unverified.** Registries are reachable now | Pinned `uv` 0.11.22; non-root `ci` user; `HEALTHCHECK`; dependency layer built from manifests only (code changes no longer re-download deps); `.dockerignore` excludes test and screenshot output | `docker build` ✅. Container: health 200, `ci analyze` of a mounted repo ✅, GitHub clone (pallets/markupsafe) ✅, **16/16 E2E tests pass against the container** (2 runs). Server-mode container reports *healthy* |
| 2 | **Bug: server-mode `HEALTHCHECK` got 401.** The middleware exempted `/health`, but under the `/api` mount the path is `/api/health` | Strip the mount prefix before the check | `test_health_is_public_when_mounted_under_api`; server-mode container shows *healthy* |
| 3 | **Bug: suggestions were 100% hotspots on large repos** (sort by severity, then truncate) | `_balanced()` gives each kind a share, then fills by severity | `test_suggestions_are_balanced_across_kinds`; NetBox top 100 = 58 hotspot / 16 complexity / 16 cycle / 7 duplication / 2 data-access / 1 unused |
| 4 | Suggestions not visible in the dashboard | *Improve* tab: filter by kind, click a node to open it; ⌘K action | E2E + axe; `ui-review/after/tab-improve.png` |
| 5 | `/summary` recomputed on every load (~0.8–1s) | Cached per project until the index DB changes (and on LLM-setting change) | `test_summary_is_cached_until_the_index_changes` |
| 6 | MCP `index_project` took paths only | Accepts GitHub URLs in local mode; rejected in server mode (same rule as the API) | `test_mcp_index_project_accepts_github_url` |
| 7 | Flaky E2E: a locator re-resolved after selection, and axe sometimes measured mid-fade on a fresh container | Pin nodes by `data-id`; axe waits for network idle plus the 200ms fade | Green: fresh-volume container ×2, dev ×1 |
| 8 | Stale docs: README ("API tab", "Explain ✦", deployment), audit-report (private GitHub "unsupported", "no Playwright"), onboarding (no suggestions panel, MCP path only), review-2026-11 (open items now fixed), competitive-notes (image export ❌, dashboard auth ⚠️) | Updated, with dates where statuses changed | Read through |
| 9 | CI didn't build the image | New `docker` job: build plus health and dashboard smoke test | YAML validated locally; not run on GitHub |

> **Screenshots:** only the six embedded in the user guide are committed. The full `ui-review/before` and `after` sets cited below stay local; regenerate them with `cd frontend && npm run screenshots -- ../docs/ui-review/after`.

## Summary

The dashboard went through six phases: audit, research, gap analysis, design system, enterprise readiness and verification. **No architecture changes:** same stack, same API, same views.

Key results:
- **Offline:** fonts are bundled; an automated check confirms zero non-localhost requests.
- **Server mode:** the dashboard now works with an API key.
- **Explore:** groups are readable at every depth.
- **Layout:** the toolbar is one row; semantic zoom makes large graphs legible.
- **New:** five client-side export formats; WCAG 2.2 A/AA passes on six screens (axe).
- **Security:** both dependency audits are clean for shipped and runtime code.
- **Tests:** 122 backend, 35 frontend unit, 15 browser E2E. All pass.

## Checks (final run)

| Check | Command | Result |
|---|---|---|
| Backend tests | `cd backend && uv run pytest -q` | **126 passed**, 0 failed (was 121 before this pass) |
| Backend lint | `uv run ruff check .` | All checks passed |
| Frontend lint (new) | `npm run lint` | 0 problems |
| Frontend unit | `npm test` | **36 passed** (was 26) |
| Build | `npm run build` | Built. Bundle 616 KB JS (ELK 1.4 MB, lazy-loaded) |
| Browser E2E + a11y + offline (new) | `npm run test:e2e` | **16 passed**, against the dev servers **and** the Docker container |
| Docker | `docker build .` then run | Builds; healthy in local and server mode; non-root |
| npm audit (shipped) | `npm audit --omit=dev` | 0 |
| pip-audit | see SECURITY.md | 0 (was 13 in `filelock`) |
| Licences | `scripts/check_licenses.py` | 0 shipped JS flagged; 2 Python for review (MPL-2.0 certifi, ISC shellingham) |

The E2E suite covers:
- ingest by path, including validation
- switching views
- selecting a node
- Enter on a focused node
- Explore expand and collapse
- ⌘K search and pick
- Ask in tool-only mode
- a pasted deep link
- the export menu and an SVG download
- axe on Layers, Explore, API flow, ingest, Ask and the palette
- offline: no external requests, and the three bundled fonts load

## Phase outputs

| Phase | Files |
|---|---|
| 1. Audit | `docs/audit-report.md` §0; `docs/ui-review/before/*.png` (23 screenshots) |
| 2. Research | `docs/RESEARCH.md` (sources marked official, secondary or unverified) |
| 3. Gaps | `docs/GAPS.md` (P0 ×8, P1 ×15, P2 roadmap ×10). No architecture change recommended, so no stop |
| 4. Design and UI | `styles.css`, `ArchNode.tsx`, `flow.ts`, `graphTheme.ts`, `icons.tsx`, `Inspector.tsx`, `LayerLegend.tsx`, `EdgeLegend.tsx` (new), `IngestPanel.tsx`, `CommandPalette.tsx`, `explore/layoutExplore.ts`; `docs/DESIGN.md` |
| 5. Enterprise | listed below |
| 6. Verify | `docs/ui-review/after/*.png` (28 screenshots); this report |

Phase 5 files:
- **Offline:** `index.html`, `main.tsx`
- **Auth:** `api.ts`, `ApiKeyPrompt.tsx` (new), `ChatPanel.tsx`
- **Exports:** `export/exportView.ts` (new), `ExportMenu.tsx` (new)
- **Refactor:** `explore/useExploreLayout.ts` (new), `App.tsx`
- **API hardening:** `ci_api/main.py`, `test_api.py`
- **Dependencies:** `uv.lock` (filelock, litellm)
- **Tooling:** `eslint.config.js`, `playwright.config.ts`, `e2e/*`, `vite.config.ts`, CI workflow, `scripts/check_licenses.py`
- **Docs:** `DECISIONS.md`, `SECURITY.md`, `LICENSES.md`, `user-guide.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, README, onboarding, architecture

## What changed and how it was verified

| Item | Change | Verified by |
|---|---|---|
| Explore group title | Single-row header; `GROUP_TITLE` 52 | Unit test (4 levels: children below the title and inside the parent); E2E (header height < 48px); before/after screenshots |
| Focus mode | Toggle (default on); fade 0.45; subtree and ancestors never faded | Unit tests (`dimUnrelated` on/off); `after/large-explore-selected.png` |
| Toolbar | One row at every width; breadcrumbs on the canvas | `after/laptop-1280-explore.png`, `after/large-explore-selected.png` |
| Semantic zoom | `zoom-far` / `mid` / `near` classes | `after/large-layers.png` vs `after/large-layers-zoomed.png`; text stays crisp after zoom (screenshot check) |
| Tints, selection, inferred | Tokens plus 2px selected border and bar; dashed and labelled inferred | Contrast table (DESIGN.md); axe color-contrast passes; unit test (inferred flag, job tint) |
| Inspector | Children listed for packages; empty files say so; no repeated path | `after/large-explore-selected.png` |
| Keyboard | Enter opens a focused node; focus ring on nodes; focusable code block | E2E (keyboard test); axe `scrollable-region-focusable` |
| Deep links | `hashchange` listener | E2E (pasted deep link) |
| Icons | Explore compass, Jobs timer; emoji glyphs replaced | Screenshots |
| Offline fonts | `@fontsource`, no CDN links | E2E with all non-localhost requests aborted: 0 external, 3 fonts loaded |
| Server-mode auth | 401 → key dialog → `sessionStorage` → `X-API-Key` | Manual browser run on a `CI_MODE=server` instance (:8020): prompt shown; wrong key shows "rejected"; right key loads the dashboard; key absent from localStorage and URL. Screenshot `after/server-mode-api-key.png` |
| Input bounds; `abs_path` hidden | 422 on oversized input | pytest `test_graph_and_source_params_are_bounded`, `test_server_mode_requires_key_and_confines_paths` |
| Exports | SVG, PNG, Mermaid, Markdown, JSON (client); full JSON (API with key) | vitest (escaping, nesting, renumbered ids); E2E (menu, SVG download) |
| Refactor | Explore layout and camera moved to a hook; App.tsx 1,632 → 1,487 lines | All E2E and unit tests; Explore expand, collapse and camera checked in the browser |
| Dependencies | `filelock` 4.2.10, `litellm` 1.109.1; `npm audit fix` (non-breaking) | pip-audit 0; 122 tests pass |

## Performance (NetBox: 2,319 files, 18,674 nodes, 35,462 edges)

Measured on an M-series Mac with the **production bundle** on a separate API instance (:8010), using `node e2e/perf.mjs netbox http://127.0.0.1:8010`. Three runs each; ranges shown.

| Metric | Result |
|---|---|
| Index: clone + full | 28.4s |
| Index: full re-index | 15.9s |
| Index: incremental, no changes | 6.6s |
| API cold first request (load index into memory) | 0.67s |
| API warm graph views | 7–37ms |
| Payload: Explore top level | 45 KB |
| Payload: Explore with 3 groups expanded | 281 KB |
| Payload: Layers (220 nodes, 1,442 edges) | 457 KB |
| Payload: Data model | 831 KB |
| Payload: full export | 25.3 MB (0.35s) |
| `/summary` | 0.76–0.98s, **not cached** (P1 below) |
| Explore first render | 0.38–0.52s, one outlier at 1.4s |
| Explore expand (click to group visible) | 0.24–0.29s; one 50–57ms long task (ELK) |
| Pan, Explore | 61fps, worst frame 17ms |
| Pan, Layers (220 nodes, 1,442 edges) | **49–55fps** (was 25–41) |
| Other views first render | Call graph 0.21–0.24s; Data model 0.20–0.83s |

On the Layers pan fix:
- A `will-change: transform` layer reached 59–60fps, but it **left the UI unpainted** in a large-graph screenshot, so it was rejected (DECISIONS #7).
- The shipped fix drops arrowheads and uses faster edge rasterisation at far zoom.

## Not verified (explicit)

- **Docker on Linux CI / other architectures:** built and verified on Docker Desktop (arm64) only. The new CI `docker` job covers amd64 but hasn't run yet.
- **Real LLM assistant:** only tool-only mode (E2E) and the fake LiteLLM (pytest) are exercised. The `litellm` minor bump (1.108 → 1.109.1) is therefore only covered by those tests.
- **CI workflow:** the new `e2e`, lint and `docker` jobs were not run on GitHub Actions. They mirror the local commands, and `channel: "chrome"` relies on Chrome being preinstalled on `ubuntu-latest`.
- **Your running dev API (:8000) was not restarted.** It still runs the old backend code. The new validation and `abs_path` behaviour are live after `ci serve` restarts; pytest covers them. `uv sync` updated `litellm` and `filelock` in the shared venv.
- **One intermittent failure:** in about 25 automated runs of "expand right after the first paint", one timed out waiting for the group header. It didn't recur in 15 targeted retries, including cold servers. Root cause unknown; the perf script now waits for network idle.
- **Design systems** (Linear, Primer, Atlassian, Radix, shadcn) were not individually researched. CodeDebrief had no reliable source.
- **Screen readers:** not tested with VoiceOver or NVDA. axe covers ARIA structure, not the full experience.
- **Mobile below laptop width:** existing breakpoints were kept, but only 1280px and 1440px were checked.

## Remaining backlog

**P0 (needs you, not code)**
- Restart the dev API (`ci serve`). It still runs the old backend code: the param bounds, health fix, summary cache and suggestion balancing apply after a restart.
- Validate the private trial repos `codal/internal-bi-llm` and `codal/accis-be` (set `CI_GITHUB_TOKEN`; carried over).
- Push the branch so the new CI jobs (lint, e2e, docker) run once on GitHub.

**P1**
- Upgrade Vite 8 and Vitest 5 to clear the dev-only advisories.
- Slimmer Docker image (~1.1 GB): make LiteLLM an optional extra of `ci-ai`.
- Investigate the intermittent expand timeout.
- Split `App.tsx` further (data loading, selection) and code-split ELK so it stays out of first paint (it is already lazy).

**P2** (see GAPS.md for details)
- dark theme, after tokenising the graph colours
- SSO, RBAC and audit via a proxy
- saved views
- commit-to-commit diff
- packaged GitHub Action
- shared graph cache across workers
- sequence diagrams
- enforced Prettier
- virtualised Inspector lists
- real-LLM smoke test
