# Gap analysis

Inputs:
- the audit in [audit-report.md](audit-report.md) §0, with screenshots in `docs/ui-review/before/`
- [RESEARCH.md](RESEARCH.md)
- [competitive-notes.md](competitive-notes.md)

Effort: S < ½ day, M ≈ 1–2 days, L > 2 days. Status reflects this pass; how each item was verified is in [REPORT.md](REPORT.md).

**Architecture:** none of these gaps needs an architecture change. Server-side identity (SSO, RBAC) is the closest. It is planned as a reverse-proxy integration on top of the existing API-key middleware, so the stack stays as is.

## P0: blocks enterprise use or misleads users

| # | Gap | Why it matters | Source | Effort | Status |
|---|---|---|---|---|---|
| 1 | Explore group title hidden under its children: the header is ~70px but 40px was reserved | A group's name is unreadable once expanded (`before/large-explore-expanded.png`) | Audit | S | Done |
| 2 | Fonts loaded from Google Fonts CDN | Breaks offline and air-gapped use; sends viewer IPs to a third party | Audit, constraint | S | Done (vendored `@fontsource`) |
| 3 | Dashboard can't authenticate in server mode | The shared server is unusable from the UI | Audit | M | Done (key prompt on 401, `X-API-Key` header) |
| 4 | Unbounded graph query params (`expanded`, ids, `path`) | Cheap DoS and log flooding | Security review | S | Done |
| 5 | Selection dims too much on large Explore graphs; dimming can't be turned off | Users lose context; looks broken | Audit (known issue) | S | Done (softer dim plus a "Dim unrelated" toggle) |
| 6 | Toolbar wraps to two rows (breadcrumbs, or width ≤1280) | Eats canvas height on laptops | Audit (known issue) | S | Done (single row; breadcrumbs move onto the canvas) |
| 7 | No ESLint, E2E or a11y check in CI | Regressions in the 1.6k-line UI go unnoticed | Audit | M | Done (ESLint, Playwright E2E, axe) |
| 8 | `/source` returns `abs_path` in server mode | Leaks the server filesystem layout to API clients | Security review | S | Done (omitted in server mode) |

## P1: expected by enterprise users

| # | Gap | Why it matters | Source | Effort | Status |
|---|---|---|---|---|---|
| 9 | Text unreadable at fit zoom on dense views | Layers on NetBox (220 nodes) is a grey blur | Audit; yFiles LOD guidance | S | Done (semantic zoom: 3 levels) |
| 10 | No per-view export (SVG, PNG, Mermaid, Markdown) | Sharing diagrams in PRs, docs and client decks | Research §2 | M | Done (client-side, no dependency) |
| 11 | Node type is shown by a 3px tick only; no soft tints | Weak scanning; colour-only signal | Prompt, Primer | S | Done (tints plus icon plus label; contrast table) |
| 12 | Selection is colour-only (1px border plus glow) | WCAG non-text contrast; not obvious | Primer, WCAG 1.4.11 | S | Done (accent-soft fill, 2px border, accent bar) |
| 13 | Package Inspector shows "No source" or an empty `__init__` | Dead end for the most common Explore click | Audit (known issue) | S | Done (lists children) |
| 14 | Overview card takes ~110px in Explore | Less canvas on the view that needs it most | Audit | S | Done (auto-compact in Explore) |
| 15 | Keyboard: focused graph node can't be opened with Enter | Keyboard users can't reach the Inspector | WCAG 2.1.1 | S | Done |
| 16 | Explore and Jobs share the fallback globe icon | Ambiguous navigation | Audit | S | Done |
| 17 | Edge legend missing (solid vs dashed, inferred) | Users don't know dashed means inferred or low confidence | Prompt | S | Done |
| 18 | Editing the URL hash in an open tab does nothing | Shared links pasted into an open tab don't navigate | Audit | S | Done (`hashchange` listener) |
| 19 | `App.tsx` ≈1,630 lines with Explore layout and camera inline | Risky to change | Audit | M | Done (Explore layout and camera moved to `explore/useExploreLayout.ts`) |
| 20 | Dependency audit not run | Supply-chain hygiene | Prompt | S | Done (see SECURITY.md) |
| 21 | Docker image never built | Deployment story unproven | Audit | S | Done: built and run; pinned `uv`, non-root, healthcheck, cached deps layer; E2E passes against the container |
| 21a | Server-mode `HEALTHCHECK` got 401 (`/api/health` not exempt under the `/api` mount) | Every server-mode container would report unhealthy | Found while verifying Docker | S | Done (+ test) |
| 21b | Suggestions panel missing in the dashboard; the list was 100% hotspots on large repos | Reviewers never saw the leads; other kinds crowded out | competitive-notes, review | S | Done (*Improve* tab, per-kind balancing) |
| 21c | `/summary` recomputed on every load (~0.8–1s on 18k nodes) | Slowest request on dashboard load | Perf | S | Done (cached until the index changes) |
| 21d | MCP `index_project` accepted paths only | Agents couldn't ingest a GitHub URL | review-2026-11 | S | Done (local mode) |
| 22 | No user guide, contributing guide or changelog | Onboarding friction | Prompt | S | Done |
| 23 | No dependency licence inventory | Enterprise legal review | Prompt | S | Done (`docs/LICENSES.md`) |

## P2: roadmap

| # | Gap | Why it matters | Source | Effort |
|---|---|---|---|---|
| 24 | Dark theme | Preference; long sessions | Prompt | M (graph colours are TS constants, not CSS tokens yet) |
| 25 | SSO (OIDC/SAML), RBAC, audit log | Enterprise identity | Swimm, Sourcegraph | L (recommended: oauth2-proxy in front plus the `X-Forwarded-User` audit log) |
| 26 | Saved, named views | Teams revisit the same slices | Research §2 | M |
| 27 | Commit-to-commit visual diff | PR review | Greptile, Swimm | L |
| 28 | Packaged GitHub Action (`ci impact --fail-on`, `ci docs`) | CI adoption | CodeBoarding, Swimm | S |
| 29 | Shared graph cache across workers (graph cache is per process) | Horizontal scale | Audit | M |
| 30 | Sequence diagrams for a traced endpoint | Code Wiki parity | Research | M |
| 31 | Prettier enforced across the frontend | Formatting consistency | Prompt | S (deferred to avoid a repo-wide reformat diff; see DECISIONS) |
| 32 | Virtualised Inspector lists for 1k+ children | Very large packages | Perf | S |
| 33 | Real-LLM agent smoke test | Only the fake LiteLLM is tested | Audit | S (needs a provider key) |
