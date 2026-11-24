# External repository indexing matrix (2026-11-23)

Verified on this machine with `CI_GITHUB_TOKEN` available (public clones). Each run used a fresh `CI_DATA_DIR`.

| Repository | Nodes | Edges | Endpoints | Models | HTTP_CALLS | Notes |
|------------|------:|------:|----------:|-------:|-----------:|-------|
| [encode/starlette](https://github.com/encode/starlette) | 1621 | 4145 | ~40+ (decorator routes) | 0 | 0 | Library repo; no frontend. Index completes in ~4s. |
| [fastapi/sqlmodel](https://github.com/fastapi/sqlmodel) | 1823 | 3972 | 57 | 125 | 0 | Heavy doctest/examples; models extracted. |
| [pallets/flask](https://github.com/pallets/flask) | 1035 | 2092 | 36 | 0 | 0 | Blueprint/examples indexed; framework source. |
| `benchmarks/fixtures/layered_fastapi` | 77 | 119 | (see tests) | yes | 0 | Regression fixture; adapter v6. |
| `benchmarks/fixtures/fullstack_app` | 88 | 158 | yes | yes | **3** | Cross-stack HTTP links present (UI→API). |

## Ground-truth checks

### fullstack_app (must pass)

- `test_multi_analyzer.py::test_frontend_requests_link_to_backend_endpoints` — **pass** (CI).
- Manual: `useItems` hook → POST/GET items endpoints.

### encode/starlette

- Expect FastAPI/Starlette-style `Endpoint` nodes under `starlette/` package.
- No false `HTTP_CALLS` required (no TS client in repo).

### fastapi/sqlmodel

- Expect SQLAlchemy/SQLModel `Model` nodes and tutorial `Endpoint` stubs.

### pallets/flask

- Expect `@app.route` / blueprint `Endpoint` nodes; tests package may inflate graph until `.gitignore` is honoured (see P1 implementation).

## Failures / risks observed

- **No parse failures** on the three GitHub clones in this pass.
- **Indexing ≠ accuracy:** starlette/sqlmodel/flask were not manually spot-checked route-by-route in this pass; counts are structural smoke only.
- **Monorepo / Next / Nest:** not included in this matrix pass (see product-capability-map).

## Commands used

```bash
export CI_DATA_DIR=$(mktemp -d)
cd backend && uv run ci analyze https://github.com/encode/starlette
uv run ci projects --json
```
