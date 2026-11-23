# Contributing

Start with [docs/onboarding.md](docs/onboarding.md) (stack, data flow, views), then [docs/architecture.md](docs/architecture.md) (pipeline and extension points).

## Setup

```bash
cd backend && uv sync --all-packages --group dev
cd ../frontend && npm ci
```

Run locally: `uv run ci serve` (API :8000, restart after backend changes) and `npm run dev` (UI :5173, proxies `/api`).

## Before you open a PR

```bash
cd backend && uv run ruff check . && uv run pytest -q
cd frontend && npm run lint && npm test && npm run build
cd frontend && npm run test:e2e        # browser flows + axe + offline check; reuses running servers
```

The E2E suite uses your installed Google Chrome and indexes `backend/benchmarks/fixtures/fullstack_app` first. CI runs all of the above (`.github/workflows/ci.yml`).

## Guidelines

- **Small, focused diffs.** No drive-by refactors; don't delete working features.
- **Style:** match the surrounding code. Backend: ruff. Frontend: ESLint (hooks rules); Prettier isn't enforced yet, so keep the existing formatting (double quotes, semicolons, ~120 columns).
- **UI:**
  - Use the tokens in `frontend/src/styles.css` and the rules in [docs/DESIGN.md](docs/DESIGN.md): one accent, no gradients, glows or emoji icons, and no CDN assets.
  - New text and background pairs must meet WCAG AA. The axe E2E test will tell you.
  - Every new screen needs loading, empty and error states, plus keyboard access.
- **Tests:** new logic gets unit tests (pytest or vitest). New user flows get a Playwright spec in `frontend/e2e/`.
- **Dependencies:** add one only with a one-line justification in [docs/DECISIONS.md](docs/DECISIONS.md), then regenerate [docs/LICENSES.md](docs/LICENSES.md).
- **Security:** never commit secrets (`.env` is ignored). Repository content is untrusted: never render it as HTML. See [docs/SECURITY.md](docs/SECURITY.md).
- **Privacy:** don't add anything that sends repository code, paths or metadata to an external service without an explicit, default-off setting.

## Extending

- New analyzer or view plugin: [architecture.md § Extending](docs/architecture.md#extending).
- New dashboard view: register a `ViewModule` in `ci_core.views`. The sidebar picks it up from `/projects/{ref}/views`, and an icon goes in `frontend/src/icons.tsx`.

## UI screenshots

`npm run screenshots -- ../docs/ui-review/after` captures every view (needs the fullstack fixture indexed and, optionally, a large repo whose name contains `netbox`). `node e2e/perf.mjs <name>` prints load, expand and pan timings for a large project.
