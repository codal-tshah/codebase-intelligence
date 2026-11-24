# Code Intelligence Parsing & Graph Technologies Research

## tree-sitter

### Takeaway
Tree-sitter is the foundational layer for high-performance, multi-language syntactic extraction, offering unparalleled speed for incremental updates and robust error recovery.

### Cited Findings
- **Offer**: An incremental parsing library that builds a concrete syntax tree (CST) and provides a query language for pattern matching — [Official Site](https://tree-sitter.github.io/tree-sitter/).
- **Problem**: Solves the need for fast, robust parsing that can handle syntax errors gracefully and update incrementally as code changes — [GitHub](https://github.com/tree-sitter/tree-sitter).
- **Vs Custom AST**: More maintainable than building custom parsers (e.g., ANTLR) for every language; allows sharing grammars across tools (Atom, VS Code, GitHub) — [Fluid Attacks Docs](https://docs.fluidattacks.com/stack/dependencies/tree-sitter).
- **Accuracy/Perf**: Benchmarks show initial parses of ~10ms for 80KB files, with incremental re-parses after edits being effectively free (~0ms for no-edit, ~4-16ms for small edits) — [tree-sitter.zig benchmarks](https://muhammad-fiaz.github.io/tree-sitter.zig/guide/performance.html).
- **Limitations**: Purely syntactic; lacks semantic understanding, type information, or cross-file resolution out of the box — [ast-grep Comparison](https://ast-grep.github.io/advanced/tool-comparison).
- **Maintenance**: Extremely active; backed by GitHub/Microsoft and a large open-source community — [GitHub Activity](https://github.com/tree-sitter/tree-sitter).
- **License**: MIT License; highly compatible with proprietary backends — [LICENSE](https://github.com/tree-sitter/tree-sitter/blob/master/LICENSE).
- **Adopt/Partial/Retain**: **Retain**. It is the industry standard for the "parsing" stage.

### Inferences
- Tree-sitter's incremental parsing is a key differentiator for IDE-like responsiveness.

### Gaps
- Specific benchmarks for Python-specific incremental parsing in the `backend` context of this project were not found.

## ast-grep

### Takeaway
ast-grep provides an ergonomic, high-level pattern matching layer on top of Tree-sitter, significantly simplifying the extraction of syntactic relationships.

### Cited Findings
- **Offer**: A CLI tool and Rust library for structural code search and rewriting using Tree-sitter ASTs — [ast-grep GitHub](https://github.com/ast-grep/ast-grep).
- **Problem**: Replaces complex, brittle AST walker code with intuitive S-expressions or code-like patterns (metavariables) — [Official Docs](https://ast-grep.github.io/advanced/how-ast-grep-works).
- **Vs Custom AST**: Much faster to implement relationship extraction rules; patterns like `import { $A } from '$B'` are easier to write and maintain than manual node traversal — [Tool Comparison](https://ast-grep.github.io/advanced/tool-comparison).
- **Accuracy/Perf**: Highly performant due to Rust implementation and multi-threaded processing — [Comparison With Other Frameworks](https://ast-grep.github.io/advanced/tool-comparison).
- **Limitations**: Syntactic only; cannot resolve types or follow data flow across files — [Fluid Attacks Docs](https://docs.fluidattacks.com/stack/dependencies/tree-sitter).
- **Maintenance**: Active, community-supported, but has high maintainer concentration — [DiscoverGit Analysis](https://discovergit.app/repo/ast-grep/ast-grep).
- **License**: MIT License; safe for proprietary use — [LICENSE](https://github.com/ast-grep/ast-grep/blob/main/LICENSE).
- **Adopt/Partial/Retain**: **Adopt (Partial)**. Excellent for replacing boilerplate AST walkers.

### Inferences
- ast-grep can serve as a "query engine" for the graph builder, allowing declarative extraction logic.

### Gaps
- Long-term maintenance stability is a risk compared to corporate-backed tools.

## Semgrep

### Takeaway
Semgrep is a powerful semantic analysis engine that bridges the gap between syntactic patterns and deep static analysis (taint, data flow), but with licensing complexity.

### Cited Findings
- **Offer**: A static analysis engine that matches code patterns while performing constant propagation, taint analysis, and data-flow tracking — [Semgrep Official](https://semgrep.dev/).
- **Problem**: Solves complex semantic discovery tasks (e.g., taint tracking) that purely syntactic tools miss — [Semgrep Docs](https://docs.semgrep.dev/faq/comparisons/opengrep).
- **Vs Custom AST**: Provides high-level semantic primitives (taint, flow) that are extremely difficult to build correctly in a custom walker — [Semgrep vs Opengrep](https://docs.semgrep.dev/faq/comparisons/opengrep).
- **Accuracy/Perf**: Precise but slower than Tree-sitter; engine is optimized with OCaml 5 multicore — [Semgrep Pro vs OSS](https://docs.semgrep.dev/semgrep-pro-vs-oss).
- **Limitations**: The community registry rules have restrictive licensing — [Licensing](https://docs.semgrep.dev/licensing).
- **Maintenance**: Very high; backed by Semgrep, Inc. — [About Semgrep](https://semgrep.dev/about/).
- **License**: Engine is LGPL-2.1; Rules Registry is "Semgrep Rules License v1.0" (Internal use OK, but cannot be bundled in competing products) — [Licensing Page](https://docs.semgrep.dev/licensing).
- **Adopt/Partial/Retain**: **Adopt (Specific)**. Use for deep semantic extraction.

### Inferences
- Best choice for "Level 2" intelligence (data flow, taint).

### Gaps
- Direct head-to-head performance benchmarks for 1M+ LOC indexing were not found.

## SCIP / LSIF

### Takeaway
SCIP is the modern, scalable successor to LSIF, providing a standardized protobuf-based transmission format for precise, cross-repository code intelligence. It significantly improves performance and developer velocity by replacing LSIF's opaque integer-based graph with a document-centric format using human-readable symbol IDs.

### Cited Findings
- **Offer**: SCIP (Sourcegraph Code Intelligence Protocol) is a protobuf-based index format; LSIF (Language Server Index Format) is its deprecated JSON-LD predecessor — [SCIP Design Docs](https://github.com/sourcegraph/scip/blob/main/docs/DESIGN.md).
- **Problem**: Standardizes "precise" navigation (defs, refs) across repos, avoiding the false positives of search-based methods — [Sourcegraph Blog](https://sourcegraph.com/blog/announcing-scip).
- **Vs Custom AST**: Replaces ad-hoc graph schemas with a industry-standard transmission format; handles cross-repo relationships by design — [Indexers Docs](https://sourcegraph.com/docs/code-navigation/writing-an-indexer).
- **Accuracy/Perf**: SCIP is 4-5x smaller than LSIF (gzipped) and avoids LSIF's global ID constraints, enabling file-level incremental indexing and parallel processing — [SCIP Design Docs](https://github.com/sourcegraph/scip/blob/main/docs/DESIGN.md).
- **Limitations**: A transmission format, not a queryable database; requires indexers to emit precise symbol strings following a URI-like grammar (`<scheme> <manager> <package> <version> <descriptors>`) — [SCIP Grammar](https://github.com/scip-code/scip/blob/main/docs/scip.md).
- **Maintenance**: Active, moving to open governance; LSIF is deprecated and removed from Sourcegraph core — [Sourcegraph Future of SCIP](https://sourcegraph.com/blog/the-future-of-scip).
- **License**: Apache-2.0 — [SCIP LICENSE](https://github.com/sourcegraph/scip/blob/main/LICENSE).
- **Adopt/Partial/Retain**: **Adopt (Transmission)**. Use SCIP for indexing exports and cross-repo links.

### Inferences
- SCIP's focus on human-readable string IDs makes debugging and merging indexes significantly easier than LSIF's opaque integers.
- Implementing SCIP would allow "Codebase Intelligence" to link different projects in its `index.db` simply by matching symbol strings.

### Gaps
- Support for Python-specific SCIP indexers beyond general LSP wrappers is less mature than for Go or TypeScript.

## PyCG

### Takeaway
PyCG is a state-of-the-art, fully static call-graph generator for Python, recently revived to support modern Python versions with high precision (~94%).

### Cited Findings
- **Offer**: A fully static analysis tool that generates call graphs for Python without importing or executing the analyzed code — [PyCG GitHub](https://github.com/vitsalis/PyCG).
- **Problem**: Extracts inter-procedural call relationships safely, including support for closures, inheritance, and decorators — [PyCG Arxiv](https://arxiv.org/abs/2103.00587).
- **Vs Custom AST**: Much deeper than simple AST walkers; handles complex Python dynamic features statically — [PyCG GitHub](https://github.com/vitsalis/PyCG).
- **Accuracy/Perf**: 94.5% precision / 87.8% recall for internal edges in real-world packages (Python 3.12); reached 90.4% recall for inside-package edges against DyPyBench execution traces — [PyCG Evaluation](https://github.com/vitsalis/pycg-evaluation).
- **Limitations**: Struggles with scaling to large generic libraries (like the full standard library) without stubs; misses dynamic constructs like `eval`, `getattr`, and `setattr` — [PyCG GitHub](https://github.com/vitsalis/PyCG).
- **Maintenance**: Archived in 2023, but development restarted in 2026 for Python 3.12+ — [PyCG GitHub](https://github.com/vitsalis/PyCG).
- **License**: Apache-2.0 — [PyCG LICENSE](https://github.com/vitsalis/PyCG/blob/main/LICENSE).
- **Adopt/Partial/Retain**: **Adopt (Partial)**. Use for specialized call-graph extraction.

### Inferences
- Essential for mapping how values flow through complex Python codebases without the risks of dynamic analysis.
- Reliable for standard function/method calls and class hierarchies, but has "known-blind-spots" in highly dynamic frameworks.

### Gaps
- Currently not available on PyPI, requiring manual integration or git-submodule usage.

## Joern / Code Property Graphs (CPG)

### Takeaway
Joern and the CPG model provide the most comprehensive graph representation for code analysis, unifying AST, CFG, and PDG via shared statement nodes, but carry significant resource overheads.

### Cited Findings
- **Offer**: Joern is an analysis platform; CPG is a unified representation combining AST, CFG, and PDG — [Joern GitHub](https://github.com/joernio/joern/).
- **Problem**: Enables deep, complex queries across all layers of code structure (e.g., data flow across control paths) by anchoring nodes to statements — [Joern.io](https://joern.io/impact/).
- **Vs Custom AST**: Combines multiple graph types into one; provides a specialized graph database (flatgraph) and query DSL — [Joern 4.0 Changelog](https://github.com/joernio/joern/blob/master/changelog/4.0.0-flatgraph.md).
- **Accuracy/Perf**: Highly precise for vulnerability discovery. Linux 4.1.16 (48M nodes, 431M edges) requires ~30GB heap for import with the modern `flatgraph` backend (down from 80GB with OverflowDB) — [Joern 4.0 Changelog](https://github.com/joernio/joern/blob/master/changelog/4.0.0-flatgraph.md).
- **Limitations**: Extremely memory-intensive (30GB-128GB for large repos); JVM dependency; primarily optimized for security research rather than general code navigation — [Joern Issue 4256](https://github.com/joernio/joern/issues/4256).
- **Maintenance**: Very active, strong research community and commercial backing — [Joern GitHub](https://github.com/joernio/joern/).
- **License**: **Apache-2.0** (Permissive) — [Joern Impact](https://joern.io/impact/).
- **Adopt/Partial/Retain**: **Defer**. Too resource-intensive for general codebase intelligence unless deep security auditing or complex data-flow queries are required.

### Inferences
- CPG is the "gold standard" for graph depth, but the cost/performance trade-off is currently unsuitable for lightweight indexing on consumer hardware.
- Unification allows jumping from syntactic locations directly to data-flow dependencies without manual lookup tables.

### Gaps
- Python-specific parsing via `pysrc2cpg` is significantly slower end-to-end (1.9x to 6.7x) than native AST parsing.

## Final Recommendation Table

| Technology | Rubric Status | Recommended Action | Justification |
| :--- | :--- | :--- | :--- |
| **tree-sitter** | Retain | **Retain** | Foundational, fast, incremental parsing. |
| **ast-grep** | Adopt Partial | **Adopt (Partial)** | Simplifies syntactic extraction logic. |
| **Semgrep** | Adopt Specific | **Adopt (Specific)** | Best for data-flow/taint analysis. |
| **SCIP** | Adopt | **Adopt** | Best-in-class for cross-repo index transmission. |
| **PyCG** | Adopt Partial | **Adopt (Partial)** | Specialized for Python static call-graphs. |
| **Joern / CPG** | Defer | **Defer** | High memory overhead; overkill for nav. |
| **LSIF** | Deprecated | **Retain (None)** | Deprecated in favor of SCIP. |

## Key Objective: Improving Static Extraction vs Analytics
- **Tree-sitter** and **ast-grep** directly improve the speed and maintainability of the **extraction phase**.
- **PyCG** improves the **depth of extracted relationships** (call graphs) without dynamic risks.
- **SCIP** improves the **interoperability** and **scale** of the resulting index.
- **Semgrep** and **Joern** lean toward **downstream analytics** (security, flow) but can inform the extraction of more complex edges.
