import { Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { getJson } from "../api";
import { METHOD_COLORS } from "../graphTheme";
import type { EndpointInfo } from "../types";

type Props = {
  projectId: string;
  reloadKey: number;
  /** Endpoint whose chain is on the canvas. */
  focusedId?: string;
  onPick: (endpoint: EndpointInfo) => void;
};

/** Group key: the router/view file (FastAPI router module, Django views module, Express file). */
function groupOf(e: EndpointInfo): string {
  const path = e.source_path ?? "";
  const file = path.split("/").pop() ?? path;
  return file.replace(/\.(py|ts|tsx|js|jsx|mjs)$/, "") || "other";
}

/** API flow sidebar: every route grouped by router file; picking one draws only its chain. */
export function ApiEndpointList({ projectId, reloadKey, focusedId, onPick }: Props) {
  const [items, setItems] = useState<EndpointInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [method, setMethod] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const autoPicked = useRef(false);

  useEffect(() => {
    if (!projectId) return;
    setItems(null);
    setError(null);
    autoPicked.current = false;
    getJson<{ endpoints: EndpointInfo[] }>(`/projects/${projectId}/endpoints`)
      .then((r) => setItems(r.endpoints))
      .catch((e: Error) => setError(e.message));
  }, [projectId, reloadKey]);

  // One endpoint at a time: open the first one when nothing is focused yet.
  useEffect(() => {
    if (!items?.length || autoPicked.current) return;
    autoPicked.current = true;
    if (!focusedId || !items.some((e) => e.id === focusedId)) onPick(items[0]);
  }, [items, focusedId, onPick]);

  useEffect(() => {
    listRef.current
      ?.querySelector<HTMLElement>(`[data-ep="${CSS.escape(focusedId ?? "")}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [focusedId, items]);

  const methods = useMemo(
    () => [...new Set((items ?? []).flatMap((e) => (e.methods.length ? e.methods : ["ANY"])))].sort(),
    [items],
  );
  const groups = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const out = new Map<string, EndpointInfo[]>();
    for (const e of items ?? []) {
      if (method && !(e.methods.length ? e.methods : ["ANY"]).includes(method)) continue;
      if (needle && !`${e.route} ${e.handler?.name ?? ""} ${e.source_path ?? ""}`.toLowerCase().includes(needle))
        continue;
      const g = groupOf(e);
      out.set(g, [...(out.get(g) ?? []), e]);
    }
    return [...out.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [items, q, method]);
  const shown = groups.reduce((n, [, list]) => n + list.length, 0);

  return (
    <aside className="api-list" aria-label="Endpoints">
      <div className="api-list-head">
        <label className="search-field">
          <Search size={14} strokeWidth={1.5} aria-hidden className="search-icon" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Filter routes"
            aria-label="Filter routes"
          />
        </label>
        <div className="chip-row" role="group" aria-label="Filter by HTTP method">
          {["", ...methods].map((m) => (
            <button
              key={m || "all"}
              type="button"
              className={`chip ${method === m ? "active" : ""}`}
              aria-pressed={method === m}
              onClick={() => setMethod(m)}
            >
              {m || "All"}
            </button>
          ))}
        </div>
        <p className="muted api-list-count">{items ? `${shown} of ${items.length} routes` : "Loading routes…"}</p>
      </div>
      {error ? (
        <p className="form-error pad" role="alert">
          {error}
        </p>
      ) : null}
      <div className="api-list-body" ref={listRef}>
        {groups.map(([group, list]) => (
          <section key={group} className="api-group">
            <h3 className="api-group-title" title={list[0]?.source_path ?? group}>
              {group} <span className="muted">{list.length}</span>
            </h3>
            <ul>
              {list.map((e) => (
                <li key={e.id}>
                  <button
                    type="button"
                    data-ep={e.id}
                    className={`api-item ${e.id === focusedId ? "active" : ""}`}
                    aria-current={e.id === focusedId ? "true" : undefined}
                    onClick={() => onPick(e)}
                    title={`${e.route}${e.handler ? ` → ${e.handler.name}` : ""}`}
                  >
                    <span className="api-item-line">
                      {(e.methods.length ? e.methods : ["ANY"]).map((m) => (
                        <span
                          key={m}
                          className="method-badge"
                          style={{ ["--method" as string]: METHOD_COLORS[m] ?? "#8A867C" }}
                        >
                          {m}
                        </span>
                      ))}
                      <span className="api-item-path mono">{e.route}</span>
                    </span>
                    {e.handler ? (
                      <span className="api-item-handler muted">{e.handler.name}</span>
                    ) : (
                      <span className="api-item-handler muted">handler not resolved</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </aside>
  );
}
