# Security notes

Scope: the API (`ci serve`), the dashboard, the CLI and the MCP server. Report issues privately to the maintainers, not in public issues.

## Data never leaves the machine

- Indexing, graph building and every view are local. No telemetry.
- The dashboard loads no third-party assets. Fonts are bundled, and the offline E2E test fails if any request leaves `localhost`.
- The optional assistant LLM (`ALLOW_LLM`, LiteLLM) is the only path that sends code context out, and only to the endpoint you configure (`LLM_API_BASE` can be a local model). Off by default. Tool-only mode answers from the graph.
- GitHub tokens: see [private-repos.md](private-repos.md). They are sent only as a header to `github.com` for one git process, and never logged or returned.

## Modes and authentication

| Mode | Who can call the API | Notes |
|---|---|---|
| `local` (default) | Anyone who can reach the port (binds 127.0.0.1 by default) | For one trusted user |
| `server` (`CI_MODE=server`) | Requests with `X-API-Key` or `Authorization: Bearer` equal to `CI_API_KEY` (constant-time compare). Only `/health` (and `/api/health` under `ci serve --ui`) is public | Requires `CI_PROJECT_ROOTS`; git-URL ingest disabled (API and MCP); `abs_path` omitted from `/source` |

The dashboard asks for the key on the first 401 and keeps it in `sessionStorage` for that tab only. It is never stored in `localStorage`, cookies or the URL. SSO, RBAC and an audit log are not built in; put an identity-aware proxy (for example oauth2-proxy) in front for those (roadmap).

## Input handling

- **Path traversal:** `/source` serves only files that were indexed **and** resolve inside the project root (`ci_core.source.resolve_source_path`). `.env`, keys and anything unindexed are unreachable. Tests: `test_source_is_allowlisted_to_indexed_files`.
- **Bounded params:**
  - node ids ≤ 512 chars
  - `expanded` ≤ 500 ids
  - `extra_child_offsets` ≤ 200
  - `path` ≤ 1024
  - search `q` ≤ 200
  - `limit` and `depth` ranges

  Over-limit requests get 422. Test: `test_graph_and_source_params_are_bounded`.
- **Project refs** resolve to registered projects only. In server mode ingest is confined to `CI_PROJECT_ROOTS`.
- **Git refs** for `impact --base` reject leading `-` (no option injection).

## Rendering repository content (XSS)

Repository text (names, docstrings, summaries, LLM answers) is untrusted.

- React escapes all text by default.
- The one `dangerouslySetInnerHTML` (`ProjectSummaryCard.MarkdownInline`) escapes `& < > "` **before** applying its two inline patterns (bold, code).
- Assistant markdown uses `react-markdown` without raw-HTML plugins, so HTML in answers is shown as text. Links are limited to its default safe URL transform plus our `node:` and `source:` schemes.
- Exports escape for their format: XML entities in SVG, `#quot;` and `#lt;` in Mermaid labels with ids re-numbered, and `\|` in Markdown tables. Unit tests cover each (`export/exportView.test.ts`).

## Dependency audit (2026-11-14)

| Check | Result |
|---|---|
| `npm audit --omit=dev` (shipped bundle) | **0** vulnerabilities |
| `npm audit` (incl. dev tools) | 13 (dev-only: Vite, Vitest, typescript-eslint chain). Fixes need major upgrades: tracked, not forced |
| `pip-audit` on the locked backend deps (`uv export`) | **0** after bumping `filelock` to 4.2.10 (was 13 CVEs via litellm → huggingface-hub) |
| Licences (`scripts/check_licenses.py`, see [LICENSES.md](LICENSES.md)) | 0 shipped JS packages flagged. 2 Python flagged for review: `certifi` (MPL-2.0, file-level copyleft, used unmodified) and `shellingham` (ISC; flagged only for its classifier spelling) |

Re-run:

```bash
cd frontend && npm audit --omit=dev
cd backend && uv export --format requirements-txt --no-hashes --all-packages --no-emit-workspace > /tmp/reqs.txt && uvx pip-audit -r /tmp/reqs.txt --disable-pip --no-deps
cd backend && uv run python ../scripts/check_licenses.py > ../docs/LICENSES.md
```

`npm audit` and `pip-audit` send package names and versions (not code) to the npm and PyPI advisory services. Run them from a connected machine if the deployment is air-gapped.

## Known limits

- The index lock is cross-process (file lock). The in-memory graph cache is per process, so run a single API worker.
- No rate limiting. Put the server behind a proxy if it is shared.
- Docker image: built and run in local and server mode (non-root `ci` user, healthcheck); the E2E suite passes against it. See [REPORT.md](REPORT.md).
