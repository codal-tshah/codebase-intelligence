import { useEffect, useState } from "react";
import { getJson } from "../api";
import { EDGE_STYLE } from "../graphTheme";
import type { PathResult, SearchHit } from "../types";
import { NodeSearch } from "./NodeSearch";

type Props = {
  projectId: string;
  selectedNodeId: string | null;
  selectedNodeName?: string;
  result: PathResult | null;
  onResult: (r: PathResult | null) => void;
  onPickNode: (id: string) => void;
};

/** Shortest dependency path between two nodes (BFS over the knowledge graph). */
export function PathPanel({ projectId, selectedNodeId, selectedNodeName, result, onResult, onPickNode }: Props) {
  const [from, setFrom] = useState<{ id: string; name: string } | null>(null);
  const [to, setTo] = useState<{ id: string; name: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (selectedNodeId && selectedNodeName && !from) setFrom({ id: selectedNodeId, name: selectedNodeName });
  }, [selectedNodeId, selectedNodeName, from]);

  const find = async () => {
    if (!from || !to) return;
    setBusy(true);
    setError(null);
    try {
      const params = new URLSearchParams({ source: from.id, target: to.id });
      onResult(await getJson<PathResult>(`/projects/${projectId}/path?${params}`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Path search failed");
    } finally {
      setBusy(false);
    }
  };

  const pick = (setter: (v: { id: string; name: string }) => void) => (hit: SearchHit) =>
    setter({ id: hit.id, name: hit.name });

  return (
    <div className="path">
      <p className="muted">How does one part of the system reach another? Pick two nodes to trace the shortest dependency path.</p>
      <div className="path-field">
        <span className="path-label">From</span>
        <div className="path-pick">
          <strong>{from?.name ?? "—"}</strong>
          <button
            type="button"
            className="link-btn"
            disabled={!selectedNodeId}
            onClick={() => selectedNodeId && setFrom({ id: selectedNodeId, name: selectedNodeName ?? selectedNodeId })}
          >
            use selected
          </button>
        </div>
        <NodeSearch projectId={projectId} placeholder="Search start node…" onPick={pick(setFrom)} />
      </div>
      <div className="path-field">
        <span className="path-label">To</span>
        <div className="path-pick">
          <strong>{to?.name ?? "—"}</strong>
        </div>
        <NodeSearch projectId={projectId} placeholder="Search target node…" onPick={pick(setTo)} />
      </div>
      <button type="button" className="btn primary" disabled={!from || !to || busy} onClick={find}>
        {busy ? "Searching…" : "Find shortest path"}
      </button>
      {error ? <p className="error-text">{error}</p> : null}

      {result ? (
        result.found ? (
          <div className="path-result">
            <p className="muted">
              {result.node_ids.length - 1} hop{result.node_ids.length === 2 ? "" : "s"}
            </p>
            <ol>
              {result.nodes.map((n, i) => {
                const edge = result.edges[i];
                return (
                  <li key={n.id}>
                    <button type="button" onClick={() => onPickNode(n.id)}>
                      <span className="tour-index">{i + 1}</span>
                      <span className="impact-name">{n.name}</span>
                      <span className="impact-sub">{n.node_type}</span>
                    </button>
                    {edge ? <span className="path-edge">↓ {EDGE_STYLE[edge.edge_type]?.label ?? edge.edge_type}</span> : null}
                  </li>
                );
              })}
            </ol>
            <button type="button" className="btn ghost small" onClick={() => onResult(null)}>
              Clear overlay
            </button>
          </div>
        ) : (
          <p className="muted pad">No dependency path found{result.reason ? ` (${result.reason})` : ""}.</p>
        )
      ) : null}
    </div>
  );
}
