import type { LayoutEdge, LayoutInput } from "../layout";

export type ElkLayoutResult = Map<string, { x: number; y: number }>;

/** Layered layout (ELK) over the visible explore subgraph — fewer crossings than dagre for wide graphs. */
export async function layoutExploreNodes(nodes: LayoutInput[], edges: LayoutEdge[]): Promise<ElkLayoutResult> {
  const ELK = (await import("elkjs/lib/elk.bundled.js")).default;
  const elk = new ELK();
  type ElkExtendedEdge = import("elkjs/lib/elk.bundled.js").ElkExtendedEdge;
  type ElkNode = import("elkjs/lib/elk.bundled.js").ElkNode;
  const ids = new Set(nodes.map((n) => n.id));
  const elkNodes: ElkNode[] = nodes.map((n) => ({
    id: n.id,
    width: n.width,
    height: n.height,
  }));
  const elkEdges: ElkExtendedEdge[] = [];
  for (const e of edges) {
    if (!ids.has(e.source) || !ids.has(e.target) || e.source === e.target) continue;
    elkEdges.push({ id: `${e.source}-${e.target}`, sources: [e.source], targets: [e.target] });
  }

  const graph: ElkNode = {
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "RIGHT",
      "elk.spacing.nodeNode": "28",
      "elk.layered.spacing.nodeNodeBetweenLayers": "72",
      "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
    },
    children: elkNodes,
    edges: elkEdges,
  };

  const laid = await elk.layout(graph);
  const out = new Map<string, { x: number; y: number }>();
  for (const n of laid.children ?? []) {
    const w = nodes.find((m) => m.id === n.id)?.width ?? 216;
    const h = nodes.find((m) => m.id === n.id)?.height ?? 78;
    out.set(n.id!, { x: (n.x ?? 0) + w / 2, y: (n.y ?? 0) + h / 2 });
  }
  const positions = new Map<string, { x: number; y: number }>();
  for (const n of nodes) {
    const p = out.get(n.id);
    if (!p) continue;
    positions.set(n.id, { x: p.x - n.width / 2, y: p.y - n.height / 2 });
  }
  return positions;
}
