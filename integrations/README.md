# Editor and agent integrations

Install Codebase Intelligence into Claude Code or Cursor so any project can generate its codebase map (architecture, API flows, jobs, ER diagram, suggestions) as Markdown + Mermaid inside the repo.

Prerequisite: clone this repository and run `cd backend && uv sync --all-packages`. `uv` must be on your `PATH`.

## Claude Code (plugin)

```bash
export CI_HOME=/absolute/path/to/codebase-intelligence   # add to your shell profile
claude plugin marketplace add /absolute/path/to/codebase-intelligence
claude plugin install codebase-intel@codebase-intelligence
```

Inside any repository, ask "generate the codebase map" (the `codebase-map` skill), or call the MCP tools directly: `generate_docs`, `list_jobs`, `suggest_optimizations`, `trace_endpoint`, `list_models`.

The plugin's MCP server runs `uv run --project $CI_HOME/backend ci mcp`. It keeps your repository as the working directory, so that repository is the default project and is indexed on first use.

## Cursor

1. Copy [cursor/mcp.json](cursor/mcp.json) to `.cursor/mcp.json` in your project (or `~/.cursor/mcp.json` for all projects) and replace the path.
2. Copy [cursor/rules/codebase-map.mdc](cursor/rules/codebase-map.mdc) to `.cursor/rules/`.
3. Ask the agent to "generate the codebase map".

## Without an agent

```bash
cd /path/to/your/repo
uv run --project "$CI_HOME/backend" ci analyze .
uv run --project "$CI_HOME/backend" ci docs          # writes docs/codebase-map/
```
