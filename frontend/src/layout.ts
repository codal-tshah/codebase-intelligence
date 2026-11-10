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
  return direction === "LR" ? wrapWideRanks(nodes, out) : out;
}

/**
 * Hub-and-spoke graphs (a function with 100+ callers) put every spoke in one dagre rank,
 * producing a single very tall column. Wrap any rank taller than `maxPerColumn` into several
 * sub-columns (keeping dagre's vertical order) and shift the following ranks right.
 */
export function wrapWideRanks(
  nodes: LayoutInput[],
  pos: Map<string, { x: number; y: number }>,
  maxPerColumn = 14,
  gapX = 28,
  gapY = 16,
): Map<string, { x: number; y: number }> {
  const ranks = new Map<number, LayoutInput[]>();
  for (const n of nodes) {
    const x = Math.round(pos.get(n.id)!.x);
    ranks.set(x, [...(ranks.get(x) ?? []), n]);
  }
  if (![...ranks.values()].some((r) => r.length > maxPerColumn)) return pos;
  const out = new Map<string, { x: number; y: number }>();
  const rowH = Math.max(...nodes.map((m) => m.height)) + gapY;
  const oldH = Math.max(...nodes.map((m) => pos.get(m.id)!.y)) || 1;
  // compress the untouched ranks to the new (wrapped) height so hubs stay vertically centred
  const scaleY = Math.min(1, (maxPerColumn * rowH) / oldH);
  let shift = 0;
  for (const x of [...ranks.keys()].sort((a, b) => a - b)) {
    const members = ranks.get(x)!.sort((a, b) => pos.get(a.id)!.y - pos.get(b.id)!.y);
    if (members.length <= maxPerColumn) {
      let prevY = -Infinity;
      for (const m of members) {
        // keep at least one row of spacing after scaling so nodes in a rank never overlap
        const y = Math.max(pos.get(m.id)!.y * scaleY, prevY + rowH);
        prevY = y;
        out.set(m.id, { x: pos.get(m.id)!.x + shift, y });
      }
      continue;
    }
    const colW = Math.max(...members.map((m) => m.width));
    const cols = Math.ceil(members.length / maxPerColumn);
    members.forEach((m, i) => {
      out.set(m.id, { x: x + shift + Math.floor(i / maxPerColumn) * (colW + gapX), y: 24 + (i % maxPerColumn) * rowH });
    });
    shift += (cols - 1) * (colW + gapX);
  }
  return out;
}

export const LAYER_ORDER = ["api", "middleware", "service", "data", "ui", "config", "test", "external"];
export const LANE_HEADER = 40;

/**
 * Layers view: one column per architectural layer (direct labels instead of a long dagre chain).
 * Nodes inside a layer are ordered by `rank` (higher first) and wrap into sub-columns.
 */
export function layoutByLayer(
  nodes: (LayoutInput & { layer?: string | null; rank: number })[],
  { rowsPerColumn = 12, gapX = 28, gapY = 16, laneGap = 72 } = {},
): { positions: Map<string, { x: number; y: number }>; lanes: { id: string; x: number; width: number; count: number }[] } {
  const byLayer = new Map<string, typeof nodes>();
  for (const n of nodes) {
    const key = n.layer && LAYER_ORDER.includes(n.layer) ? n.layer : "other";
    byLayer.set(key, [...(byLayer.get(key) ?? []), n]);
  }
  const order = [...LAYER_ORDER, "other"].filter((k) => byLayer.has(k));
  const positions = new Map<string, { x: number; y: number }>();
  const lanes: { id: string; x: number; width: number; count: number }[] = [];
  let x = 0;
  for (const key of order) {
    const items = [...byLayer.get(key)!].sort((a, b) => b.rank - a.rank || a.id.localeCompare(b.id));
    const colW = Math.max(...items.map((i) => i.width));
    const cols = Math.ceil(items.length / rowsPerColumn);
    items.forEach((n, i) => {
      const col = Math.floor(i / rowsPerColumn);
      const row = i % rowsPerColumn;
      positions.set(n.id, { x: x + col * (colW + gapX), y: LANE_HEADER + row * (n.height + gapY) });
    });
    const width = cols * colW + (cols - 1) * gapX;
    lanes.push({ id: key, x, width, count: items.length });
    x += width + laneGap;
  }
  return { positions, lanes };
}
