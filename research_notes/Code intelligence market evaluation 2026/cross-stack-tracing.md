# Cross-Stack Tracing and Linking Patterns for Static Indexers

This document evaluates actionable patterns for linking frontend, backend, and database layers in a static indexer environment (no runtime instrumentation). It compares market leaders like Sourcegraph and Greptile, along with full-stack framework strategies and OpenAPI-driven tools.

## How do modern code intelligence tools perform cross-stack tracing without runtime instrumentation?

### Takeaway
Modern tools like Sourcegraph and Greptile use a combination of precise symbol indexing (SCIP), graph-based relationship mapping, and agentic multi-hop exploration to bridge stack boundaries.

### Cited Findings
- **Sourcegraph (SCIP):** Uses the Source Code Intelligence Protocol (SCIP) to create a language-agnostic index. Cross-repository navigation is achieved by assigning a unique ID to symbols consisting of `package@version + qualified_symbol_name`. When a frontend calls a function defined in a backend package, the indexer resolves the reference via this unique ID. — [Source](https://sourcegraph.com/blog/cross-repository-code-navigation)
- **Greptile (Graph-based Context):** Builds a repository graph encompassing functions, classes, imports, and dependencies. It uses an "agentic detective" approach where an LLM-based agent can recursively search the codebase to follow nested function calls (e.g., following a button `onClick` to a backend service call and then to a database query). — [Source](https://www.greptile.com/docs/how-greptile-works/graph-based-codebase-context)
- **RedwoodJS Studio:** Uses OpenTelemetry (OTel) for runtime observability, but its architecture facilitates static linking by enforcing a clear separation of "cells" and "services," which can be mapped by indexers. — [Source](https://docs.redwoodjs.com/docs/studio)
- **tRPC (T3 Stack):** Facilitates cross-stack linking through "type sharing." The frontend imports the `AppRouter` type from the backend. Static indexers like `scip-typescript` can follow these type-only imports to link a client procedure call directly to its server-side implementation. — [Source](https://github.com/MuellerMarvin/t3-better-auth/issues/2)

### Inferences
- **Symbol-Level Linking is the "Gold Standard":** For frameworks like tRPC, the link is effectively a direct function call in the eyes of a symbol-aware indexer.
- **Agentic Search as a Bridge:** Where symbol-level linking fails (e.g., string-based REST calls), agentic tools like Greptile use LLMs to "connect the dots" by searching for similar patterns or following import chains that static analysis might miss.

### Gaps
- The exact performance overhead of Greptile's "agentic detective" approach vs. Sourcegraph's pre-computed SCIP index for very large codebases (10M+ lines).

## What are the actionable patterns for HTTP client matching and OpenAPI sync in static indexers?

### Takeaway
The primary pattern is to extract client call sites and server route registrations, then join them using a canonical `(METHOD, normalized_path)` key, often using OpenAPI as a universal intermediary.

### Cited Findings
- **Canonical Normalization:** Tools like `tieline` and `ast-graph` normalize parameter forms such as `:id`, `{id}`, and `${id}` to a common placeholder (e.g., `{}`) and reduce both sides to a `(METHOD, path)` key. — [Source](https://github.com/nugehs/tieline)
- **Router Mount Prefix Resolution:** Static indexers must handle router mounting (e.g., an Express router mounted at `/api` in one file and defining a `/users` route in another). Tools trace the `app.use()` calls to reconstruct the full path. — [Source](https://github.com/neat-technologies/neat/commit/247b938a9c8f65b82e31ef1fc7758e288a0f259a)
- **OpenAPI as a Bridge:** `powerducklab` reverse-engineers OpenAPI documents from framework route graphs. The resulting spec serves as a universal contract that both the frontend indexer (calling the contract) and backend indexer (implementing the contract) can link to. — [Source](https://github.com/powerducklab/code-to-openapi)
- **Framework-Specific Extraction:** Practical implementations require specialized "language packs" or "framework packs" that understand the specific routing idioms of Express, FastAPI, Spring, etc. — [Source](https://github.com/clay-good/OpenLore/blob/main/docs/cross-service-topology.md)

### Inferences
- **OpenAPI Sync is the most scalable cross-repo strategy:** Rather than linking every frontend to every backend repo directly, linking both to a shared OpenAPI spec reduces the complexity from \(O(N \times M)\) to \(O(N + M)\).
- **Type-Safe Clients:** Generating clients from OpenAPI (e.g., `openapi-typescript`) makes static linking trivial, as the client methods become direct symbol references.

### Gaps
- Detailed strategies for handling complex URL construction (e.g., helper functions that build URLs dynamically) in purely static environments without falling back to "unverifiable".

## What confidence/fallback patterns are used when exact matches fail?

### Takeaway
Tools use tiered confidence models (e.g., RESOLVED, INFERRED, AMBIGUOUS) and strictly separate proven facts from heuristic guesses to maintain "epistemic honesty."

### Cited Findings
- **StrataGraph Confidence Model:** Uses four bands: `RESOLVED` (compiler-accurate, 0.9-1.0), `EXTRACTED` (deterministic AST read, 0.95-1.0), `INFERRED` (heuristic guess, 0.4-0.8), and `AMBIGUOUS` (fanned-out candidates, <0.4). — [Source](https://stratagraph.dev/docs/accuracy/methodology)
- **Honesty Contract:** OpenLore follows a "nothing on dynamic" rule. If a target is dynamic (e.g., `fetch(endpoint)`), no edge is minted to avoid false positives. It reports these as "unverifiable gaps" instead of guessing. — [Source](https://github.com/clay-good/OpenLore/blob/main/docs/cross-service-topology.md)
- **Unique-Name Fallback:** `staleproof` allows attribute calls `x.m()` to link to methods named `m` in imported repositories if the candidate set is small (1-4) and the name is not generic (not `get`, `set`, etc.). These are labeled as `by-name`. — [Source](https://staleproof.dev/docs/indexing.md)
- **AI Gap Filling:** `powerducklab` uses a "completeness gate" where AI is only invoked to fill specific gaps in the contract that the static engine could not prove, and its output is marked as AI-generated. — [Source](https://github.com/powerducklab/code-to-openapi)

### Inferences
- **Labeling is critical:** Fallback edges must carry their provenance to prevent users (or downstream agents) from treating a guess as a fact.
- **Negative Signal is Valuable:** Reporting "N dynamic calls could not be resolved" is more useful for improving coverage than silently ignoring them or guessing incorrectly.

### Gaps
- Whether any tool successfully uses runtime logs/traces as a feedback loop to "promote" `INFERRED` edges to `RESOLVED` in a hybrid static-runtime index.
