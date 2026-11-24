# Editor and agent integrations

Install Codebase Intelligence into Claude Code or Cursor so any project can generate its codebase map (architecture, API flows, jobs, ER diagram, suggestions) as Markdown + Mermaid inside the repo.

**Quick install:** `bash integrations/install.sh` from a checkout (or run it standalone with `CI_REPO_URL` set; it clones into `~/.codebase-intelligence-src`). It runs `uv sync`, builds the dashboard if `npm` exists, and prints the steps below.

Manual prerequisite: clone this repository and run `cd backend && uv sync --all-packages`. `uv` must be on your `PATH`.

## Claude Code (plugin)

```bash
export CI_HOME=/absolute/path/to/codebase-intelligence   # add to your shell profile
claude plugin marketplace add /absolute/path/to/codebase-intelligence
claude plugin install codebase-intel@codebase-intelligence
```

Inside any repository, ask "generate the codebase map" (the `codebase-map` skill), or call the MCP tools directly: `build_context` (one-call context pack before editing), `find_references`, `generate_docs`, `list_jobs`, `suggest_optimizations`, `trace_endpoint`, `list_models`.

The plugin's MCP server runs `uv run --project $CI_HOME/backend ci mcp`. It keeps your repository as the working directory, so that repository is the default project and is indexed on first use.

## Cursor

1. Copy [cursor/mcp.json](cursor/mcp.json) to `.cursor/mcp.json` in your project (or `~/.cursor/mcp.json` for all projects) and replace the path.
2. Copy [cursor/rules/codebase-map.mdc](cursor/rules/codebase-map.mdc) to `.cursor/rules/`.
3. Ask the agent to "generate the codebase map".

## GitHub Action (impact gate) — experimental

[github-action/action.yml](github-action/action.yml) is a **sketch**, not a published or consumer-ready Action.

| Aspect | Current state |
| --- | --- |
| **Status** | Experimental; for maintainers validating the idea inside this monorepo only. |
| **Layout assumption** | Steps use `${{ github.action_path }}/../../backend` so `uv sync` and `uv run ci` run from the **Codebase Intelligence** repository checkout (same layout as this tree). |
| **Analyze target** | `ci analyze .` uses `${{ github.workspace }}`, which is correct when the workflow runs in **this** repo; it is wrong if you only vendor the action YAML into another repository without also checking out CI’s `backend/`. |
| **Before external use** | Package or pin the CLI (`uv tool install` / container), set `working-directory` to the consumer repo, pass `CI_DATA_DIR`, document `CI_GITHUB_TOKEN` for private clones, and replace monorepo-relative paths with an explicit `CI_HOME` or composite `inputs.ci_repo_path`. |

Intended behavior once wired correctly: shallow index the workspace, then `ci impact --base origin/main --fail-on high`. Do not reference this action from third-party repos until the above packaging work is done.

## Without an agent

```bash
cd /path/to/your/repo
uv run --project "$CI_HOME/backend" ci analyze .
uv run --project "$CI_HOME/backend" ci docs          # writes docs/codebase-map/
uv run --project "$CI_HOME/backend" ci hook install  # re-index after each commit (background)
```
