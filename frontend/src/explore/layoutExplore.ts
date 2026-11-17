import type { GraphEdge, GraphNode } from "../types";

const WIDTH = 216;
const BASE_HEIGHT = 78;
/** Height reserved above a group's children for its single-row title (.arch-group-head + padding). */
export const GROUP_TITLE = 52;
const GROUP_PAD = 16;
const GROUP_MIN_W = 260;
const GROUP_MIN_INNER_H = 100;

export type ExploreLayoutNode = {
  id: string;
  width: number;
  height: number;
  parentId?: string;
  isGroup: boolean;
};

export type ExploreLayoutEdge = { id: string; source: string; target: string };

export type ExploreLayoutInput = {
  graphNodes: GraphNode[];
  graphEdges: GraphEdge[];
};

/** Which visible nodes are expanded groups (children laid out inside). */
function expandedGroupIds(nodes: GraphNode[]): Set<string> {
  const out = new Set<string>();
  for (const n of nodes) {
    const p = n.properties ?? {};
    if (!p.explore_expanded) continue;
    const hasChild = nodes.some((c) => (c.properties?.parent_id as string | undefined) === n.id);
    const trunc = Number(p.truncated_children ?? 0) > 0;
    if (hasChild || trunc) out.add(n.id);
  }
  return out;
}

function directChildren(nodes: GraphNode[], parentId: string): GraphNode[] {
  return nodes
    .filter((n) => (n.properties?.parent_id as string | undefined) === parentId)
    .sort((a, b) => a.label.localeCompare(b.label));
}

function leafSize(_n: GraphNode): { w: number; h: number } {
  void _n;
  return { w: WIDTH, h: BASE_HEIGHT };
}

function measureGroup(
  id: string,
  nodes: GraphNode[],
  groups: Set<string>,
  memo: Map<string, { w: number; h: number }>,
): { w: number; h: number } {
  if (memo.has(id)) return memo.get(id)!;
  const kids = directChildren(nodes, id);
  if (!kids.length) {
    const s = { w: GROUP_MIN_W, h: GROUP_TITLE + GROUP_PAD * 2 + GROUP_MIN_INNER_H };
    memo.set(id, s);
    return s;
  }
  let maxW = 0;
  let sumH = 0;
  for (const c of kids) {
    const sub = groups.has(c.id) ? measureGroup(c.id, nodes, groups, memo) : leafSize(c);
    maxW = Math.max(maxW, sub.w);
    sumH += sub.h + 12;
  }
  const w = Math.max(GROUP_MIN_W, maxW + GROUP_PAD * 2);
  const h = GROUP_TITLE + GROUP_PAD + sumH + GROUP_PAD;
  const s = { w, h };
  memo.set(id, s);
  return s;
}

export function buildExploreLayoutModel(input: ExploreLayoutInput): {
  layoutNodes: ExploreLayoutNode[];
  layoutEdges: ExploreLayoutEdge[];
} {
  const { graphNodes: nodes, graphEdges: edges } = input;
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const groups = expandedGroupIds(nodes);
  const memo = new Map<string, { w: number; h: number }>();

  const layoutNodes: ExploreLayoutNode[] = [];

  for (const n of nodes) {
    const props = n.properties ?? {};
    const pid = (props.parent_id as string | null | undefined) ?? undefined;
    const isG = groups.has(n.id);
    const sz = isG ? measureGroup(n.id, nodes, groups, memo) : leafSize(n);
    layoutNodes.push({
      id: n.id,
      width: sz.w,
      height: sz.h,
      parentId: pid && byId.has(pid) ? pid : undefined,
      isGroup: isG,
    });
  }

  const ids = new Set(nodes.map((n) => n.id));
  const layoutEdges: ExploreLayoutEdge[] = [];
  for (const e of edges) {
    if (!ids.has(e.source) || !ids.has(e.target) || e.source === e.target) continue;
    layoutEdges.push({ id: e.id, source: e.source, target: e.target });
  }

  return { layoutNodes, layoutEdges };
}

type ElkNode = import("elkjs/lib/elk.bundled.js").ElkNode;
type ElkExtendedEdge = import("elkjs/lib/elk.bundled.js").ElkExtendedEdge;

export type ElkLayoutResult = Map<string, { x: number; y: number; width: number; height: number }>;

/** Layout used at the root and inside every expanded group. */
const GROUP_LAYOUT = {
  "elk.algorithm": "layered",
  "elk.direction": "RIGHT",
  "elk.edgeRouting": "ORTHOGONAL",
  "elk.spacing.nodeNode": "28",
  "elk.spacing.edgeNode": "16",
  "elk.spacing.edgeEdge": "8",
  "elk.layered.spacing.nodeNodeBetweenLayers": "56",
  "elk.layered.spacing.edgeNodeBetweenLayers": "16",
  "elk.separateConnectedComponents": "true",
  "elk.spacing.componentComponent": "24",
  "elk.aspectRatio": "1.6",
  "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
  // parallel / converging edges share a trunk instead of running side by side
  "elk.layered.mergeEdges": "true",
};

/** A long dependency chain of wide groups (models → repositories → services → routers) would be
 * one very wide row; wrapping folds it into rows that respect the aspect ratio. Only used where
 * children are themselves groups: for plain cards it would break short chains into columns. */
const WRAP_GROUPS = { "elk.layered.wrapping.strategy": "MULTI_EDGE" };

export type ExploreRoutes = Map<string, { x: number; y: number }[]>;
export const routeKey = (source: string, target: string) => `${source}\u0000${target}`;

/** Chain of ancestors from the root down to `id` (inclusive). */
function chainOf(id: string, parentOf: Map<string, string | undefined>): string[] {
  const out: string[] = [];
  let cur: string | undefined = id;
  let guard = 0;
  while (cur && guard++ < 64) {
    out.unshift(cur);
    cur = parentOf.get(cur);
  }
  return out;
}

/**
 * Nested ELK model. Groups are NOT given a fixed size: ELK sizes each compound node to fit
 * its laid-out children (with a minimum), so children never spill out and siblings never
 * overlap. Child coordinates come back relative to their parent, which is exactly what
 * React Flow expects for nodes with `parentId`.
 *
 * Every dependency edge is declared in the group that is the lowest common ancestor of its two
 * ends, between that group's direct children (deeper ends are lifted). Each group is therefore
 * laid out by its own internal dependencies (left → right) and unconnected children pack into a
 * grid. Edges whose ends are both direct children of the same group get an orthogonal route.
 */
export function buildElkGraph(input: ExploreLayoutInput): ElkNode {
  const { layoutNodes, layoutEdges } = buildExploreLayoutModel(input);
  const parentOf = new Map(layoutNodes.map((n) => [n.id, n.parentId]));
  const childMap = new Map<string | undefined, ExploreLayoutNode[]>();
  for (const n of layoutNodes) {
    const list = childMap.get(n.parentId) ?? [];
    list.push(n);
    childMap.set(n.parentId, list);
  }

  // container id (undefined = root) → edges between its direct children
  const edgesIn = new Map<string | undefined, ElkExtendedEdge[]>();
  const seen = new Set<string>();
  for (const e of layoutEdges) {
    const sc = chainOf(e.source, parentOf);
    const tc = chainOf(e.target, parentOf);
    let i = 0;
    while (i < sc.length && i < tc.length && sc[i] === tc[i]) i++;
    // one end contains the other: nesting already expresses it
    if (i === sc.length || i === tc.length) continue;
    const container = i === 0 ? undefined : sc[i - 1];
    const s = sc[i]!;
    const t = tc[i]!;
    const key = routeKey(s, t);
    if (seen.has(key)) continue;
    seen.add(key);
    const list = edgesIn.get(container) ?? [];
    list.push({ id: `elk:${s}->${t}`, sources: [s], targets: [t] });
    edgesIn.set(container, list);
  }

  const toElk = (n: ExploreLayoutNode): ElkNode => {
    const kids = childMap.get(n.id) ?? [];
    if (n.isGroup && kids.length) {
      return {
        id: n.id,
        layoutOptions: {
          ...GROUP_LAYOUT,
          ...(kids.some((k) => k.isGroup) ? WRAP_GROUPS : {}),
          "elk.padding": `[top=${GROUP_TITLE},left=${GROUP_PAD},bottom=${GROUP_PAD},right=${GROUP_PAD}]`,
          "elk.nodeSize.constraints": "MINIMUM_SIZE",
          "elk.nodeSize.minimum": `(${GROUP_MIN_W}, ${GROUP_TITLE + GROUP_PAD * 2 + 40})`,
        },
        children: kids.map(toElk),
        edges: edgesIn.get(n.id) ?? [],
      };
    }
    return { id: n.id, width: n.width, height: n.height };
  };

  return {
    id: "explore-root",
    layoutOptions: {
      ...GROUP_LAYOUT,
      ...((childMap.get(undefined) ?? []).some((k) => k.isGroup) ? WRAP_GROUPS : {}),
      "elk.layered.spacing.nodeNodeBetweenLayers": "72",
      "elk.spacing.componentComponent": "40",
      // Each group is laid out on its own (inside-out) with the edges declared inside it.
      "elk.hierarchyHandling": "SEPARATE_CHILDREN",
    },
    children: (childMap.get(undefined) ?? []).map(toElk),
    edges: edgesIn.get(undefined) ?? [],
  };
}

/** Flatten ELK output to parent-relative positions + final sizes (groups sized by ELK). */
export function flattenElk(laid: ElkNode): ElkLayoutResult {
  const out: ElkLayoutResult = new Map();
  const visit = (n: ElkNode) => {
    for (const c of n.children ?? []) {
      out.set(c.id, { x: c.x ?? 0, y: c.y ?? 0, width: c.width ?? WIDTH, height: c.height ?? BASE_HEIGHT });
      visit(c);
    }
  };
  visit(laid);
  return out;
}

/** Orthogonal routes (absolute canvas coordinates) for edges between siblings, keyed by routeKey. */
export function extractRoutes(laid: ElkNode): ExploreRoutes {
  const routes: ExploreRoutes = new Map();
  const visit = (n: ElkNode, ox: number, oy: number) => {
    for (const e of (n.edges ?? []) as ElkExtendedEdge[]) {
      const sec = e.sections?.[0];
      if (!sec) continue;
      const pts = [sec.startPoint, ...(sec.bendPoints ?? []), sec.endPoint].map((p) => ({ x: p.x + ox, y: p.y + oy }));
      routes.set(routeKey(e.sources[0]!, e.targets[0]!), pts);
    }
    for (const c of n.children ?? []) visit(c, ox + (c.x ?? 0), oy + (c.y ?? 0));
  };
  visit(laid, 0, 0);
  return routes;
}

export async function layoutExploreGraph(input: ExploreLayoutInput): Promise<{ positions: ElkLayoutResult; routes: ExploreRoutes }> {
  if (!input.graphNodes.length) return { positions: new Map(), routes: new Map() };
  const ELK = (await import("elkjs/lib/elk.bundled.js")).default;
  const elk = new ELK();
  const laid = await elk.layout(buildElkGraph(input));
  return { positions: flattenElk(laid), routes: extractRoutes(laid) };
}

export async function layoutExploreNodes(input: ExploreLayoutInput): Promise<ElkLayoutResult> {
  return (await layoutExploreGraph(input)).positions;
}
