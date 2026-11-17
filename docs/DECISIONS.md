# Decisions

Short records of choices that are expensive to undo or that add dependencies. Newest first. Each entry gives the decision, why, and what was rejected.

## 2026-11-14: enterprise-readiness pass

### Dependencies added

| Package | Scope | Why (one line) |
|---|---|---|
| `@fontsource/schibsted-grotesk`, `@fontsource/ibm-plex-mono`, `@fontsource-variable/newsreader` | runtime (CSS and fonts only) | Bundle the existing fonts so the UI works offline and air-gapped. OFL-1.1. |
| `@playwright/test` | dev | Browser E2E for the main flows. Uses the installed Chrome (`channel: "chrome"`), so no browser download. |
| `@axe-core/playwright` | dev | Automated WCAG 2.2 A/AA checks on real screens. |
| `eslint`, `@eslint/js`, `typescript-eslint`, `eslint-plugin-react-hooks`, `globals` | dev | Linting, mainly hooks rules, for a 1.5k-line React app. |

Nothing heavy was added to the shipped bundle besides the font files.

### Decisions

0. **Docker image (follow-up, same day):**
   - Pinned `uv` 0.11.22.
   - Runs as a non-root `ci` user (uid 10001).
   - `HEALTHCHECK` on `/api/health`.
   - Third-party dependencies install from the workspace manifests and lockfile only, so code changes don't re-download them.
   - Size is ~1.1 GB, mostly litellm, tokenizers and huggingface-hub for the optional assistant. A slim variant without `ci-ai`'s LLM extras is a possible follow-up, but it would need `ci-ai` to make LiteLLM an optional extra.
   - The auth middleware now strips the mount prefix, so `/api/health` stays public in server mode.

1. **Image export is drawn from our own layout, not with `html-to-image`.**
   - React Flow's official example pins `html-to-image@1.11.11`, and edges outside the viewport get clipped (see RESEARCH.md).
   - We already know every node's position and size and every edge's endpoints. A ~100-line SVG writer is complete, dependency-free and deterministic. PNG is that SVG rasterised on a canvas.
   - Trade-off: the SVG is a simplified card (type, name, path), not a pixel copy of the DOM.
2. **Dashboard auth in server mode uses an API-key prompt.**
   - On any 401 the UI asks for `CI_API_KEY`, keeps it in `sessionStorage` (this tab only) and sends `X-API-Key`.
   - It is never written to `localStorage`, cookies or the URL.
   - Rejected: a cookie session (needs server-side session state and CSRF handling) and a key in the URL (leaks via history and logs).
   - SSO is deliberately left to a reverse proxy (roadmap, GAPS #25).
3. **`/source` omits `abs_path` in server mode.** It reveals the server's filesystem layout. Local mode keeps it for the *Open in VS Code* link.
4. **Graph query params are bounded:**
   - ids ≤ 512 chars
   - `expanded` ≤ 500 ids
   - `extra_child_offsets` ≤ 200
   - `path` ≤ 1024
   - `end` ≥ 1

   The dashboard never comes close to these limits; they stop accidental or abusive huge requests.
5. **Semantic zoom uses CSS classes at 0.5 and 0.9 zoom.** One `useStore` selector returns the level, so React re-renders only when the level changes, not on every wheel tick.
6. **Focus mode is a toggle, default on, fading to 0.45** (was a fixed 0.32). The old fade made large-graph selections look broken. The toggle lets users keep full contrast.
7. **`will-change: transform` on the viewport was rejected.**
   - It made panning Layers on NetBox (220 nodes, 1,442 edges) run at 59–60fps.
   - But it left the top bar and panels unpainted (Chrome tile memory) in a large-graph screenshot.
   - Used instead: at far zoom, drop arrowheads and use `shape-rendering: optimizeSpeed`. That gives 49–55fps, up from 25–41, with no glitch.
8. **Explore group header is one row**, with `GROUP_TITLE` 40 → 52px. The old multi-line header (~70px) slid under the children.
9. **Explore layout and camera effects moved from `App.tsx` to `explore/useExploreLayout.ts`.** Code moved as-is with dependencies passed in; behaviour is unchanged. App.tsx went from 1,632 to ~1,490 lines.
10. **Prettier is not enforced yet.** Formatting the whole frontend would produce a large unrelated diff. ESLint runs in CI; Prettier is on the roadmap (GAPS #31).
11. **Dev-tool advisories (Vite, Vitest, ESLint packages) are not force-upgraded.**
    - `npm audit` reports 13; **all are dev-only** (`npm audit --omit=dev`: 0).
    - The fixes are major versions (Vite 8, Vitest 5) that need their own migration.
12. **`filelock` 3.32.7 → 4.2.10, with `litellm` 1.108.0 → 1.109.1.** pip-audit reported 13 CVEs in the transitive `filelock` (litellm → huggingface-hub). After the bump pip-audit is clean and all backend tests pass.
13. **Dark theme deferred.** Graph colours are TypeScript constants; tokenising them comes first.
14. **The user's running dev API server was not restarted.** The backend changes are covered by pytest. A separate instance on :8010 (production bundle) was used for measurements and stopped afterwards.

## Earlier

Decisions from earlier passes are recorded inline in [architecture.md](architecture.md), [private-repos.md](private-repos.md) and [competitive-notes.md](competitive-notes.md).
- **2026-11-16: No new dependencies for FR-3.** The popover is in-house (about 250 lines) rather than Floating UI/Radix, because we only need anchored placement, flip, shift and roving focus. Orthogonal routes reuse ELK, which is already bundled. Gzip is Starlette's built-in middleware, which skips SSE by default.
- **2026-11-16: Per-project settings and saved views live in the data dir**, not in the repository, so indexing stays read-only for source folders.

