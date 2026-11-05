import { useState } from "react";

type Props = {
  onAnalyze: (target: { git_url?: string; path?: string }) => Promise<void>;
  busy: boolean;
  error: string | null;
};

const GITHUB = /^https?:\/\/(www\.)?github\.com\/[\w.-]+\/[\w.-]+\/?(\.git)?$/i;
const LOCAL = /^(\/|~\/|[A-Za-z]:\\)/;

export function IngestPanel({ onAnalyze, busy, error }: Props) {
  const [target, setTarget] = useState("");
  const value = target.trim();
  const isGit = GITHUB.test(value);
  const isPath = LOCAL.test(value);
  const valid = isGit || isPath;

  return (
    <div className="ingest-panel">
      <div className="ingest-icon">⎇</div>
      <h2>Connect a repository</h2>
      <p className="muted">
        Paste a public GitHub URL or an absolute local path. The analyzers detect Python (Django, FastAPI, Flask,
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
        {error ? <p className="form-error">{error}</p> : null}
        <button type="submit" className="btn primary wide" disabled={!valid || busy}>
          {busy ? "Indexing repository…" : isPath ? "Analyze local project" : "Analyze repository"}
        </button>
      </form>
      <p className="ingest-hint muted">
        Or from a terminal: <code>ci analyze .</code> · AI agents: <code>ci mcp</code>
      </p>
    </div>
  );
}
