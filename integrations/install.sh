#!/usr/bin/env bash
# Install Codebase Intelligence (CLI, API, MCP server) and print the editor setup.
#
#   bash integrations/install.sh                 # from a checkout: installs that checkout
#   CI_REPO_URL=... bash install.sh              # standalone: clones into $CI_HOME first
#
# Env: CI_HOME (default ~/.codebase-intelligence-src), CI_REPO_URL, CI_SKIP_UI=1 (skip the dashboard build).
# Needs git and uv (https://docs.astral.sh/uv/); npm only for the dashboard. No secrets are read or written.
set -euo pipefail

REPO_URL="${CI_REPO_URL:-https://github.com/codal-tshah/codebase-intelligence.git}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$here/../backend/pyproject.toml" ]; then
  CI_HOME="$(cd "$here/.." && pwd)"
else
  CI_HOME="${CI_HOME:-$HOME/.codebase-intelligence-src}"
  if [ -d "$CI_HOME/.git" ]; then
    git -C "$CI_HOME" pull --ff-only
  else
    git clone --depth 1 "$REPO_URL" "$CI_HOME"
  fi
fi

command -v uv >/dev/null 2>&1 || { echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/" >&2; exit 1; }
(cd "$CI_HOME/backend" && uv sync --all-packages)

if [ "${CI_SKIP_UI:-0}" != "1" ] && command -v npm >/dev/null 2>&1; then
  (cd "$CI_HOME/frontend" && npm install --silent && npm run build --silent)
fi

cat <<EOF

Installed in $CI_HOME

1. Add to your shell profile:
     export CI_HOME="$CI_HOME"
     alias ci='uv run --project "\$CI_HOME/backend" ci'

2. Claude Code:
     claude plugin marketplace add "$CI_HOME"
     claude plugin install codebase-intel@codebase-intelligence

   Cursor: copy $CI_HOME/integrations/cursor/mcp.json to .cursor/mcp.json (set the path)
           and $CI_HOME/integrations/cursor/rules/codebase-map.mdc to .cursor/rules/

3. In a repository:
     ci analyze .            # index
     ci hook install         # keep it fresh after each commit
     ci docs                 # write docs/codebase-map/
     ci serve --ui "\$CI_HOME/frontend/dist"   # dashboard on http://127.0.0.1:8000

Private GitHub repos: export CI_GITHUB_TOKEN=... (see $CI_HOME/docs/private-repos.md)
EOF
