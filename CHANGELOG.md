# Changelog

All notable changes. Dates are when the work landed on a branch; versions are not tagged yet.

## Unreleased: enterprise-readiness pass (2026-11-14)

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
