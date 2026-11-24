# MCP and Agent-Oriented Code Intelligence

## Tool Granularity

### Takeaway
Modern MCP servers for code intelligence are moving toward high-granularity toolsets (40+ tools) organized into specialized functional domains, while maintaining a primary task-bundling entry point.

### Cited Findings
- **Industry Trend**: 2026 market leaders (e.g., `repo-context-forge`, `CodeContext-OS`) group tools into servers for Filesystem (6 tools), Symbols/AST (8), Dependencies (6), Git (7), and Context Packs (7) — [Source](https://github.com/negativexq/repo-context-forge)
- **Local State**: The `codebase-intelligence` server provides a moderate-granularity set (~15 tools) covering indexing, exploration, flow tracing, and impact analysis — [Source](backend/apps/mcp/src/ci_mcp/server.py)
- **Specialization**: Market tools differentiate between lexical search, deterministic AST symbol lookup, and semantic dense retrieval, whereas local tools focus primarily on the static graph — [Source](https://glama.ai/mcp/servers/Akgithub2028/CodeContext-OS/tree)

### Inferences
- While high granularity provides flexibility for advanced agents, it increases the risk of "tool fatigue" and high-latency exploration roundtrips.
- The "Ideal MCP" provides granular tools for verification but encourages agents to use a single aggregator for initial discovery.

### Gaps
- How does the performance of 40+ granular tools compare to a few "fat" tools in high-latency MCP transports (e.g., remote SSE)?

## `build_context` Bundling

### Takeaway
The "Ideal" context bundling tool is task-shaped and token-budgeted, returning a ranked package of cited evidence (source, symbols, callers, tests) instead of raw symbol dumps.

### Cited Findings
- **Market Standard**: `get_context` or `build_context` tools now accept a `token_budget` and return a "Context Pack" including `brief`, `freshness`, `evidence`, and `missingEvidence` signals — [Source](https://github.com/MarshallEriksen-Neura/ragcode)
- **Local Implementation**: `build_context` uses a fixed `max_snippets` count rather than a token budget. It bundles node details, source, callers/callees, models, and endpoint traces in one call — [Source](backend/packages/ai/src/ci_ai/tools.py)
- **Ranking**: State-of-the-art bundles use "skeleton" expansion (showing structure while eliding bodies) to fit more context into the token window — [Source](https://github.com/MarshallEriksen-Neura/ragcode)

### Inferences
- The local implementation is functionally complete for symbol discovery but lacks the "budget-aware pruning" necessary for large-scale codebase tasks where context windows are tight.
- Including endpoint traces automatically in `build_context` is a competitive advantage for full-stack intelligence.

### Gaps
- The local tool does not currently support `missingEvidence` reports, which are critical for preventing agent hallucinations when the graph is sparse.

## Citation Contracts & Grounding

### Takeaway
Grounding is shifting from "raw snippets" to "verified evidence," where citation contracts ensure every claim is linked to a file:line range and checked for freshness.

### Cited Findings
- **Grounding Mechanism**: Market tools (e.g., `RagCode`) provide an `edit-readiness` verdict (e.g., `safe_to_edit_after_reading`) based on evidence completeness — [Source](https://github.com/MarshallEriksen-Neura/ragcode)
- **Citation Protocol**: Citations must be checked against observed source paths and ranges; unsupported citations must be reported rather than accepted — [Source](https://github.com/negativexq/repo-context-forge)
- **Local State**: The codebase uses `collect_refs` to extract node ids and file:line locations from results, providing basic grounding for citations — [Source](backend/packages/ai/src/ci_ai/toolspec.py)

### Inferences
- Local tools provide sufficient metadata for basic citations, but lack a formal "contract" that validates if the provided snippets actually support the agent's proposed plan.
- The reliance on `redaction` and `sanitize_for_llm` locally ensures security but may conflict with strict citation range verification if large blocks are omitted.

### Gaps
- Is there a standard JSON schema for "Citation Contracts" that can be shared across different MCP clients (Claude, Cursor, Copilot)?

## Objective: Gap Analysis vs Ideal MCP

| Tool | Ideal 2026 Feature | Local `codebase-intel` Status | Gap / Opportunity |
| --- | --- | --- | --- |
| `list_projects` | Federation-aware; cross-repo dependencies. | Local projects only; single-repo context. | **Federation**: Missing cross-repo link detection. |
| `trace_endpoint` | Traces through message queues and external services. | Traces HTTP, Models, and Jobs within the repo. | **Breadth**: Add external service/API contract tracing. |
| `impact` | Risk-scored; "fail-on" CI integration; ownership metadata. | BFS-based blast radius; hop-distance ranking. | **Risk Scoring**: Add explicit ownership and tier-based risk levels. |
| `read_source` | Skeleton expansion; token-capped; secret-redacted. | Line-range based; redacted; fixed character cap. | **Adaptive Skeletons**: Elide function bodies automatically for large files. |
| `build_context` | Task-shaped; token-budgeted; `missingEvidence` signal. | Symbol-shaped; snippet-count based; no "missing" signal. | **Task Grounding**: Re-orient from "symbol context" to "task context". |

### Cited Findings
- **Impact Depth**: Ideal tools distinguish between "High Risk" (>5 consumers) and "Low Risk" changes — [Source](https://codeknowledge.dev/docs/MCP-Tools)
- **Local Impact**: Uses `impact_for_request` to calculate affected nodes but lacks the "ownership" and "risk factors" required for PR-gate maturity — [Source](backend/packages/core/src/ci_core/insights.py)
