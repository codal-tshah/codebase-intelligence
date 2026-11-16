import { useEffect, useState } from "react";
import { Check, GitBranch } from "lucide-react";
import { getJson } from "../api";

type Props = {
  onAnalyze: (target: { git_url?: string; path?: string }) => Promise<void>;
  busy: boolean;
  error: string | null;
};

const GITHUB = /^https?:\/\/(www\.)?github\.com\/[\w.-]+\/[\w.-]+\/?(\.git)?$/i;
const LOCAL = /^(\/|~\/|[A-Za-z]:\\)/;

type Access = { ok: boolean; reason?: string; default_branch?: string | null; needs_token?: boolean; token_configured?: boolean };

/** Debounced preflight: can the server read this GitHub repo (with CI_GITHUB_TOKEN if set)? */
function useGitAccess(url: string | null): Access | "checking" | null {
  const [state, setState] = useState<Access | "checking" | null>(null);
  useEffect(() => {
    if (!url) {
      setState(null);
      return;
    }
    let live = true;
    setState("checking");
    const t = setTimeout(() => {
      getJson<Access>(`/git/check?url=${encodeURIComponent(url)}`)
        .then((r) => live && setState(r))
        .catch((e: Error) => live && setState({ ok: false, reason: e.message }));
    }, 500);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [url]);
  return state;
}

export function IngestPanel({ onAnalyze, busy, error }: Props) {
  const [target, setTarget] = useState("");
  const value = target.trim();
  const isGit = GITHUB.test(value);
  const isPath = LOCAL.test(value);
  const valid = isGit || isPath;
  const access = useGitAccess(isGit ? value : null);
  const blocked = isGit && access !== null && access !== "checking" && !access.ok;

  return (
    <div className="ingest-panel">
      <div className="ingest-icon" aria-hidden>
        <GitBranch size={20} strokeWidth={1.5} />
      </div>
      <h2>Connect a repository</h2>
      <p className="muted">
        Paste a GitHub URL or an absolute local path. Private repositories need <code>CI_GITHUB_TOKEN</code> set
        on the server (or clone locally and use the path). The analyzers detect Python (Django, FastAPI, Flask,
        SQLAlchemy) and TypeScript/JavaScript (React, Next.js, Express, NestJS) automatically, link frontend calls to
        backend routes, and build an explorable graph. Nothing leaves your machine unless you enable an LLM.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (valid && !busy) void onAnalyze(isGit ? { git_url: value } : { path: value });
        }}
      >
        <label className="field">
          <span>GitHub URL or local path</span>
          <input
            placeholder="https://github.com/owner/repository  or  /Users/me/src/my-app"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            disabled={busy}
            autoFocus
          />
        </label>
        {value && !valid ? <p className="form-error">Enter a github.com repository URL or an absolute path.</p> : null}
        {isGit && access === "checking" ? <p className="muted ingest-access">Checking access…</p> : null}
        {isGit && access && access !== "checking" ? (
          access.ok ? (
            <p className="muted ingest-access">
              <Check size={12} strokeWidth={1.5} aria-hidden /> Reachable{access.default_branch ? ` · default branch ${access.default_branch}` : ""}
              {access.token_configured ? " · using server token" : ""}
            </p>
          ) : (
            <p className="form-error">
              {access.reason}
              {access.needs_token ? " (see docs/private-repos.md)" : ""}
            </p>
          )
        ) : null}
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        <button type="submit" className="btn primary wide" disabled={!valid || busy || blocked}>
          {busy ? "Indexing repository…" : isPath ? "Analyze local project" : "Analyze repository"}
        </button>
      </form>
      <p className="ingest-hint muted">
        Or from a terminal: <code>ci analyze .</code> · AI agents: <code>ci mcp</code>
      </p>
    </div>
  );
}
