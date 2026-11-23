# Competitive notes

What comparable tools do well, where we stand, and what we're adopting. Reviewed 2026-11-14; re-check quarterly. Research only: no code or UI assets were copied.

## References

| Reference | What it is | Licence | Sources read |
|---|---|---|---|
| **nu demo** | Next.js app: GitHub URL (+ optional token) → chat and a summary over code chunks retrieved from Pinecone (GPT-4o) | Not stated | [demo](https://codebase-intelligence-nu.vercel.app/) landing page, [repo](https://github.com/nancy-kataria/codebase-intelligence) README and route list |
| **Understand Anything (UA)** | Agent plugin: Tree-sitter structure + LLM summaries → knowledge-graph JSON, dashboard, tours, chat, diff and onboarding commands | MIT | [site](https://understand-anything.com/#install), [repo](https://github.com/Egonex-AI/Understand-Anything) README |
| **CIS** (MCP Market) | Rust daemon, Tree-sitter code graph over MCP stdio: 37 navigation, search and speculative-edit tools | MIT | [listing](https://mcpmarket.com/server/codebase-intelligence-system), [repo](https://github.com/abdissa-png/codebase-intelligence-system) README |

The nu demo's form wasn't submitted, so its post-ingest screens are known from the README only. I didn't read UA's MCP package README.

## What each does well

**nu demo**
- One screen: repository URL, optional token, *Initialize*.
- Explains tokens and GitHub's rate limit right on the form.
- Checks the repository is reachable before ingesting.
- Zod validation on every API route.

**Understand Anything**
- One-line install into about 18 agents and IDEs.
- The graph is a committable JSON file, plus a read-only `npx` viewer that needs no LLM.
- `--auto-update` git hook keeps the graph current.
- Domain view (business flows), onboarding and diff-review commands.
- Broad file-type coverage (Docker, Terraform, SQL, Markdown).

**CIS**
- IDE-style navigation for agents: `go_to_definition`, `find_references`, `find_symbol_at`.
- `build_context` packs relevant code for an agent in one call.
- Hybrid keyword and semantic search; a file watcher re-indexes changes.
- Nine languages.

## Capability matrix

✅ have · ⚠️ partial · ❌ missing · ↔ intentionally different

| Capability | nu demo | UA | CIS | Us | Where (ours) |
|---|---|---|---|---|---|
| Install into Claude Code / Cursor | – | ✅ | ✅ | ✅ `install.sh`, plugin, Cursor rule (not published) | `integrations/` |
| Ingest a GitHub URL | ✅ API | ❌ | ❌ | ✅ shallow clone | `ci_parsers.files` |
| Private repos | token in browser | ❌ | ❌ | ↔ server env token | `CI_GITHUB_TOKEN`, [private-repos.md](private-repos.md) |
| Access preflight | ✅ | – | – | ✅ `/git/check`, live in the form | `check_git_access`, `IngestPanel.tsx` |
| Deterministic static graph | ❌ | ✅ | ✅ | ✅ | analyzers |
| Framework semantics (routes, ORM, DI, frontend→backend HTTP) | ❌ | ⚠️ LLM | ❌ | ✅ unique | `adapters/*`, `ci_core.analysis` |
| Hierarchical drill-down | ❌ | ✅ | – | ✅ Explore | `views/explore.py` |
| API flow, ER, jobs, integrations views | ❌ | ❌ | ❌ | ✅ unique | `ci_core/views/` |
| Domain / business-flow view | ❌ | ✅ | ❌ | ❌ | – |
| Tour / onboarding | ⚠️ | ✅ | ❌ | ⚠️ tour only | `insights.build_tour` |
| Chat with citations | ✅ | ✅ | ❌ | ✅ graph tools, LLM optional | `ci_ai.agent` |
| Semantic search | ✅ | ✅ | ✅ | ⚠️ placeholder embeddings | `ci_ai` chunks |
| Impact, path, PR gate | ❌ | ⚠️ | ⚠️ | ✅ `impact --base --fail-on` | `insights`, CLI |
| References / context packing | ❌ | ❌ | ✅ | ✅ `find_references`, `build_context` | `ci_ai.tools`, MCP |
| Keep index fresh | nightly wipe | ✅ hook | ✅ watcher | ✅ `ci hook install` + dashboard banner | CLI, `FreshnessBanner` |
| Output viewable without a server | ❌ | ✅ JSON + viewer | ❌ | ⚠️ Mermaid via `ci docs`, JSON via `ci export` | `ci_core.docgen` |
| Image export | ❌ | ✅ | ❌ | ❌ | – |
| Language breadth | any text | 26+ file types | 9 languages | ⚠️ Python, TypeScript (plugin API) | `analyzers` entry points |
| Optimization suggestions | ❌ | ❌ | ❌ | ✅ unique | `ci_core.suggestions` |
| Shared-server auth | ❌ | ❌ | ❌ | ⚠️ API key; the dashboard doesn't send it | `ci_api` |

## Positioning

The references either chat over raw code chunks (nu demo), sketch the codebase with LLM help (UA), or give an agent IDE-style navigation (CIS). We answer **what actually happens when this code runs**, deterministically:
- an endpoint traced from the UI component through the handler, services and models to the database
- background jobs and what they write
- the blast radius of a change, usable as a PR gate in CI
- ER diagrams and refactoring leads

It's static and reproducible, and works without an LLM. The same graph is available in the dashboard, CLI, MCP and as Markdown docs committed to the repo. That fits Codal's full-stack Django/FastAPI + React/Nest client work: onboarding, reviews and client-facing audits, including private repositories via a server-side token. Our gaps are breadth (languages, install reach), not depth.

## Adopt / Defer / Skip

| Decision | Idea (source) | Why | Status |
|---|---|---|---|
| Adopt | Access preflight (nu) | Failures are cheap and clear | **Done**: `GET /git/check`, live check in the ingest form, preflight in `POST /projects/analyze` |
| Adopt | Post-commit hook (UA, CIS) | A stale graph undermines trust | **Done**: `ci hook install/uninstall/status`; pairs with the existing freshness banner |
| Adopt | `build_context`, `find_references` (CIS) | Agents need one call, not five | **Done**: GraphTools, agent toolspec, MCP |
| Adopt | One-line install (UA) | Adoption depends on it | **Done**: `integrations/install.sh`; publishing the marketplace is still open |
| Adopt | Committable graph + static viewer (UA) | Reviewers and clients can see it without a server | **Next sprint**: `ci export --html` |
| Defer | Domain / business-flow view (UA) | Needs an LLM pass to be good | P2 |
| Defer | Real embeddings / hybrid search (CIS, nu) | The schema is ready; pick a local model | P2 |
| Defer | PNG/SVG export (UA) | Mermaid docs cover most sharing | P2 |
| Defer | Go/Java analyzers (CIS) | Wait for a client project that needs them | P2 |
| Skip | Token typed in the browser (nu) | A server-env token is safer for shared hosts | – |
| Skip | Speculative edits, branches, merges (CIS) | Not our problem | – |
| Skip | Persona UI, localisation (UA) | Polish without a clear gap | – |
| Skip | Nightly index wipe (nu) | We index incrementally | – |

## Backlog

| Pri | Item | Problem it solves | Where |
|---|---|---|---|
| P0 | Publish the plugin marketplace (repo access, versioning, author and icon) | Teams can't install without cloning by hand | `.claude-plugin/`, `integrations/` |
| P0 | Validate on `codal/internal-bi-llm` and `codal/accis-be` | Not yet proven on real client code | needs `CI_GITHUB_TOKEN` |
| P1 | `ci export --html`: single-file read-only viewer | Share a graph in a PR or client handover without a server | `ci_cli`, frontend build flag reading embedded JSON |
| P1 | Suggestions panel in the dashboard | Leads exist in the API and CLI but not where reviewers look | `App.tsx`, `/suggestions` |
| P1 | Dashboard auth in server mode | The shared server is unusable from the UI | `frontend/src/api.ts`, `ci_api` |
| P2 | Domain view via an LLM pass over endpoints and jobs | Business-level map for PMs and clients | new view + `ci_ai` |
| P2 | Real embedding model, hybrid search | Better recall for vague questions | `ci_ai` chunks |
| P2 | Go / Java analyzers | Client stacks beyond Python/TS | new analyzer packages |

## Done in this pass

- `ci_parsers.check_git_access`, `GET /git/check`, preflight in ingest, live status in `IngestPanel.tsx`
- `GraphTools.build_context` / `find_references` → agent toolspec and MCP tools
- `ci hook install|uninstall|status` (idempotent; preserves an existing hook)
- `integrations/install.sh`
- Tests: `test_git_clone.py`, `test_fullstack_api.py`, `test_cli.py`, `test_mcp.py`
