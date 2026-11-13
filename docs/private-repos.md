# Private GitHub repositories

`ci analyze <url>`, `POST /projects/analyze {"git_url": …}` and the dashboard's *Connect a repository* form clone over HTTPS. Public repos need nothing. A private repo needs a GitHub token on the machine that runs the clone (the CLI, or the API server).

## Setup

1. Create a **fine-grained personal access token** on GitHub: Settings → Developer settings → Fine-grained tokens.
   - **Resource owner:** the organisation that owns the repos (for example `codal`). The org may need to approve the token.
   - **Repository access:** only the repos you want to index.
   - **Permissions:** *Contents: Read-only* (Metadata: Read-only is added automatically). Nothing else.
   - A classic token with the `repo` scope also works, but grants far more than needed.
2. Put it in the environment of the process that clones, never in git:
   ```bash
   # backend/.env or your shell profile (both are git-ignored / local)
   export CI_GITHUB_TOKEN=github_pat_...
   ```
   `GITHUB_TOKEN` is used as a fallback, so CI runners and `gh`-style setups work unchanged.
3. Restart the API (`ci serve` doesn't reload settings), then index:
   ```bash
   uv run ci analyze https://github.com/<org>/<repo>
   # or paste the URL into the dashboard
   ```

## How the token is handled

- It is sent as an HTTP `Authorization` header to `github.com` for that one `git` process only, via `GIT_CONFIG_*` environment variables (`ci_parsers.files._git_auth_env`).
- It is **not** in the command line (`ps`), the remote URL, the clone's `.git/config`, logs, API responses or error messages. `Settings.github_token` is excluded from `repr`.
- `GIT_TERMINAL_PROMPT=0`, so a missing or wrong token fails immediately instead of hanging.
- Clones live in `$CI_DATA_DIR/sources/<repo>` (default `~/.codebase-intelligence/sources`). Re-indexing the same URL runs `git pull --ff-only` with the same token.

## Errors

| Response | Meaning | Fix |
|---|---|---|
| `400 git clone failed: … not found. If the repository is private, set CI_GITHUB_TOKEN` | No token, or the token can't see the repo | Set the token; check repo access and org approval |
| `400 git clone failed: … Authentication failed` | Expired or revoked token | Regenerate it |
| `403 git_url ingest is disabled in server mode` | `CI_MODE=server` | Clone yourself under `CI_PROJECT_ROOTS` and index by `path` |

## Alternative: clone yourself

If you already have SSH or `gh` access, cloning yourself avoids giving the tool a token at all:

```bash
gh repo clone <org>/<repo> ~/src/<repo>
uv run ci analyze ~/src/<repo>
```

## Limitations

- GitHub over HTTPS only. GitHub Enterprise, GitLab, Bitbucket and SSH URLs are rejected by the URL validator.
- One token per server process. There's no per-user or per-project token, so everyone using that server can index anything the token can read. Don't set it on a shared server you wouldn't trust with those repos.
- Shallow clone of the default branch only; no branch or tag selection.
- The dashboard can't enter a token. That's deliberate: tokens stay in server configuration.
