# Research: tree-sitter, ast-grep, and Semgrep for Static Extraction

## Rubric: tree-sitter

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
- **Recommendation**: **Retain**. It is the industry standard for the "parsing" stage of codebase intelligence.

### Inferences
- For codebase intelligence, Tree-sitter's incremental parsing is a key differentiator for IDE-like responsiveness, as it avoids full-file reparsing on every keystroke.
- The lack of semantic depth means a secondary layer (like a symbol resolver or data-flow engine) is always required.

### Gaps
- Specific benchmarks for Python-specific incremental parsing in the `backend` context of this project were not found; general benchmarks are used as a proxy.

## Rubric: ast-grep

### Takeaway
ast-grep provides an ergonomic, high-level pattern matching layer on top of Tree-sitter, significantly simplifying the extraction of syntactic relationships without the complexity of manual AST walking.

### Cited Findings
- **Offer**: A CLI tool and Rust library for structural code search and rewriting using Tree-sitter ASTs — [ast-grep GitHub](https://github.com/ast-grep/ast-grep).
- **Problem**: Replaces complex, brittle AST walker code with intuitive S-expressions or code-like patterns (metavariables) — [Official Docs](https://ast-grep.github.io/advanced/how-ast-grep-works).
- **Vs Custom AST**: Much faster to implement relationship extraction rules; patterns like `import { $A } from '$B'` are easier to write and maintain than manual node traversal — [Tool Comparison](https://ast-grep.github.io/advanced/tool-comparison).
- **Accuracy/Perf**: Highly performant due to Rust implementation and multi-threaded processing using `ignore` for file walking — [Comparison With Other Frameworks](https://ast-grep.github.io/advanced/tool-comparison).
- **Limitations**: Syntactic only; cannot resolve types or follow data flow across files — [Fluid Attacks Docs](https://docs.fluidattacks.com/stack/dependencies/tree-sitter).
- **Maintenance**: Active, but has high maintainer concentration (Herrington Darkholme); lacks corporate backing but has community support — [DiscoverGit Analysis](https://discovergit.app/repo/ast-grep/ast-grep).
- **License**: MIT License; safe for proprietary use — [LICENSE](https://github.com/ast-grep/ast-grep/blob/main/LICENSE).
- **Recommendation**: **Adopt (Partial)**. Excellent for replacing boilerplate AST walkers for symbol and basic relationship (e.g., calls, imports) extraction.

### Inferences
- ast-grep can serve as a "query engine" for the graph builder, allowing developers to define extraction logic in declarative YAML/S-expressions rather than imperative Python/Rust walkers.

### Gaps
- Long-term maintenance stability is a risk compared to Tree-sitter or Semgrep due to the lack of corporate backing.

## Rubric: Semgrep

### Takeaway
Semgrep is a powerful semantic analysis engine that bridges the gap between syntactic patterns and deep static analysis (taint, data flow), but it carries higher licensing complexity and performance overhead.

### Cited Findings
- **Offer**: A static analysis engine that matches code patterns while performing constant propagation, taint analysis, and data-flow tracking — [Semgrep Official](https://semgrep.dev/).
- **Problem**: Solves complex semantic discovery tasks (e.g., "find all user-input flowing to this specific database call") that purely syntactic tools miss — [Semgrep Docs](https://docs.semgrep.dev/faq/comparisons/opengrep).
- **Vs Custom AST**: Provides high-level semantic primitives (taint, flow) that are extremely difficult to build correctly in a custom walker — [Semgrep vs Opengrep](https://docs.semgrep.dev/faq/comparisons/opengrep).
- **Accuracy/Perf**: Slower than Tree-sitter/ast-grep for simple searches but offers much higher precision for semantic relationships; engine is optimized with OCaml 5 multicore — [Semgrep Pro vs OSS](https://docs.semgrep.dev/semgrep-pro-vs-oss).
- **Limitations**: The community registry rules have restrictive licensing; the engine itself is relatively heavyweight compared to raw Tree-sitter — [Licensing](https://docs.semgrep.dev/licensing).
- **Maintenance**: Very high; backed by Semgrep, Inc. with significant venture funding — [About Semgrep](https://semgrep.dev/about/).
- **License**: Engine is LGPL-2.1; Rules Registry is "Semgrep Rules License v1.0" (Internal use OK, but cannot be bundled in competing commercial products) — [Licensing Page](https://docs.semgrep.dev/licensing).
- **Recommendation**: **Adopt (Specific)**. Use for deep semantic extraction (e.g., taint flow for security or dependency reachability) where syntactic patterns are insufficient.

### Inferences
- Semgrep is the best choice for "Level 2" intelligence (data flow, taint) but is likely too slow and complex for "Level 1" (basic symbol extraction).
- Licensing risks are manageable if the tool is used as an internal engine and registry rules are not redistributed as a product feature.

### Gaps
- The exact performance delta for large-scale repo indexing (e.g., 1M+ LOC) vs. ast-grep was not found in a direct head-to-head benchmark.

## Key Question: tree-sitter's incremental parsing and speed
Tree-sitter's incremental parsing significantly improves extraction speed during **iterative analysis** (e.g., an IDE plugin or incremental build system). By retaining the previous AST and only re-parsing changed subtrees, it reduces re-parse times from linear (proportional to file size) to logarithmic or constant for most edits. For **batch indexing**, the benefit is smaller, but the balanced binary tree structures used for repeats still provide efficient traversal compared to flat arrays in traditional parsers — [Source A](https://muhammad-fiaz.github.io/tree-sitter.zig/guide/performance.html); [Source B](https://github.com/tree-sitter/tree-sitter/issues/995).

## Key Question: ast-grep or Semgrep vs traditional AST walkers
Both tools can effectively replace traditional manual AST walkers by providing a **declarative DSL** for extraction. ast-grep is superior for **syntactic relationships** (e.g., identifying all `class` definitions or `import` statements) due to its speed and simplicity. Semgrep is superior for **semantic relationships** (e.g., finding call sites where an argument originates from a specific config file) by automating the data-flow and taint tracking that would otherwise require thousands of lines of manual walker code — [Source A](https://ast-grep.github.io/advanced/tool-comparison); [Source B](https://docs.semgrep.dev/semgrep-pro-vs-oss).

## Key Question: Licensing risks in proprietary backend
- **tree-sitter**: **Low risk**. MIT license allows embedding in any commercial or proprietary backend.
- **ast-grep**: **Low risk**. MIT license allows proprietary use and distribution.
- **Semgrep**: **Moderate risk**. The engine is LGPL-2.1 (safe for internal use/calling as a process, but requires care if linking). The primary risk is the **Semgrep Rules License v1.0** for the registry; a proprietary product *cannot* bundle Semgrep's managed rules to provide a competing "code intelligence" or security product without a commercial partnership — [Source A](https://docs.semgrep.dev/licensing); [Source B](https://docs.semgrep.dev/faq/comparisons/opengrep).
