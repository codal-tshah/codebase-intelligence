# Joern and Code Property Graphs (CPG)

## How does the Code Property Graph (CPG) unify AST, CFG, and PDG for static extraction?

### Takeaway
The CPG unifies representations by using **statement and predicate nodes** as shared anchors: while the AST provides the hierarchical skeleton, the CFG and PDG add directed edges between these same nodes to represent execution order and dependencies respectively.

### Cited Findings
- The CPG is defined as a directed, edge-labeled, attributed multigraph where $G = (V, E, \lambda, \mu)$ is the union of AST, CFG, and PDG graphs. — [Fabian Yamaguchi, S&P 2014](https://fabianyamaguchi.com/files/2014-ieeesp.pdf)
- Unification occurs because "in each of the three graphs, a node exists for each statement and predicate in the source code." The AST is the only one that introduces additional non-statement nodes. — [Fabian Yamaguchi, S&P 2014](https://fabianyamaguchi.com/files/2014-ieeesp.pdf)
- CPG edges include `AST` (syntactic), `CFG` (control flow), and `PDG` which is the union of `CDG` (control dependency) and `REACHING_DEF` (data dependency/DDG). — [MegaVul Specification](https://github.com/Icyrockton/MegaVul/blob/main/SPECIFICATION.md)
- Modern Joern implementations use an extensible base schema (defined in `cpg.proto`) that allows language-agnostic traversals across these layers using a Scala-based DSL. — [Joern Documentation](https://docs.joern.io/code-property-graph/)

### Inferences
- The unification allows for "semantic" queries (e.g., "find all calls to `malloc` where the size argument is influenced by a user-controlled variable") that are difficult to perform on raw ASTs alone.
- Because statement nodes are shared, one can jump from a syntax tree location to its corresponding data-flow dependencies without a manual lookup table.

### Gaps
- The exact precision of the Python-specific data-flow implementation (e.g., handling of dynamic attributes vs. static analysis) is noted as "fuzzy" in some docs, but specific precision metrics for Python 3.12+ features were not found.

---

## What are the performance overheads of Joern's graph generation for multi-million line repos?

### Takeaway
Joern can handle 100M+ nodes but requires **substantial RAM (30GB to 128GB)** and tens of minutes for import on multi-million line codebases like the Linux kernel.

### Cited Findings
- Importing Linux 4.1.16 (48M nodes, 431M edges) takes approximately **11 minutes** using the `flatgraph` backend with a **30GB heap** minimum; the older `OverflowDB` backend required **80GB heap** and 18 minutes. — [Joern 4.0.0 Changelog](https://github.com/joernio/joern/blob/master/changelog/4.0.0-flatgraph.md)
- For a 100M+ node corpus (Firefox, Chromium, Kernels), Joern can iterate over all nodes in ~16 seconds once imported, but initial generation is the bottleneck. — [ShiftLeft Blog](https://blog.shiftleft.io/querying-detailed-whole-program-representations-with-100-mil-loc-on-commodity-hardware-ffbf2d50ee70)
- The `wireshark` codebase took roughly **6 hours** to process on a machine with **128GB RAM**, after failing on smaller machines. — [Alessandro Mantovani Research](https://elmanto.github.io/posts/sast_derby_joern_vs_codeql)
- Python-specific parsing via `pysrc2cpg` is significantly slower than native CPython `ast` or `tree-sitter` (roughly 1.9x to 6.7x slower end-to-end) because it involves CPG construction and type recovery passes. — [Sugar Compiler Benchmarks](https://github.com/TSavo/sugar/issues/5954)

### Inferences
- The high memory overhead makes Joern unsuitable for "instant" or "lightweight" indexing on consumer-grade hardware for very large projects.
- The `flatgraph` transition (columnar layout) significantly improved memory efficiency (40% reduction) but didn't eliminate the JVM/RAM bottleneck.

### Gaps
- No specific "time per 1k LOC" metric was found for the Python frontend specifically, only whole-project metrics for C/Java.

---

## Can Joern be used without its GPL/restrictive components?

### Takeaway
Yes. The core Joern platform, frontends, and CPG specification are licensed under **Apache 2.0**, which allows for non-GPL in-process embedding and commercial use without copyleft requirements.

### Cited Findings
- Joern and its core components (CLI, `semanticcpg`, frontends like `pysrc2cpg`) are explicitly licensed under **Apache License 2.0**. — [Joern LICENSE](https://github.com/joernio/joern/blob/master/LICENSE)
- The Code Property Graph specification is open-sourced as a suggested standard and includes a `cpg.proto` for generating language bindings in Python, C++, etc. — [ShiftLeft CPG Repo](https://github.com/ShiftLeftSecurity/codepropertygraph/)
- Apache 2.0 is compatible with GPLv3 (combined work becomes GPLv3) but allows for proprietary or non-GPL embedding if the conditions (notice/attribution) are met. — [Apache Foundation](https://www.apache.org/licenses/GPL-compatibility.html)
- While some frontends historically downloaded external binaries (e.g., `goastgen`), the project has moved toward internal forks (e.g., `joernio/goastgen`) to maintain independence. — [Joern Issue #4931](https://github.com/joernio/joern/issues/4931)

### Inferences
- Embedding Joern in a Python application can be done via the `cpgqls-client` (RPC to a Joern server) or by loading CPG exports (CSV/JSON) into a Python graph library like `cpg2py`, avoiding JVM in-process overhead.
- There are no "hidden" GPL traps in the main repository, though specific third-party parsers invoked by frontends should be audited individually.

### Gaps
- The "Ocular" commercial version's proprietary extensions were not analyzed, but they do not affect the open-source Apache 2.0 core.

---

## 8 Adoption Rubric Items for Codebase Intelligence

| Rubric Item | Evaluation |
| :--- | :--- |
| **1. Offer** | A language-agnostic, multi-layered property graph unifying AST, CFG, and PDG. |
| **2. Problem** | Solves the "fragmented analysis" problem by providing a single queryable model for syntax, control, and data flow. |
| **3. Vs Custom AST** | Significantly more semantic depth (data flow) but 2x-5x slower to parse and 10x-100x more memory intensive than raw `cpython-ast`. |
| **4. Accuracy/Perf** | High accuracy for vulnerability mining; performance is batch-oriented, not real-time. High RAM requirement. |
| **5. Limitations** | JVM dependency, heavy memory footprint, "fuzzy" parsing approach may lose strict syntactic fidelity compared to tree-sitter. |
| **6. Maintenance** | High. Very active community and commercial backing by Qwiet AI. |
| **7. License** | **Apache 2.0** (Permissive). Safe for non-GPL in-process embedding or linking. |
| **8. Adopt/Partial/Retain** | **Partial / Deep Analysis Only**. Retain tree-sitter/SQLite for fast indexing; offer Joern as an optional backend for deep data-flow/security queries. |
