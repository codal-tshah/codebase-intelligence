import { ExternalLink, Pencil, RefreshCw, Search, Settings2, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { getJson, sendJson } from "../api";
import { runIndexJob, timeAgo } from "../indexJobs";
import type { AuditEntry, Job, ProjectOverview, ProjectSettings, ServerStatus } from "../types";
import { MenuSelect } from "./Popover";
import { RemoveProjectDialog } from "./RemoveProjectDialog";

type Tab = "projects" | "activity" | "status";
type SortKey = "name" | "indexed" | "files";

type Props = {
  currentId: string;
  initialTab?: Tab;
  onOpen: (id: string) => void;
  onAdd: () => void;
  onRemoved: (id: string) => void;
  onRenamed: () => void;
  /** Called after an index job finishes for `id` (the dashboard reloads that project's views). */
  onIndexed: (id: string) => void;
  onClose: () => void;
};

/** Manage projects: search/sort, stats, re-index, rename, per-project settings, remove; plus the
 * audit log and the server status page. */
export function ProjectsPage({ currentId, initialTab = "projects", onOpen, onAdd, onRemoved, onRenamed, onIndexed, onClose }: Props) {
  const [tab, setTab] = useState<Tab>(initialTab);
  const [items, setItems] = useState<ProjectOverview[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<SortKey>("indexed");
  const [jobs, setJobs] = useState<Record<string, Job>>({});
  const [renaming, setRenaming] = useState<{ id: string; name: string; error?: string } | null>(null);
  const [settingsFor, setSettingsFor] = useState<string | null>(null);
  const [removing, setRemoving] = useState<ProjectOverview | null>(null);

  const load = useCallback(() => {
    getJson<ProjectOverview[]>("/projects/overview")
      .then((r) => {
        setItems(r);
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const list = (items ?? []).filter(
      (p) => !needle || p.name.toLowerCase().includes(needle) || p.root_path.toLowerCase().includes(needle) || (p.framework ?? "").toLowerCase().includes(needle),
    );
    return list.sort((a, b) =>
      sort === "name"
        ? a.name.localeCompare(b.name)
        : sort === "files"
          ? (b.files ?? 0) - (a.files ?? 0)
          : String(b.indexed_at ?? "").localeCompare(String(a.indexed_at ?? "")),
    );
  }, [items, q, sort]);

  const reindex = async (p: ProjectOverview, incremental: boolean) => {
    try {
      const done = await runIndexJob(p.id, { incremental, onProgress: (j) => setJobs((m) => ({ ...m, [p.id]: j })) });
      setJobs((m) => ({ ...m, [p.id]: done }));
      load();
      onIndexed(p.id);
    } catch (e) {
      setJobs((m) => ({ ...m, [p.id]: { id: "", status: "failed", message: "", error: e instanceof Error ? e.message : "failed" } }));
    }
  };

  const saveRename = async () => {
    if (!renaming) return;
    try {
      await sendJson("PATCH", `/projects/${renaming.id}`, { name: renaming.name });
      setRenaming(null);
      load();
      onRenamed();
    } catch (e) {
      setRenaming({ ...renaming, error: e instanceof Error ? e.message : "Rename failed" });
    }
  };

  return (
    <main className="projects-page" aria-labelledby="projects-title">
      <header className="projects-head">
        <h1 id="projects-title">Projects</h1>
        <div className="panel-tabs projects-tabs" role="tablist">
          {(["projects", "activity", "status"] as Tab[]).map((t) => (
            <button key={t} type="button" role="tab" aria-selected={tab === t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
              {t === "projects" ? "Projects" : t === "activity" ? "Activity" : "Status"}
            </button>
          ))}
        </div>
        <div className="projects-head-actions">
          <button type="button" className="btn secondary small" onClick={onAdd}>
            Add repository
          </button>
          {currentId ? (
            <button type="button" className="btn ghost small" onClick={onClose}>
              Back to diagram
            </button>
          ) : null}
        </div>
      </header>

      {tab === "projects" ? (
        <section aria-label="Project list">
          <div className="projects-toolbar">
            <label className="search-field">
              <Search size={14} strokeWidth={1.5} aria-hidden className="search-icon" />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, path, framework" aria-label="Search projects" />
            </label>
            <span className="muted">Sort</span>
            <MenuSelect<SortKey>
              label="Sort projects"
              value={sort}
              onChange={setSort}
              options={[
                { value: "indexed", label: "Last indexed" },
                { value: "name", label: "Name" },
                { value: "files", label: "Size (files)" },
              ]}
            />
          </div>
          {error ? (
            <p className="form-error" role="alert">
              Couldn't load projects: {error}
            </p>
          ) : null}
          {items === null && !error ? <p className="muted pad">Loading projects…</p> : null}
          {items && items.length === 0 ? (
            <div className="empty-hint">
              <p>No repository yet.</p>
              <button type="button" className="btn primary small" onClick={onAdd}>
                Add a repository
              </button>
            </div>
          ) : null}
          <ul className="project-rows">
            {shown.map((p) => {
              const job = jobs[p.id];
              const running = job && (job.status === "pending" || job.status === "running");
              return (
                <li key={p.id} className={`project-row ${p.id === currentId ? "current" : ""}`}>
                  <div className="project-row-main">
                    {renaming?.id === p.id ? (
                      <form
                        className="rename-form"
                        onSubmit={(e) => {
                          e.preventDefault();
                          void saveRename();
                        }}
                      >
                        <input
                          autoFocus
                          aria-label={`New name for ${p.name}`}
                          value={renaming.name}
                          maxLength={120}
                          onChange={(e) => setRenaming({ ...renaming, name: e.target.value, error: undefined })}
                          onKeyDown={(e) => e.key === "Escape" && setRenaming(null)}
                        />
                        <button type="submit" className="btn primary small" disabled={!renaming.name.trim()}>
                          Save
                        </button>
                        <button type="button" className="btn ghost small" onClick={() => setRenaming(null)}>
                          Cancel
                        </button>
                        {renaming.error ? <span className="form-error">{renaming.error}</span> : null}
                      </form>
                    ) : (
                      <h2 className="project-row-name">
                        {p.name}
                        {p.id === currentId ? <span className="badge">open</span> : null}
                        {p.stale ? (
                          <span className="badge badge-warn" title={`HEAD ${p.head_commit?.slice(0, 8)} · indexed ${p.indexed_commit?.slice(0, 8)}`}>
                            new commits since index
                          </span>
                        ) : null}
                        {p.source_missing ? <span className="badge badge-warn">source folder missing</span> : null}
                        {p.indexing || running ? <span className="badge">indexing</span> : null}
                      </h2>
                    )}
                    <p className="muted project-row-path mono" title={p.root_path}>
                      {p.git_url ?? p.root_path}
                    </p>
                    <p className="project-row-stats">
                      <span>{p.files ?? p.stats.files ?? "?"} files</span>
                      <span>{p.stats.endpoints ?? 0} routes</span>
                      <span>{p.stats.models ?? 0} models</span>
                      <span>{(p.stats.nodes ?? 0).toLocaleString()} nodes</span>
                      <span title={p.indexed_at ?? undefined}>indexed {timeAgo(p.indexed_at)}</span>
                      {p.framework ? <span className="muted">{p.framework}</span> : null}
                    </p>
                    {job ? (
                      <p className={job.status === "failed" ? "form-error" : "muted"} role="status">
                        {running ? (
                          <>
                            <progress max={1} value={job.progress ?? 0} aria-label="Index progress" /> {job.message || "Indexing…"}
                          </>
                        ) : job.status === "failed" ? (
                          `Index failed: ${job.error ?? "unknown error"}`
                        ) : (
                          job.message
                        )}
                      </p>
                    ) : null}
                    {settingsFor === p.id ? <ProjectSettingsForm projectId={p.id} onClose={() => setSettingsFor(null)} /> : null}
                  </div>
                  <div className="project-row-actions">
                    <button type="button" className="btn secondary small" onClick={() => onOpen(p.id)}>
                      <ExternalLink size={14} strokeWidth={1.5} aria-hidden /> Open
                    </button>
                    <button
                      type="button"
                      className="btn ghost small"
                      disabled={Boolean(running) || p.indexing || p.source_missing}
                      onClick={() => void reindex(p, true)}
                      title="Re-analyse only if files changed since the last index (fast)"
                    >
                      <RefreshCw size={14} strokeWidth={1.5} aria-hidden /> Re-index changed
                    </button>
                    <button
                      type="button"
                      className="btn ghost small"
                      disabled={Boolean(running) || p.indexing || p.source_missing}
                      onClick={() => void reindex(p, false)}
                      title="Rebuild the whole index from scratch"
                    >
                      Full re-index
                    </button>
                    <button type="button" className="icon-btn" title="Rename" aria-label={`Rename ${p.name}`} onClick={() => setRenaming({ id: p.id, name: p.name })}>
                      <Pencil size={14} strokeWidth={1.5} aria-hidden />
                    </button>
                    <button
                      type="button"
                      className="icon-btn"
                      title="Settings: ignore patterns, auto-refresh"
                      aria-label={`Settings for ${p.name}`}
                      aria-expanded={settingsFor === p.id}
                      onClick={() => setSettingsFor((s) => (s === p.id ? null : p.id))}
                    >
                      <Settings2 size={14} strokeWidth={1.5} aria-hidden />
                    </button>
                    <button
                      type="button"
                      className="icon-btn danger-icon"
                      title="Remove from this tool (your source folder is never touched)"
                      aria-label={`Remove ${p.name}`}
                      disabled={Boolean(running) || p.indexing}
                      onClick={() => setRemoving(p)}
                    >
                      <Trash2 size={14} strokeWidth={1.5} aria-hidden />
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      {tab === "activity" ? <AuditLog /> : null}
      {tab === "status" ? <StatusPanel /> : null}

      {removing ? (
        <RemoveProjectDialog
          project={removing}
          onCancel={() => setRemoving(null)}
          onRemoved={(id) => {
            setRemoving(null);
            setItems((list) => (list ?? []).filter((x) => x.id !== id));
            onRemoved(id);
          }}
        />
      ) : null}
    </main>
  );
}

function ProjectSettingsForm({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const [settings, setSettings] = useState<ProjectSettings | null>(null);
  const [text, setText] = useState("");
  const [auto, setAuto] = useState(false);
  const [state, setState] = useState<"idle" | "saving" | "saved" | string>("idle");

  useEffect(() => {
    getJson<ProjectSettings>(`/projects/${projectId}/settings`)
      .then((s) => {
        setSettings(s);
        setText(s.ignore.join("\n"));
        setAuto(s.auto_refresh);
      })
      .catch((e: Error) => setState(e.message));
  }, [projectId]);

  const save = async () => {
    setState("saving");
    try {
      const s = await sendJson<ProjectSettings>("PUT", `/projects/${projectId}/settings`, {
        ignore: text.split("\n").map((l) => l.trim()).filter(Boolean),
        auto_refresh: auto,
      });
      setSettings(s);
      setText(s.ignore.join("\n"));
      setState("saved");
    } catch (e) {
      setState(e instanceof Error ? e.message : "Save failed");
    }
  };

  return (
    <form
      className="project-settings"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <label className="field">
        <span>Ignore patterns (one per line, gitignore style; applied on the next index)</span>
        <textarea
          rows={5}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setState("idle");
          }}
          placeholder={"legacy/\n*/migrations/\nscripts/*.py"}
          spellCheck={false}
          className="mono"
        />
      </label>
      <p className="muted">
        Stored in this tool's data folder, not in your repository. Generated folders (node_modules, .venv, dist, build, htmlcov, coverage) are always skipped.
      </p>
      {settings?.repo_ciignore ? (
        <details>
          <summary className="muted">This repository also has a .ciignore (read-only here)</summary>
          <pre className="mono project-settings-ci">{settings.repo_ciignore}</pre>
        </details>
      ) : null}
      <label className="switch-row">
        <input type="checkbox" checked={auto} onChange={(e) => (setAuto(e.target.checked), setState("idle"))} />
        <span>
          Keep up to date automatically: re-index changed files when git HEAD moves (after <code>git pull</code>, a commit or a branch switch)
        </span>
      </label>
      <div className="auth-actions">
        <button type="button" className="btn ghost small" onClick={onClose}>
          Close
        </button>
        <button type="submit" className="btn primary small" disabled={!settings || state === "saving"}>
          {state === "saving" ? "Saving…" : "Save settings"}
        </button>
      </div>
      {state === "saved" ? (
        <p className="muted" role="status">
          Saved. Ignore patterns take effect on the next re-index.
        </p>
      ) : state !== "idle" && state !== "saving" ? (
        <p className="form-error" role="alert">
          {state}
        </p>
      ) : null}
    </form>
  );
}

const ACTION_LABEL: Record<string, string> = {
  "project.add": "Added",
  "project.analyze": "Added and indexed",
  "project.index": "Re-indexed",
  "project.auto_refresh": "Auto-refreshed",
  "project.rename": "Renamed",
  "project.settings": "Settings changed",
  "project.delete": "Removed",
};

function AuditLog() {
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    getJson<{ entries: AuditEntry[] }>("/audit?limit=300")
      .then((r) => setEntries(r.entries))
      .catch((e: Error) => setError(e.message));
  }, []);
  if (error) return <p className="form-error">Couldn't load the activity log: {error}</p>;
  if (!entries) return <p className="muted pad">Loading…</p>;
  if (!entries.length) return <p className="muted pad">No activity recorded yet. Adding, indexing, renaming, settings changes and removals appear here.</p>;
  return (
    <div className="audit-wrap">
      <table className="audit-table">
        <caption className="sr-only">Mutating actions, newest first</caption>
        <thead>
          <tr>
            <th scope="col">When</th>
            <th scope="col">Action</th>
            <th scope="col">Project</th>
            <th scope="col">Result</th>
            <th scope="col">By</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e, i) => (
            <tr key={`${e.ts}-${i}`}>
              <td title={e.ts}>{timeAgo(e.ts)}</td>
              <td>{ACTION_LABEL[e.action] ?? e.action}</td>
              <td>{e.project_name ?? e.project_id ?? "—"}</td>
              <td className={e.outcome === "failed" ? "form-error" : undefined}>
                {e.outcome}
                {e.action === "project.rename" ? ` (${String(e.detail.from)} → ${String(e.detail.to)})` : ""}
                {typeof e.detail.message === "string" && e.detail.message ? ` · ${e.detail.message}` : ""}
              </td>
              <td className="muted">{e.actor}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusPanel() {
  const [s, setS] = useState<ServerStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    getJson<ServerStatus>("/status")
      .then(setS)
      .catch((e: Error) => setError(e.message));
  }, []);
  if (error) return <p className="form-error">Couldn't reach the API: {error}</p>;
  if (!s) return <p className="muted pad">Loading…</p>;
  return (
    <section className="status-grid" aria-label="Server status">
      <dl>
        <div>
          <dt>API</dt>
          <dd>
            {s.status} · v{s.version}
          </dd>
        </div>
        <div>
          <dt>Mode</dt>
          <dd>{s.mode === "server" ? "Server (API key required, paths limited to CI_PROJECT_ROOTS)" : "Local (single user)"}</dd>
        </div>
        <div>
          <dt>AI answers</dt>
          <dd>{s.llm_enabled ? "LLM enabled (ALLOW_LLM)" : "Graph-only (no code leaves this machine)"}</dd>
        </div>
        <div>
          <dt>Private GitHub</dt>
          <dd>{s.github_token_configured ? "CI_GITHUB_TOKEN configured" : "No token (public repos and local paths only)"}</dd>
        </div>
        <div>
          <dt>Projects</dt>
          <dd>{s.project_count}</dd>
        </div>
        {s.data_dir ? (
          <div>
            <dt>Data folder</dt>
            <dd className="mono">{s.data_dir}</dd>
          </div>
        ) : null}
        <div>
          <dt>Running jobs</dt>
          <dd>{s.active_jobs.length ? s.active_jobs.map((j) => `${j.project_name}: ${j.message || j.status}`).join(" · ") : "none"}</dd>
        </div>
        <div>
          <dt>Analyzers</dt>
          <dd>{s.analyzers.map((a) => `${a.name} v${a.version}`).join(" · ")}</dd>
        </div>
      </dl>
    </section>
  );
}
