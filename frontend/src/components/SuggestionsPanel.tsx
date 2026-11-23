import { useEffect, useMemo, useState } from "react";
import { getJson } from "../api";
import { NodeIcon } from "../icons";

type SuggestionNode = { id: string; name: string; type: string; source_path?: string | null; line?: number | null };
type Suggestion = {
  kind: string;
  severity: "high" | "medium" | "low";
  title: string;
  detail: string;
  nodes: SuggestionNode[];
};

const KIND_LABEL: Record<string, string> = {
  hotspot: "Hotspot",
  complexity: "Large function",
  duplication: "Duplication",
  "data-access": "Scattered writes",
  cycle: "Import cycle",
  unused: "Possibly unused",
};

type Props = {
  projectId: string;
  reloadKey: number;
  onPickNode: (id: string) => void;
};

/** Refactoring and reuse leads from `/suggestions` (static heuristics, no LLM). */
export function SuggestionsPanel({ projectId, reloadKey, onPickNode }: Props) {
  const [items, setItems] = useState<Suggestion[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState<string>("all");

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    setItems(null);
    setError(null);
    getJson<{ suggestions: Suggestion[] }>(`/projects/${projectId}/suggestions?limit=100`)
      .then((r) => !cancelled && setItems(r.suggestions))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [projectId, reloadKey]);

  const kinds = useMemo(() => [...new Set((items ?? []).map((s) => s.kind))], [items]);
  const shown = (items ?? []).filter((s) => kind === "all" || s.kind === kind);

  if (error) {
    return (
      <p className="form-error pad" role="alert">
        Couldn't load suggestions: {error}
      </p>
    );
  }
  if (items === null) {
    return (
      <div className="pad" aria-busy="true" aria-label="Loading suggestions">
        <span className="skeleton" style={{ width: "70%" }} />
        <span className="skeleton" style={{ width: "50%", marginTop: 8 }} />
      </div>
    );
  }
  if (items.length === 0) {
    return (
      <p className="muted pad">
        No suggestions: no hotspots, large functions, duplicates, cycles or unused code were detected.
      </p>
    );
  }

  return (
    <div className="suggestions">
      <p className="muted">
        Leads for a reviewer, found by static heuristics. Dynamic calls can be missed, so confirm in the source before
        acting.
      </p>
      <div className="chip-row" role="group" aria-label="Filter suggestions">
        {["all", ...kinds].map((k) => (
          <button
            key={k}
            type="button"
            className={`chip ${kind === k ? "active" : ""}`}
            aria-pressed={kind === k}
            onClick={() => setKind(k)}
          >
            {k === "all" ? `All ${items.length}` : `${KIND_LABEL[k] ?? k} ${items.filter((s) => s.kind === k).length}`}
          </button>
        ))}
      </div>
      <ul className="suggestion-list">
        {shown.map((s, i) => (
          <li key={`${s.kind}-${s.title}-${i}`} className="suggestion">
            <div className="suggestion-head">
              <span className={`severity severity--${s.severity}`}>{s.severity}</span>
              <span className="muted">{KIND_LABEL[s.kind] ?? s.kind}</span>
            </div>
            <p className="suggestion-title">{s.title}</p>
            <p className="muted suggestion-detail">{s.detail}</p>
            <div className="relations">
              <ul>
                {s.nodes.slice(0, 8).map((n) => (
                  <li key={n.id}>
                    <button
                      type="button"
                      onClick={() => onPickNode(n.id)}
                      title={n.source_path ? `${n.source_path}${n.line ? `:${n.line}` : ""}` : n.name}
                    >
                      <NodeIcon type={n.type} size={12} />
                      <span className="impact-name">{n.name}</span>
                      <span className="impact-sub">{n.source_path ?? n.type}</span>
                    </button>
                  </li>
                ))}
              </ul>
              {s.nodes.length > 8 ? <p className="muted">+{s.nodes.length - 8} more</p> : null}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
