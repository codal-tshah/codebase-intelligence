/**
 * Selection tracing and edge bundling for graph views (pure functions, unit-tested).
 *
 * Direction is always relative to the selected node:
 *   upstream   ("in")  nodes that depend on the selection: they call / import / route to it
 *   downstream ("out") nodes the selection depends on: it calls / imports / reads them
 */

export type TraceDirection = "both" | "up" | "down";
export type TraceRole = "up" | "down" | "both";

export type TraceSettings = {
  direction: TraceDirection;
  /** Hops to follow; `Infinity` (shown as "All") follows the whole reachable chain. */
  depth: number;
};

export const DEFAULT_TRACE: TraceSettings = { direction: "both", depth: 1 };
/** Depth choices offered in the UI (plus "All"). */
export const TRACE_DEPTHS = [1, 2, 3, 4, 5, 6, 8, 10];

type EdgeLike = { id: string; source: string; target: string; edge_type: string };

type WalkResult = { hops: Map<string, number>; edgeIds: Set<string> };

export type TraceResult = {
  /** node id → hop distance upstream (1 = direct dependant). */
  up: Map<string, number>;
  /** node id → hop distance downstream (1 = direct dependency). */
  down: Map<string, number>;
  /** edge id → which side of the trace it belongs to. */
  edgeRole: Map<string, TraceRole>;
};

/** Containment is drawn by nesting, never followed as a dependency. */
const NOT_DEPENDENCY = new Set(["CONTAINS"]);

function walk(start: string, edges: EdgeLike[], forward: boolean, depth: number): WalkResult {
  const adj = new Map<string, EdgeLike[]>();
  for (const e of edges) {
    if (NOT_DEPENDENCY.has(e.edge_type) || e.source === e.target) continue;
    const key = forward ? e.source : e.target;
    const list = adj.get(key);
    if (list) list.push(e);
    else adj.set(key, [e]);
  }
  const hops = new Map<string, number>();
  const edgeIds = new Set<string>();
  let frontier = [start];
  const seen = new Set([start]);
  for (let d = 1; d <= depth && frontier.length; d++) {
    const next: string[] = [];
    for (const cur of frontier) {
      for (const e of adj.get(cur) ?? []) {
        const other = forward ? e.target : e.source;
        // An edge into an already-visited node still belongs to the traced chain (diamonds).
        edgeIds.add(e.id);
        if (seen.has(other)) continue;
        seen.add(other);
        hops.set(other, d);
        next.push(other);
      }
    }
    frontier = next;
  }
  return { hops, edgeIds };
}

/** Multi-hop trace from `selected` over the edges that are drawn on the canvas. */
export function traceSelection(selected: string, edges: EdgeLike[], settings: TraceSettings): TraceResult {
  const depth = Math.max(1, settings.depth);
  const up: WalkResult =
    settings.direction === "down"
      ? { hops: new Map<string, number>(), edgeIds: new Set<string>() }
      : walk(selected, edges, false, depth);
  const down: WalkResult =
    settings.direction === "up"
      ? { hops: new Map<string, number>(), edgeIds: new Set<string>() }
      : walk(selected, edges, true, depth);
  const edgeRole = new Map<string, TraceRole>();
  for (const id of up.edgeIds) edgeRole.set(id, "up");
  for (const id of down.edgeIds) edgeRole.set(id, edgeRole.has(id) ? "both" : "down");
  return { up: up.hops, down: down.hops, edgeRole };
}

/** Role of a node in a trace (a node can be both upstream and downstream in a cycle). */
export function nodeRole(id: string, t: TraceResult): TraceRole | null {
  const u = t.up.has(id);
  const d = t.down.has(id);
  return u && d ? "both" : u ? "up" : d ? "down" : null;
}

// --------------------------------------------------------------------------- bundling

/** Draw priority when several relation types connect the same pair: the most specific wins. */
const TYPE_PRIORITY = [
  "HTTP_CALLS",
  "ROUTES_TO",
  "WRITES_MODEL",
  "READS_MODEL",
  "QUERIES",
  "CALLS",
  "SUBSCRIBES",
  "RENDERS",
  "MIDDLEWARE",
  "INJECTS",
  "DEPENDS_ON",
  "FK_TO",
  "HANDLES",
  "IMPORTS",
];

export type BundledEdge<E> = E & {
  /** All original edge ids folded into this one (first id is the bundle's id). */
  memberIds: string[];
  /** relation type → count across the bundle. */
  byType: Record<string, number>;
  /** Total underlying relations (sums server-side aggregation weights). */
  weight: number;
};

/**
 * Fold parallel edges (same source → target) into one drawn edge, so "imports + calls + reads"
 * between two modules is one line with a breakdown instead of three overlapping strokes.
 * CONTAINS edges are never merged with dependencies.
 */
export function bundleParallelEdges<
  E extends EdgeLike & { confidence?: number | null; properties?: Record<string, unknown> | null },
>(edges: E[]): BundledEdge<E>[] {
  const byPair = new Map<string, E[]>();
  const order: string[] = [];
  for (const e of edges) {
    const key = e.edge_type === "CONTAINS" ? `c|${e.id}` : `${e.source}\u0000${e.target}`;
    const list = byPair.get(key);
    if (list) list.push(e);
    else {
      byPair.set(key, [e]);
      order.push(key);
    }
  }
  return order.map((key) => {
    const group = byPair.get(key)!;
    const byType: Record<string, number> = {};
    let weight = 0;
    for (const e of group) {
      const w = Math.max(1, Number(e.properties?.weight ?? 1));
      weight += w;
      const inner = e.properties?.by_type as Record<string, number> | undefined;
      if (inner && typeof inner === "object") {
        for (const [t, n] of Object.entries(inner)) byType[t] = (byType[t] ?? 0) + Number(n);
      } else {
        byType[e.edge_type] = (byType[e.edge_type] ?? 0) + w;
      }
    }
    const rank = (t: string) => {
      const i = TYPE_PRIORITY.indexOf(t);
      return i < 0 ? TYPE_PRIORITY.length : i;
    };
    const lead = [...group].sort((a, b) => rank(a.edge_type) - rank(b.edge_type))[0];
    const confidence = Math.max(...group.map((e) => e.confidence ?? 1));
    return {
      ...lead,
      id: group[0].id,
      confidence,
      memberIds: group.map((e) => e.id),
      byType,
      weight,
    };
  });
}

/** "calls ×3 · imports" style summary of a bundle for labels and tooltips. */
export function bundleLabel(byType: Record<string, number>, labelFor: (t: string) => string): string {
  return Object.entries(byType)
    .sort((a, b) => b[1] - a[1])
    .map(([t, n]) => (n > 1 ? `${labelFor(t)} ×${n}` : labelFor(t)))
    .join(" · ");
}
