# Product improvement roadmap (November 2026)

Research-backed evaluation and implementation status for Codebase Intelligence. Synthesis of:

- [Code intelligence market evaluation 2026](../reports/Code%20intelligence%20market%20evaluation%202026.md)
- [Product capability map](../research_notes/Code%20intelligence%20market%20evaluation%202026/product-capability-map.md)
- [External repo matrix](../research_notes/Code%20intelligence%20market%20evaluation%202026/external-repos.md)

**Verified on 2026-11-23** unless marked *assumed*.

## 1. Executive summary

The product delivers its core promise: **local-first static graph**, **cross-stack HTTP linking** (fixture-proven), **dashboard + CLI + MCP**, **impact/path/tour**, and **grounded chat with citations** (tool-only and API-tested). Gaps are **trust signals** (confidence labelling, dynamic-call honesty), **agent context shaping** (token budgets), **fixture coverage** for partial claims (Next.js, monorepos), and **GTM packaging** (GitHub Action).

Market position: agent-first MCP servers (GitNexus, Greptile) are the growth vector; permissive-license, deterministic cross-stack tracing remains differentiated.

## 2. Capability matrix (abbreviated)

| Area | Status | Evidence |
|------|--------|----------|
| Python Django/FastAPI/Flask/SQLAlchemy | Implemented | `layered_fastapi`, `synthetic_django`, GitHub clones |
| TypeScript React/Express/Nest | Implemented | `fullstack_app`, adapter tests |
| Next.js | Partial (fixture-verified) | App/Pages routes, middleware, client/server directives; no loading/template/rewrite graph |
| Cross-stack HTTP | Implemented | `fullstack_app` 3 `HTTP_CALLS`; `test_multi_analyzer` |
| Incremental index | Implemented | `test_pipeline.py`, hooks |
| Explore / views | Implemented | E2E + `test_explore.py` |
| MCP (21 tools) | Implemented | `ci_mcp/server.py`, `test_mcp.py` |
| `build_context` | Enhanced | `token_budget`, `missing_evidence` (2026-11-23) |
| `.gitignore` discovery | Implemented | `test_gitignore_discovery.py` |
| GitHub Action | Partial | `integrations/github-action/action.yml` (composite sketch) |

Full table: [product-capability-map.md](../research_notes/Code%20intelligence%20market%20evaluation%202026/product-capability-map.md).

## 3. Real-world indexing (Phase C)

| Target | Nodes | Edges | HTTP_CALLS | Verdict |
|--------|------:|------:|-----------:|---------|
| encode/starlette | 1621 | 4145 | 0 | Smoke OK |
| fastapi/sqlmodel | 1823 | 3972 | 0 | Smoke OK |
| pallets/flask | 1035 | 2092 | 0 | Smoke OK |
| fullstack_app fixture | 88 | 158 | 3 | **Ground-truth pass** |

Route-by-route accuracy on large OSS clones was *not* manually audited in this pass.

## 4. Technology decisions

| Technology | Decision |
|------------|----------|
| tree-sitter | **Retain** |
| Python AST + adapters | **Retain** |
| pathspec / `.gitignore` | **Adopted** (runtime dep on `ci-parsers`) |
| ast-grep, PyCG | **Partial adopt** (future; see graph-architecture-research) |
| SCIP export | **P2** interop |
| Semgrep / Joern / CPG | **Defer** (license / resource cost) |
| GitNexus embed | **Reject** (noncommercial license) |

Details: [parsing-and-graphs.md](../research_notes/Code%20intelligence%20market%20evaluation%202026/parsing-and-graphs.md), [graph-architecture-research.md](graph-architecture-research.md).

## 5. Prioritized backlog

### P0 — trust and proof

| Item | Benefit | Complexity | Acceptance criteria |
|------|---------|------------|---------------------|
| Edge provenance labels in UI/MCP | Agents stop treating guesses as facts | M | **Done** 2026-11-24 — shared `evidence` tier + HTTP `match_variant`; re-index for full linker metadata on old graphs |
| Fixtures for partial claims | README matches reality | M | **Done** (2026-11-24): five fixtures under `benchmarks/fixtures/`; extend with real OSS clones over time |

### P1 — reliability (some done this pass)

| Item | Status |
|------|--------|
| Honour `.gitignore` | **Done** 2026-11-23 |
| `build_context` token budget + missing evidence | **Done** 2026-11-23 |
| Explore via CLI/MCP | Open |
| Impact risk tiers + ownership metadata | Open |
| GitHub Action (packaged) | Sketch only |

### P2 — market parity

| Item | Notes |
|------|------|
| Sequence diagram for traced endpoint | GAPS #30 |
| OpenAPI bridge for linking | Research-backed |
| ast-grep / PyCG spikes | After packaging review |
| SCIP export | Interop |

### P3 — optional

Cross-repo federation, OTel overlays, pluggable graph DB, Semgrep subprocess.

## 6. Implemented in this research pass (Wave 1)

1. Root `.gitignore` in file discovery (`ci_parsers.files`).
2. MCP/API `build_context`: `token_budget`, `missing_evidence`.
3. Research artifacts + this roadmap.
4. Composite GitHub Action example under `integrations/github-action/`.

## 7. Verification (Phase G)

| Gate | Result (2026-11-23) |
|------|---------------------|
| `uv run pytest -q` | Pass |
| `npm test` / `npm run build` | Pass (prior session) |
| `npm run test:e2e` | Pass (18 tests, prior session) |
| `scripts/check_ai_docs.py` | Pass |
| External clone index smoke | Pass (3 repos) |
| Live LLM Ask | *Not run* — requires operator `ALLOW_LLM` + provider key |

## 8. Remaining manual steps

- Re-index projects after adapter or discovery changes.
- Configure `ALLOW_LLM` for live Ask/MCP smoke.
- Publish GitHub Action to marketplace or vendor doc when paths are finalized for consumers.
