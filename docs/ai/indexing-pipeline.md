# Indexing pipeline

*Last verified against code: `backend/packages/indexer/src/ci_indexer/pipeline.py`, `backend/packages/indexer/src/ci_indexer/changes.py`, `backend/packages/indexer/src/ci_indexer/analyzers.py`, `backend/packages/core/src/ci_core/analysis.py`, `backend/packages/adapters/django/src/ci_adapters_django/adapter.py`, `backend/apps/api/src/ci_api/autorefresh.py`.*

## Stages

1. **Discover files** — `ci_parsers.files.list_*` with built-in skip dirs, repository **root** `.gitignore` (via `pathspec`; negation supported), optional `.ciignore`, and size caps. Nested `.gitignore` files in subdirectories are **not** applied (only the repo root file).
2. **Analyze** — `ci_indexer.analyzers.analyze_project` runs registered analyzers (entry points `codebase_intelligence.analyzers`).
3. **Merge** — `ci_core.analysis.merge_results`, `link_http_calls` (cross-stack HTTP edges). For each static client call, `match_endpoint` records `literal` or `proxy_prefix` matches on `HTTP_CALLS` edges and matching `http_calls[]` rows; external hosts become `DEPENDS_ON` with `match_variant: external`; unmatched locals get `match_variant: unresolved` on the call record only (no fake edge).
4. **Persist** — `IndexPipeline` rewrites SQLite; updates fingerprints; optional chunk embeddings.
5. **Serve** — `GraphStore.load_index()` invalidates cache on DB change.

## Incremental classification (`changes.py`)

| Level | When |
| --- | --- |
| `SKIP` | No file changes |
| `PARTIAL` | Few cosmetic edits |
| `ARCHITECTURE` | Added/removed files or structural roles (settings, urls, models, …) |
| `FULL` | No baseline, `force`, adapter **version** change, or >50% files touched |

Combined analyzer version string bumps → `FULL` rebuild.

## Adapter versioning

Django: `ADAPTER_VERSION = "6"` in `adapter.py` (namespace packages, SQLAlchemy field types, FastAPI `Annotated` dependency aliases). Bump when edge semantics change so existing projects re-index.

## Concurrency

`index.lock` (fcntl) + per-process `threading.Lock`; `index_in_progress()` blocks project delete. API startup marks orphan `running` jobs failed.

## Git hooks (`ci hook install`)

Hooks: `post-commit`, `post-merge`, `post-checkout`, `post-rewrite` — background incremental re-index of repo at hook path.

## Auto-refresh

Env `CI_AUTO_REFRESH_SECONDS` (default `60`, `0` off). API loop (`autorefresh.py`) incremental-indexes projects with `settings.auto_refresh` when `git HEAD` differs from indexed `commit_sha`.

## Jobs

`IndexJobRecord` statuses: `pending`, `running`, `completed`, `failed`. Poll `GET .../jobs/{id}` or CLI JSON.

## Failure behaviour

Failed job stores `error` on job row; graph from last successful index remains until a successful rewrite.
