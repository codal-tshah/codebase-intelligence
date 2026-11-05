import { useEffect, useMemo, useState } from "react";
import { getJson } from "../api";
import type { EndpointInfo, NodeRef } from "../types";

type Props = {
  projectId: string;
  reloadKey: number;
  selectedId: string | null;
  onTrace: (endpoint: EndpointInfo) => void;
  onPickNode: (id: string) => void;
};

/** API explorer: every route (any framework) with its handler, guards, data access and UI callers. */
export function EndpointsPanel({ projectId, reloadKey, selectedId, onTrace, onPickNode }: Props) {
  const [items, setItems] = useState<EndpointInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [method, setMethod] = useState<string>("");
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    setItems(null);
    setError(null);
    getJson<{ endpoints: EndpointInfo[] }>(`/projects/${projectId}/endpoints`)
      .then((r) => setItems(r.endpoints))
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load endpoints"));
  }, [projectId, reloadKey]);

  useEffect(() => {
    if (selectedId && items?.some((e) => e.id === selectedId)) setExpanded(selectedId);
  }, [selectedId, items]);

  const methods = useMemo(() => {
    const all = new Set<string>();
    for (const e of items ?? []) for (const m of e.methods.length ? e.methods : ["ANY"]) all.add(m);
    return [...all].sort();
  }, [items]);

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return (items ?? []).filter((e) => {
      if (method && !(e.methods.length ? e.methods : ["ANY"]).includes(method)) return false;
      if (!q) return true;
      return (
        e.route.toLowerCase().includes(q) ||
        (e.handler?.name ?? "").toLowerCase().includes(q) ||
        (e.source_path ?? "").toLowerCase().includes(q) ||
        e.models.some((m) => m.name.toLowerCase().includes(q))
      );
    });
  }, [items, filter, method]);

  if (error) return <p className="error-text pad">{error}</p>;
  if (!items)
    return (
      <div className="skeleton-list" aria-busy="true" aria-label="Loading endpoints">
        {Array.from({ length: 7 }, (_, i) => (
          <span key={i} className="skeleton" style={{ width: `${70 + ((i * 17) % 30)}%` }} />
        ))}
      </div>
    );
  if (items.length === 0)
    return (
      <div className="placeholder">
        <p className="placeholder-title">No HTTP endpoints found</p>
        <p className="muted">Routes are detected for Django, FastAPI, Flask, Express, NestJS and Next.js.</p>
      </div>
    );

  const linked = items.filter((e) => e.callers.length > 0).length;

  return (
    <div className="endpoints">
      <div className="endpoints-head">
        <p className="muted">
          {items.length} route{items.length === 1 ? "" : "s"} · {linked} called from client code
        </p>
        <input className="endpoints-filter" placeholder="Filter by route, handler, model…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <div className="chip-row">
          <button type="button" className={`chip ${method === "" ? "active" : ""}`} onClick={() => setMethod("")}>
            all
          </button>
          {methods.map((m) => (
            <button key={m} type="button" className={`chip ${method === m ? "active" : ""}`} onClick={() => setMethod(m === method ? "" : m)}>
              {m}
            </button>
          ))}
        </div>
      </div>
      <ul className="endpoint-list">
        {visible.map((e) => {
          const open = expanded === e.id;
          return (
            <li key={e.id} className={`endpoint ${selectedId === e.id ? "selected" : ""}`}>
              <button type="button" className="endpoint-row" onClick={() => setExpanded(open ? null : e.id)}>
                <span className="method-group">
                  {(e.methods.length ? e.methods : ["ANY"]).map((m) => (
                    <span key={m} className={`method method--${m}`}>
                      {m}
                    </span>
                  ))}
                </span>
                <span className="endpoint-route" title={e.route}>
                  {e.route}
                </span>
                {e.callers.length ? <span className="endpoint-callers" title="Called from client code">{e.callers.length} caller{e.callers.length > 1 ? "s" : ""}</span> : null}
              </button>
              {open ? (
                <div className="endpoint-detail">
                  <Row label="Handler" items={e.handler ? [e.handler] : []} empty="inline / unresolved" onPick={onPickNode} />
                  <Row label="Guards" items={[...e.guards, ...e.dependencies]} onPick={onPickNode} />
                  <Row label="Data" items={e.models} suffix={(m) => ` (${(m as EndpointInfo["models"][number]).access.join("/")})`} onPick={onPickNode} />
                  <Row label="External" items={e.external} onPick={onPickNode} />
                  <Row label="Called by" items={e.callers} onPick={onPickNode} />
                  <div className="endpoint-actions">
                    <span className="muted mono">
                      {e.framework ?? ""} · {e.source_path}:{e.line}
                    </span>
                    <button type="button" className="btn small primary" onClick={() => onTrace(e)}>
                      Trace flow
                    </button>
                  </div>
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Row({
  label,
  items,
  empty,
  suffix,
  onPick,
}: {
  label: string;
  items: NodeRef[];
  empty?: string;
  suffix?: (n: NodeRef) => string;
  onPick: (id: string) => void;
}) {
  if (!items.length && !empty) return null;
  return (
    <div className="endpoint-row-detail">
      <span className="endpoint-label">{label}</span>
      <span className="endpoint-values">
        {items.length
          ? items.map((n) => (
              <button key={n.id} type="button" className="link-btn" onClick={() => onPick(n.id)}>
                {n.name}
                {suffix ? suffix(n) : ""}
              </button>
            ))
          : <span className="muted">{empty}</span>}
      </span>
    </div>
  );
}
