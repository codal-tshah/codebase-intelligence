# Change playbooks

*Last verified against code paths cited in each section (2026-11-20).*

Use with the [change-to-doc map](README.md#change-to-doc-map).

## Add an HTTP endpoint

1. Add handler in `backend/apps/api/src/ci_api/routers/` (correct router file).
2. Reuse `require_project` / `pid` from `deps.py`; return shapes consistent with neighbors.
3. Keep `{"detail", "request_id"}` errors (raise `HTTPException`).
4. Add pytest in `backend/apps/api/tests/`.
5. Update `docs/ai/api-reference.md`; user-visible → `docs/user-guide.md` + `CHANGELOG.md`.

## Add a view module

1. Create `ci_core/views/<name>.py`; call `register_view(ViewModule(...))`.
2. Import module from `ci_core/views/__init__.py` or entry point `codebase_intelligence.views`.
3. Respect `MAX_NODES` (220) patterns in `_common.py`.
4. Add/adjust API tests for `GET .../graph/{view}`.
5. Update `docs/ai/architecture-map.md`, `frontend/src/icons.tsx` if new sidebar entry.

## Add an analyzer / framework rule

1. Package under `backend/packages/adapters/...` or plugin with entry point `codebase_intelligence.analyzers`.
2. Bump adapter `ADAPTER_VERSION` when output semantics change.
3. Add fixture regression under `backend/benchmarks/fixtures/` (human-owned) + pytest.
4. Update `docs/ai/indexing-pipeline.md`, `docs/DECISIONS.md` if new dependency.

## Change DB schema

1. Alter SQLAlchemy models in `ci_core/db.py` + migration strategy (today: `create_all` on index DB — coordinate breaking changes).
2. Bump analyzer version to force `FULL` re-index.
3. Update `docs/ai/data-model.md`, `docs/architecture.md`.

## Add a dependency

1. Add to relevant `pyproject.toml` / `package.json` with uv/npm.
2. One-line justification in `docs/DECISIONS.md`; regenerate `docs/LICENSES.md` per CONTRIBUTING.
3. Update `docs/ai/testing-and-quality.md` if gates change.

## Add an environment variable

1. Read in `ci_core/settings.py`; document in `.env.example`.
2. Update `docs/ai/runbook.md`, `README.md` or `docs/onboarding.md` if user-facing.

## Add a frontend control

1. Implement in `frontend/src/components/` or `App.tsx`; use design tokens.
2. Wire API via `api.ts`; no floating promises.
3. Vitest and/or Playwright if user-visible flow.
4. Update `docs/ai/frontend-guide.md`, `docs/DESIGN.md` if visual rules touched, `CHANGELOG.md`.
