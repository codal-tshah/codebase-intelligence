import { useEffect, useRef, useState } from "react";
import { postJson } from "../api";
import { IMPACT_COLORS } from "../graphTheme";
import type { ImpactItem, ImpactReport } from "../types";

type Props = {
  projectId: string;
  selectedNodeId: string | null;
  selectedNodeName?: string;
  report: ImpactReport | null;
  onReport: (report: ImpactReport | null) => void;
  onPickNode: (id: string) => void;
  autoRunToken: number;
};

export function ImpactPanel({ projectId, selectedNodeId, selectedNodeName, report, onReport, onPickNode, autoRunToken }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [files, setFiles] = useState("");
  const [depth, setDepth] = useState(3);
  const lastToken = useRef(autoRunToken);

  const run = async (body: Record<string, unknown>) => {
    setBusy(true);
    setError(null);
    try {
      onReport(await postJson<ImpactReport>(`/projects/${projectId}/impact`, { depth, ...body }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Impact analysis failed");
    } finally {
      setBusy(false);
    }
  };

  // The freshness banner can ask for a working-tree analysis from outside this panel.
  useEffect(() => {
    if (autoRunToken !== lastToken.current) {
      lastToken.current = autoRunToken;
      void run({});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRunToken]);

  const byHop = new Map<number, ImpactItem[]>();
  for (const a of report?.affected ?? []) {
    const hop = a.hops ?? 1;
    byHop.set(hop, [...(byHop.get(hop) ?? []), a]);
  }

  return (
    <div className="impact">
      <p className="muted">
        See what a change could break: dependants are found by walking edges backwards from the changed code.
      </p>
      <div className="impact-actions">
        <button type="button" className="btn primary small" disabled={busy} onClick={() => run({})}>
          Uncommitted changes
        </button>
        <button
          type="button"
          className="btn ghost small"
          disabled={busy || !selectedNodeId}
          onClick={() => run({ node_ids: [selectedNodeId] })}
          title={selectedNodeName ? `Impact of ${selectedNodeName}` : "Select a node first"}
        >
          Selected node
        </button>
        <label className="depth">
          depth
          <select value={depth} onChange={(e) => setDepth(Number(e.target.value))}>
            {[1, 2, 3, 4, 5].map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>
      </div>
      <form
        className="impact-files"
        onSubmit={(e) => {
          e.preventDefault();
          const list = files.split(/[\s,]+/).filter(Boolean);
          if (list.length) void run({ files: list });
        }}
      >
        <input value={files} onChange={(e) => setFiles(e.target.value)} placeholder="or file paths: shop/models.py, …" />
        <button type="submit" className="btn ghost small" disabled={busy || !files.trim()}>
          Analyze
        </button>
      </form>
      {error ? <p className="error-text">{error}</p> : null}
      {busy ? <p className="muted">Analyzing…</p> : null}

      {report ? (
        <div className="impact-report">
          <div className={`risk risk--${report.risk.level}`}>
            <div className="risk-gauge">
              <span style={{ width: `${report.risk.score}%` }} />
            </div>
            <div>
              <strong>{report.risk.level.toUpperCase()} risk</strong>
              <span className="muted"> · score {report.risk.score}</span>
            </div>
          </div>
          <p className="muted">
            {report.changed.length} changed · {report.affected.length} affected · {report.affected_endpoints.length} endpoint(s)
            {report.changed_files.length ? ` · ${report.changed_files.length} file(s)` : ""}
          </p>
          {report.notes.length > 0 ? (
            <ul className="impact-notes">
              {report.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          ) : null}
          {report.layers.length > 0 ? (
            <div className="chip-row">
              {report.layers.map((l) => (
                <span key={l.id} className="chip static">
                  {l.name} · {l.count}
                </span>
              ))}
            </div>
          ) : null}
          {[...byHop.entries()]
            .sort((a, b) => a[0] - b[0])
            .map(([hop, items]) => (
              <details key={hop} open={hop === 1}>
                <summary>
                  <span className="hop-dot" style={{ background: IMPACT_COLORS[Math.min(hop, 3)] }} />
                  {hop} hop{hop > 1 ? "s" : ""} away · {items.length}
                </summary>
                <ul className="impact-list">
                  {items.slice(0, 40).map((it) => (
                    <li key={it.id}>
                      <button type="button" onClick={() => onPickNode(it.id)}>
                        <span className="impact-name">{it.name}</span>
                        <span className="impact-sub">
                          {it.node_type} · via {it.via_name}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </details>
            ))}
          <button type="button" className="btn ghost small" onClick={() => onReport(null)}>
            Clear overlay
          </button>
        </div>
      ) : null}
    </div>
  );
}
