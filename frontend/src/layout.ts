import dagre from "@dagrejs/dagre";

export type LayoutInput = { id: string; width: number; height: number };
export type LayoutEdge = { source: string; target: string };

/** Left-to-right layered layout (dagre). Returns top-left positions as React Flow expects. */
export function layoutNodes(
  nodes: LayoutInput[],
  edges: LayoutEdge[],
  direction: "LR" | "TB" = "LR",
): Map<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: direction, nodesep: 28, ranksep: 90, marginx: 24, marginy: 24 });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of nodes) g.setNode(n.id, { width: n.width, height: n.height });
  const ids = new Set(nodes.map((n) => n.id));
  for (const e of edges) {
    if (ids.has(e.source) && ids.has(e.target) && e.source !== e.target) g.setEdge(e.source, e.target);
  }
  dagre.layout(g);
  const out = new Map<string, { x: number; y: number }>();
  for (const n of nodes) {
    const p = g.node(n.id);
    out.set(n.id, { x: p.x - n.width / 2, y: p.y - n.height / 2 });
  }
  return out;
}
