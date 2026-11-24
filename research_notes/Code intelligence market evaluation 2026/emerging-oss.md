# Emerging OSS Code Intelligence and Architecture Projects (2024-2026)

## Market Evaluation: Code Intelligence & Architecture Mapping

### Takeaway
The 2024-2026 landscape is dominated by local-first, graph-based indexing tools that bridge static analysis (Tree-sitter/SCIP) with the Model Context Protocol (MCP) to provide AI agents with structural codebase context.

### Cited Findings
- **GitNexus (abhigyanpatwari/GitNexus)**: A "zero-server" code intelligence engine that indexes codebases into a knowledge graph of symbols, calls, and execution flows. It features a web graph explorer, CLI, and MCP tools like `impact` and `trace`. — [Source](https://github.com/abhigyanpatwari/GitNexus/)
- **CodeGraphContext (CodeGraphContext/CodeGraphContext)**: A powerful MCP server and CLI toolkit that indexes local code into a graph database (supporting FalkorDB, KuzuDB, etc.) using Tree-sitter and SCIP. It enables AI assistants to trace call chains and understand class hierarchies across files. — [Source](https://github.com/CodeGraphContext/CodeGraphContext)
- **sqry (verivus-oss/sqry)**: A local Rust-based semantic code search tool with 37 language plugins. It builds AST-backed symbol and relationship graphs, offering a declarative rule layer for executing custom TOML rule packs against the graph. — [Source](https://github.com/verivus-oss/sqry)
- **Synaptic (Synaptic-Graph/Synaptic)**: Auditable code intelligence for AI agents that maps dependencies, predicts change impact, and verifies refactors. It includes source-linked history from commits and decisions to plan reviewable repairs. — [Source](https://github.com/Synaptic-Graph/Synaptic)
- **Telos (stroland02/telos)**: A visual-first architecture sentinel that renders a semantic-zoom map (layers → modules → files → symbols). It integrates live OpenTelemetry overlays (traces/metrics) and an MCP layer for agent queries. — [Source](https://github.com/stroland02/telos)
- **ArchiLens (saurabh-oss/archilens)**: Focused on architecture governance, it generates layered diagrams and checks architecture-rule compliance in CI. It provides an architecture diff and optional AI review for every pull request. — [Source](https://github.com/saurabh-oss/archilens)
- **codebase-index (denfry/codebase-index)**: A ranking-focused indexer that provides "evidence-bearing answers" to an agent's questions. It uses reciprocal-rank fusion across multiple retrievers (symbol, path, FTS) to emit ranked code ranges with a read plan. — [Source](https://github.com/denfry/codebase-index)
- **GitHub MCP Server (github/github-mcp-server)**: The official GitHub implementation for the Model Context Protocol, providing agents with structured access to repositories, issues, pull requests, and GitHub Code Search. — [Source](https://github.com/github/github-mcp-server)

### Inferences
- The shift from vector-only search to **graph-augmented retrieval (GraphRAG)** is standard for code intelligence in 2026.
- **Local-first** is the dominant architectural pattern for security-conscious codebase indexing, with tools like sqry and Synaptic emphasizing zero-server Rust binaries.
- **Architecture governance** (ArchiLens, Telos) is moving from static documentation to live, CI-integrated verification.

### Gaps
- Long-term scalability benchmarks for local graph databases (LadybugDB, FalkorDB Lite) on multi-million line codebases are still emerging.

---

## Project Evaluation Table

| Project | Description | License | Signal (Stars/Status) | Recommendation (for Local Indexer) |
| :--- | :--- | :--- | :--- | :--- |
| **GitNexus** | Zero-server engine for symbols, calls, and execution flows with MCP and Web UI. | PolyForm Noncommercial 1.0.0 | 48.7k stars; high adoption; active. | **Integrate** as a visualization benchmark; note license restrictions. |
| **CodeGraphContext** | MCP/CLI graph indexer using Tree-sitter/SCIP with pluggable graph backends. | MIT | 4.4k stars; active maintainer; stable v2+. | **Adopt** the pluggable backend architecture for SQLite/KuzuDB flexibility. |
| **sqry** | Rust-based semantic search with 37 languages and a declarative TOML rule engine. | MIT | 27 stars; early-stage; high feature density. | **Integrate** the rule engine logic for custom architecture checks. |
| **Synaptic** | Audit-focused intelligence for change forecasting and test selection. | AGPL-3.0 | 32 stars; stable releases; Rust binary. | **Ignore** for core due to AGPL, but study its isolated worktree verification. |
| **Telos** | Semantic-zoom map with live OpenTelemetry overlays and agent memory. | MIT | 5 stars; innovative; visual-first. | **Adopt** the "semantic-zoom" UI pattern for large codebase exploration. |
| **ArchiLens** | CI-integrated architecture diagrams and fan-out/layer rule enforcement. | MIT | 2 stars; focused on PR workflows. | **Integrate** the PR architecture-diff logic into the indexing pipeline. |
| **codebase-index** | Evidence-bearing retrieval using ranking fusion and uncertainty reporting. | MIT | 13 stars; active; emphasis on "graph honesty." | **Adopt** the ranked read-plan and uncertainty reporting mechanism. |
| **GitHub MCP Server** | Official MCP server for GitHub repo metadata, issues, PRs, and code search. | MIT | 34.5k stars; canonical; high maintenance. | **Integrate** for fetching out-of-band context (PRs/Issues) for the graph. |
