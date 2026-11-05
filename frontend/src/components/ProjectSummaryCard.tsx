import { useState } from "react";

export type ProjectSummary = {
  summary: string;
  techStack: string[];
  patterns: string[];
  stats: {
    files: number;
    lines: string;
    languages: number;
    nodes?: number;
    edges?: number;
    endpoints?: number;
    models?: number;
    components?: number;
    httpLinks?: number;
  };
  layers?: { id: string; name: string; color: string; count: number }[];
  hotspots?: { id: string; name: string; node_type: string; score: number }[];
  integrations?: string[];
  warnings?: string[];
};

type Props = {
  projectName: string;
  gitUrl?: string;
  summary: ProjectSummary | null;
  loading?: boolean;
  onPickNode?: (id: string) => void;
};

const STORAGE_KEY = "ci.summary.open";

function readOpen(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

/** "11 routes, 3 called from the UI" — numbers with context instead of a grid of stat cards. */
function facts(s: ProjectSummary): string[] {
  const out: string[] = [];
  const routes = s.stats.endpoints ?? 0;
  if (routes) out.push(`${routes} route${routes === 1 ? "" : "s"}${s.stats.httpLinks ? `, ${s.stats.httpLinks} called from the UI` : ""}`);
  if (s.stats.models) out.push(`${s.stats.models} data model${s.stats.models === 1 ? "" : "s"}`);
  if (s.stats.components) out.push(`${s.stats.components} UI component${s.stats.components === 1 ? "" : "s"}`);
  out.push(`${s.stats.files} files, ${s.stats.lines} lines`);
  return out;
}

export function ProjectSummaryCard({ projectName, gitUrl, summary, loading, onPickNode }: Props) {
  const [open, setOpen] = useState(readOpen);
  const toggle = () => {
    setOpen((o) => {
      try {
        window.localStorage.setItem(STORAGE_KEY, o ? "0" : "1");
      } catch {
        /* storage unavailable */
      }
      return !o;
    });
  };

  if (loading) {
    return (
      <div className="overview" aria-busy="true" aria-label="Loading project overview">
        <span className="skeleton" style={{ width: "28%", height: 22 }} />
        <span className="skeleton" style={{ width: "72%" }} />
      </div>
    );
  }
  if (!summary) return null;
  const hot = summary.hotspots?.[0];

  return (
    <section className="overview" aria-label="Project overview">
      <div className="overview-head">
        <h1 className="overview-title">{projectName}</h1>
        <p className="overview-facts">{facts(summary).join(" · ")}</p>
        <button type="button" className="btn ghost small overview-toggle" onClick={toggle} aria-expanded={open}>
          {open ? "Less" : "Details"}
        </button>
      </div>
      {hot ? (
        <p className="overview-finding">
          Start with{" "}
          <button type="button" className="inline-link" onClick={() => onPickNode?.(hot.id)}>
            {hot.name}
          </button>
          : {hot.score} other parts of the code depend on it, so changes there have the widest reach.
        </p>
      ) : null}
      {open ? (
        <div className="overview-details">
          <MarkdownInline text={summary.summary} />
          {gitUrl ? <p className="mono muted">{gitUrl.replace(/^https:\/\//, "")}</p> : null}
          <dl className="overview-dl">
            <dt>Stack</dt>
            <dd>{summary.techStack.join(", ")}</dd>
            {summary.patterns.length ? (
              <>
                <dt>Patterns</dt>
                <dd>{summary.patterns.join(", ")}</dd>
              </>
            ) : null}
            {summary.integrations && summary.integrations.length ? (
              <>
                <dt>External</dt>
                <dd>{summary.integrations.join(", ")}</dd>
              </>
            ) : null}
            {summary.hotspots && summary.hotspots.length > 1 ? (
              <>
                <dt>Most depended on</dt>
                <dd>
                  {summary.hotspots.map((h, i) => (
                    <span key={h.id}>
                      {i ? ", " : ""}
                      <button type="button" className="inline-link" onClick={() => onPickNode?.(h.id)}>
                        {h.name}
                      </button>
                      <span className="muted"> ({h.score})</span>
                    </span>
                  ))}
                </dd>
              </>
            ) : null}
          </dl>
          {summary.warnings && summary.warnings.length > 0 ? (
            <p className="overview-warning" title={summary.warnings.join("\n")}>
              {summary.warnings.length} file{summary.warnings.length === 1 ? "" : "s"} had syntax errors and were only partly analyzed.
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function MarkdownInline({ text }: { text: string }) {
  // Escape first: the summary can come from an LLM reading repository content.
  const html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
  return <p className="overview-summary" dangerouslySetInnerHTML={{ __html: html }} />;
}
