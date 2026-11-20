# Frontend guide (agents)

*Last verified against code: `frontend/src/App.tsx`, `api.ts`, `flow.ts`, `trace.ts`, `explore/*`, `styles.css`, `vite.config.ts`.*

User-facing UI: [docs/user-guide.md](../user-guide.md). Design rules: [docs/DESIGN.md](../DESIGN.md).

## Stack

Vite, React 18, TypeScript strict, `@xyflow/react`, ELK + dagre layouts, Vitest, Playwright (`frontend/e2e/`).

## API access

`frontend/src/api.ts`: base `"/api"`. Dev server proxies to `CI_API_URL` or `http://127.0.0.1:8000` (`vite.config.ts`). Production/static UI served by `ci serve --ui` uses same `/api` prefix.

## State (`App.tsx`)

Tracks active project, sidebar view id, selected node, explore expansions, trace mode, panels (Ask, Impact, Path, etc.). Fetches graph via `GET /projects/{id}/graph/{view}` with explore query params.

## URL hash

Hash encodes project/view/focus/expanded nodes (`explore/hash.ts`). `writeHash` uses `history.replaceState`; external `hashchange` applies pasted deep links.

## Layout

- **Explore:** nested ELK (`layoutExplore.ts`), level expansion API params `expand_to_level`, `level_root`.
- **Other views:** often dagre (`layout.ts`).
- **Edges:** `RoutedEdge.tsx`, aggregation in server views (`architecture`, `explore`).

## Trace

`trace.ts` computes upstream/downstream highlight sets from selection + graph payload.

## Components

Major areas under `frontend/src/components/` (Inspector, ChatPanel, CommandPalette, SuggestionsPanel, …). Icons: `frontend/src/icons.tsx` for view sidebar entries.

## Tests

- Unit: colocated `*.test.ts`.
- E2E: `e2e/*.spec.ts`, axe offline specs; requires Chrome channel.

Do not add CDN assets; fonts bundled at build.
