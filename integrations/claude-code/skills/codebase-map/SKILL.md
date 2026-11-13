---
name: codebase-map
description: Generate or refresh visual docs for this repository (architecture, API endpoint flows, background/scheduled jobs, ER diagram, optimization suggestions) as Markdown + Mermaid under docs/codebase-map, or answer "how does X flow / who writes table Y / what runs on a schedule" from the code graph. Use when asked to map, diagram, visualize or document the codebase, its endpoints, jobs or database.
---

# Codebase map

Uses the `codebase-intel` MCP server (Codebase Intelligence). The server indexes the current repository on first use.

## Generate the docs

1. If code changed since the last run, call `index_project` with the repository path (incremental is the default).
2. Call `generate_docs` (default `output_dir`: `docs/codebase-map`). It writes:
   - `README.md`: index and graph stats
   - `architecture.md`: packages and dependencies
   - `api-flows.md`: one flowchart per endpoint, route → handler → services → models, plus UI callers; each node shows its summary as helper text
   - `jobs.md`: background tasks, cron/interval jobs and management commands, their schedules and the models they write
   - `data-model.md`: Mermaid `erDiagram` plus who reads and writes each model
   - `suggestions.md`: optimization and reuse leads
3. Tell the user which files were written. Mermaid renders on GitHub, GitLab, VS Code and Cursor. For the interactive version, run `ci serve --ui` from the Codebase Intelligence checkout.

## Answer questions instead

- Endpoint behaviour: `trace_endpoint` (route, optional method).
- Jobs and who writes to the DB outside requests: `list_jobs`.
- Tables, fields and relations: `list_models`.
- Refactoring and reuse ideas: `suggest_optimizations`. Present these as leads to check, not facts: static analysis can miss dynamic calls.
- Quote code with `read_source` using the file:line from results.

Don't edit the generated files by hand; regenerate them.
