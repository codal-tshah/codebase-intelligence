# Research: comparable tools, enterprise features, graph UX

Gathered 2026-11-14 with web search. **Research only:** no repository code, paths or secrets were sent anywhere, and no code or UI assets were copied. Most results were secondary sources (blogs, directories), so claims are marked:

- **(official)**: from the vendor's own docs or blog
- **(secondary)**: third-party write-up, not checked against official docs
- **(unverified)**: one low-quality source only

Earlier notes on Understand Anything, the nu demo and CIS are in [competitive-notes.md](competitive-notes.md).

## 1. Comparable tools

| Tool | What it does | Relevant to us | Sources |
|---|---|---|---|
| **CodeBoarding** | Open-source CLI: static analysis plus LLM agents produce Mermaid architecture diagrams. Has a VS Code extension and a GitHub Action that regenerates diagrams on push. Python, TS/JS, Java, Go, PHP. *(secondary)* Nodes link to source or sub-diagrams. *(unverified)* Licence is reported inconsistently: check the repo. | Mermaid output for docs and CI is a proven distribution channel. Our `ci docs` covers it, but a GitHub Action example would help. | [dev.to](https://dev.to/brovatten/codeboarding-interactive-diagrams-of-code-2bbe), [PyPI](https://pypi.org/project/codeboarding/), [brightcoding blog](https://blog.brightcoding.dev/2026/02/16/codeboarding-ai-powered-interactive-diagrams-for-codebases) |
| **DeepWiki** (Cognition) | Replace `github.com` with `deepwiki.com` to get an LLM-generated wiki with diagrams and chat. Private repos are paid. `.devin/wiki.json` steers generation. *(secondary)* | Zero-setup entry point and a config file that steers output. Cloud-only, so not usable for air-gapped code. That's our differentiator. | [HF blog](https://huggingface.co/blog/lynn-mikami/deepwiki), [codersera guide](https://codersera.com/blog/deepwiki-complete-guide-2026) |
| **Google Code Wiki** | Public preview (Nov 2025). Gemini-generated wiki regenerated after each commit; architecture, class and sequence diagrams; each section links to code; chat. A CLI extension for internal repos was announced. *(official blog; details secondary)* | "Regenerate on every commit" plus "every section links to code" are what make generated docs trustworthy. We have freshness and source links; we lack sequence diagrams. | [Google Developers Blog](https://developers.googleblog.com/en/introducing-code-wiki-accelerating-your-code-understanding/), [InfoQ](https://infoq.com/news/2025/11/google-code-wiki/), [The Register](https://www.theregister.com/2025/11/17/google_previews_code_wiki/) |
| **Sourcegraph** | Code search plus navigation. Precise navigation uses SCIP indexes uploaded from CI or auto-indexing; search-based fallback covers 40+ languages; self-hosted on Docker Compose or Kubernetes. *(official)* | Index in CI and upload later. Graceful fallback from precise to heuristic results; we do the same with confidence on HTTP links. | [Precise navigation](https://sourcegraph.com/docs/code-navigation/precise-code-navigation), [Syntactic navigation](https://sourcegraph.com/docs/code-navigation/syntactic-code-navigation) |
| **Swimm** | Docs coupled to code. Auto-sync runs in CI and fails a check when a code change makes a doc stale. GitHub App. SAML SSO. *(official for auto-sync; SSO secondary)* | A "stale doc" CI check maps to our `impact --fail-on` gate and freshness API. SSO is table stakes for enterprise buyers. | [Auto-sync docs](https://docs.swimm.io/features/keep-docs-updated-with-auto-sync), [Continuous documentation](https://docs.swimm.io/new-to-swimm/continuous-documentation) |
| **Backstage** | Software catalog. The Catalog Graph plugin shows entity relations (`ownedBy`, `dependsOn`, API relations) with depth and kind filters. Relations are declared in YAML, not inferred. *(official)* | Depth and kind filters on a relation graph: our Explore Depth plus layer filters. We infer from code, which Backstage can't. A Backstage plugin is a plausible integration later. | [Creating the catalog graph](https://backstage.io/docs/features/software-catalog/creating-the-catalog-graph), [npm plugin](https://npmjs.com/package/@backstage/plugin-catalog-graph) |
| **CodeSee** | Codebase maps. Acquired by GitKraken in May 2024; maps folded into the GitKraken DevEx platform. *(official press release)* | A standalone "code map" product didn't survive alone; maps fit inside a broader workflow (review, onboarding, CI). | [GitKraken press release](https://gitkraken.com/press/gitkraken-acquires-codesee-launches-devex-platform), [SD Times](https://sdtimes.com/software-development/gitkraken-acquires-codesee-launches-new-devex-platform/) |
| **Greptile** | Builds a graph of files, functions and dependencies; AI PR review using it. Self-hosted via Docker Compose, Helm or air-gapped, with bring-your-own LLM. *(official docs, partly secondary)* | Enterprise buyers ask for air-gapped deployment plus BYO model. We are local-first with LiteLLM, so we can claim this honestly once Docker is verified. | [Greptile docs](https://www.greptile.com/docs/introduction), [key features](https://www.greptile.com/docs/code-review/key-features) |
| **CodeDebrief** | No reliable source found. | – | – |

## 2. Enterprise code-intelligence features (what buyers expect)

| Feature | Seen in | We have |
|---|---|---|
| Search with filters | Sourcegraph, Backstage | ⌘K search with node types; layer filters |
| Saved views and shareable links | Backstage graph routes, DeepWiki URLs | Deep links (`#/p&v&n&e`); no named saved views |
| Export: Mermaid, Markdown, SVG, PNG, JSON | CodeBoarding (Mermaid), Code Wiki | JSON (server) and Mermaid docs (`ci docs`); per-view client export added this pass (see REPORT) |
| Staleness indicators | Swimm auto-sync, Code Wiki | Freshness banner plus `/freshness` |
| Commit-to-commit diff | Greptile, Swimm | `impact --base` (impact, not a visual diff) |
| RBAC, audit log, SSO | Swimm (SSO), Sourcegraph Enterprise | API key in server mode only; no RBAC, SSO or audit log |
| Offline / air-gapped | Greptile, Sourcegraph self-hosted | Local-first; fonts vendored this pass |
| CI integration | Swimm, CodeBoarding Action, Sourcegraph CLI upload | `ci impact --fail-on`, `ci docs`; no packaged Action |
| API | All | REST plus MCP |

## 3. Graph UX and accessibility

- **Semantic zoom and level of detail:** show less, but bigger, information when zoomed out (labels only), and full cards when zoomed in. yFiles recommends simpler rendering at low zoom for large-diagram performance. *(official yFiles docs)* Research on large graphs keeps top-ranked labels readable at every zoom level. *(paper)* Sources: [yFiles large graph performance](https://docs.yfiles.com/yfiles-html/dguide/large_graph_performance/), [arXiv 2605.17498](https://arxiv.org/pdf/2605.17498).
- **React Flow image export:** the official example uses `html-to-image`, pinned to 1.11.11. A known issue clips edges outside the viewport. *(official example; issue secondary)* We generate SVG from our own layout instead, so no dependency and no clipping. Sources: [reactflow.dev download-image](https://reactflow.dev/examples/misc/download-image), [lightrun issue summary](https://lightrun.com/answers/wbkd-react-flow-edges-are-not-visible-outside-react-flow__viewport-when-we-export-the-canvas-to-png).
- **WCAG 2.2 AA** additions that matter here *(W3C)*:
  - 2.4.11 Focus Not Obscured (Minimum)
  - 2.5.8 Target Size (Minimum): 24×24 CSS px, or enough spacing
  - 3.3.8 Accessible Authentication

  Text contrast stays at 4.5:1 and non-text (selection, focus) at 3:1. Source: [W3C: What's new in WCAG 2.2](https://w3.org/WAI/standards-guidelines/wcag/new-in-22/).
- **Selection and focus (Primer):**
  - Selected state counts as non-text contrast, so 3:1.
  - The accent token covers selected, focused and highlighted states.
  - When colour alone signals state, add a non-colour cue such as an outline.

  Sources: [Primer colour considerations](https://primer.style/guides/accessibility/color-considerations), [Primer focus management](https://primer.style/accessibility/focus-management/).
- **Design systems** (Linear, Primer, Atlassian, Radix, shadcn): not re-researched this pass. The existing token system (one accent, neutral paper, 4px spacing) already follows the shared pattern of a small token set with semantic roles. **Not verified against each system's docs.**

## 4. What we take from this

1. Air-gapped plus deterministic is our clearest differentiator against DeepWiki and Code Wiki (cloud LLM). Keep every asset local: fonts are now vendored.
2. Each node and each doc section must link to its source. We do this in the Inspector and in Mermaid docs.
3. Export and CI checks are how diagrams spread inside companies (CodeBoarding Action, Swimm check). Client-side exports were added; a packaged GitHub Action is on the roadmap.
4. Semantic zoom is the standard answer for large graphs. Implemented as three zoom levels.
5. Enterprise identity (SSO, RBAC, audit) is expected but needs an auth proxy or IdP integration: roadmap, see [GAPS.md](GAPS.md).
