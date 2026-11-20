# Testing and quality

*Last verified against code: `CONTRIBUTING.md`, `.github/workflows/ci.yml`, `.pre-commit-config.yaml`, `backend/pyproject.toml`, `frontend/package.json`.*

## Local gates (match CONTRIBUTING)

**Backend** (from `backend/`):

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q
```

**Frontend** (from `frontend/`):

```bash
npm run lint
npm run format:check
npm run typecheck
npm test
npm run build
npm run test:e2e   # optional locally; required in CI job `e2e`
```

## CI (`.github/workflows/ci.yml`)

- **test job:** ruff, format, mypy, pip-audit on exported lockfile, license check, pytest, `ci analyze` synthetic + fullstack, `score_benchmark.py`.
- **frontend job:** lint, format:check, typecheck, vitest, build.
- **e2e job:** `npx playwright test` after backend sync + frontend `npm ci`.

## Pre-commit (`.pre-commit-config.yaml`)

Ruff 0.17.3 on `backend/`, local eslint+prettier on `frontend/`, detect-secrets with `.secrets.baseline`. Excludes `backend/benchmarks/fixtures/`, `docs/ui-review/`.

## Mypy scope

Strict on `packages/core/src/ci_core` and `packages/parsers/src/ci_parsers`; `ci_core/db.py` excluded until SQLAlchemy plugin.

## Fixtures

Under `backend/benchmarks/fixtures/` — do not edit in doc-only tasks. Regression tests reference `synthetic_django`, `fullstack_app`, `layered_fastapi`.

## Benchmarks

- `backend/benchmarks/score_benchmark.py --fixture benchmarks/fixtures/synthetic_django`
- `backend/scripts/benchmark_graph.py` — graph timing on indexed DB (read-only)

## Agent doc checker

```bash
python scripts/check_ai_docs.py
```

Also: `python scripts/check_ai_docs.py` at repo root (CI `test` job and pre-commit `check-ai-docs`).
