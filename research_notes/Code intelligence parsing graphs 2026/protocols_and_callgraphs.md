# SCIP, LSIF, and PyCG for Static Code Intelligence

## What are the trade-offs between LSIF and SCIP for large-scale graph indexing?

### Takeaway
SCIP (Sourcegraph Code Intelligence Protocol) is a Protobuf-based evolution of LSIF that replaces a complex graph-based JSON structure with a document-centric streaming format, significantly improving scalability and developer velocity.

### Cited Findings
- SCIP uses human-readable string IDs for symbols (e.g., `scip-python pypi requests 2.25.1 requests/get.`) instead of LSIF's opaque numeric IDs, making indexes easier to debug and merge. — [Source](https://sourcegraph.com/blog/announcing-scip)
- LSIF requires maintaining a global graph state in memory to assign numeric IDs, which hinders parallel processing of files and incremental indexing. — [Source](https://github.com/sourcegraph/scip/blob/main/docs/DESIGN.md)
- SCIP payloads are typically 4x smaller when gzipped and 5x smaller uncompressed compared to LSIF. — [Source](https://sourcegraph.com/blog/announcing-scip)
- Sourcegraph has fully deprecated LSIF support in favor of SCIP due to performance bottlenecks and difficulty in implementing incremental indexing. — [Source](https://github.com/scip-code/scip/blob/main/docs/DESIGN.md)

### Inferences
- For "Codebase Intelligence," which uses SQLite, SCIP's document-centric structure is a better fit for row-based storage than LSIF's graph of vertices and edges.
- SCIP's design allows for per-file indexing in parallel, which is critical for large monorepos.

### Gaps
- Exact memory usage comparisons for specific large Python codebases were not found in the protocol specs.

## How accurate is PyCG's call graph extraction for complex Python codebases compared to static analysis?

### Takeaway
PyCG provides state-of-the-art static call-graph generation for Python with ~94% precision, though it deliberately trades off completeness for dynamic constructs to maintain scalability.

### Cited Findings
- PyCG achieves 94.5% precision and 87.8% recall on real-world packages, outperforming prior tools like `pyan3` and `JARVIS`. — [Source](https://github.com/vitsalis/pycg-evaluation)
- Against execution traces (DyPyBench), PyCG reached 90.4% recall for inside-package edges. — [Source](https://github.com/vitsalis/pycg-evaluation)
- The tool misses edges created by `eval`, `getattr`, `setattr`, and some built-in methods (e.g., `list.append`) because it does not model the full Python runtime. — [Source](https://arxiv.org/abs/2103.00587)
- PyCG ignores conditionals and loops to remain efficient, over-approximating by considering all branches. — [Source](https://arxiv.org/abs/2103.00587)

### Inferences
- PyCG is highly reliable for standard function/method calls and class hierarchies but will have "known-blind-spots" in highly dynamic frameworks (e.g., Django's signal routing or heavy use of `getattr`).
- Since "Codebase Intelligence" uses Python AST, PyCG's logic could be integrated to improve call-graph accuracy over basic AST walking.

### Gaps
- Accuracy metrics for the "2026 redesign" are based on the latest evaluation repo, but specific performance on Python 3.13+ features (like PEP 695 generics) is still being benchmarked.

## How well do these protocols handle cross-repository relationships?

### Takeaway
SCIP provides a robust, URI-like naming convention for symbols that enables seamless cross-repository navigation, whereas LSIF relied on a more complex "moniker" system that was prone to state-sync issues.

### Cited Findings
- SCIP symbol IDs are globally unique, following the pattern: `<scheme> <manager> <package-name> <version> <descriptors>`. — [Source](https://github.com/scip-code/scip/blob/main/docs/scip.md)
- Cross-repository navigation works by resolving a reference's unique symbol ID to the repository that "exports" that specific package version. — [Source](https://sourcegraph.com/blog/cross-repository-code-navigation)
- scip-clang and other indexers use a "package map" to identify which source paths belong to which external packages and versions. — [Source](https://github.com/sourcegraph/scip-clang/blob/main/docs/CrossRepo.md)
- LSIF's "monikers" (import/export) were intended for this but were difficult to implement correctly across different build systems. — [Source](https://sourcegraph.com/blog/announcing-scip)

### Inferences
- Implementing SCIP would allow "Codebase Intelligence" to link different projects in its `index.db` simply by matching symbol strings, provided they follow the SCIP grammar.

### Gaps
- Performance overhead of large "package maps" in monorepos with thousands of dependencies was not explicitly quantified.

## Technology Adoption Rubric

| Rubric Item | SCIP (Sourcegraph) | LSIF (Language Server Index) | PyCG (Python Call Graph) |
| :--- | :--- | :--- | :--- |
| **1. Offer** | Protobuf-based precise index format | JSON-based graph index format | Static call-graph generator |
| **2. Problem** | Precise nav at scale; dev speed | Precise nav standardization | Call graphs without execution |
| **3. Vs Custom AST** | A result format for AST analysis | Complex graph output for AST | An analyzer *using* AST |
| **4. Accuracy/Perf** | High (streaming, 5x smaller) | Low (global state, slow JSON) | High (94% precision) |
| **5. Limitations** | Transmission only, no query API | Opaque IDs, hard to debug | Misses dynamic `eval`/`getattr` |
| **6. Maintenance** | Active (Sourcegraph) | Deprecated (by Sourcegraph) | Active (Redesigned 2026) |
| **7. License** | Apache 2.0 | MIT / CC | Apache 2.0 |
| **8. Rubric Status** | **Adopt** (for export/transmission) | **Avoid** (legacy only) | **Partial** (for Python call graphs) |
