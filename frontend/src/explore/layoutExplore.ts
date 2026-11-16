import type { GraphEdge, GraphNode } from "../types";

const WIDTH = 216;
const BASE_HEIGHT = 78;
const GROUP_TITLE = 40;
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

/** True when `a` is `b` or an ancestor of `b` (via parentId). */
function isAncestorOrSelf(a: string, b: string, parentOf: Map<string, string | undefined>): boolean {
  let cur: string | undefined = b;
  let guard = 0;
  while (cur && guard++ < 64) {
    if (cur === a) return true;
    cur = parentOf.get(cur);
  }
  return false;
}

/**
 * Nested ELK model. Groups are NOT given a fixed size: ELK sizes each compound node to fit
 * its laid-out children (with a minimum), so children never spill out and siblings never
 * overlap. Child coordinates come back relative to their parent, which is exactly what
 * React Flow expects for nodes with `parentId`.
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

  const toElk = (n: ExploreLayoutNode): ElkNode => {
    const kids = childMap.get(n.id) ?? [];
    if (n.isGroup && kids.length) {
      return {
        id: n.id,
        layoutOptions: {
          "elk.padding": `[top=${GROUP_TITLE},left=${GROUP_PAD},bottom=${GROUP_PAD},right=${GROUP_PAD}]`,
          "elk.nodeSize.constraints": "MINIMUM_SIZE",
          "elk.nodeSize.minimum": `(${GROUP_MIN_W}, ${GROUP_TITLE + GROUP_PAD * 2 + 40})`,
        },
        children: kids.map(toElk),
      };
    }
    return { id: n.id, width: n.width, height: n.height };
  };

  // Edges between a node and its own ancestor (e.g. CONTAINS to a nested child) break
  // hierarchical layout and are already expressed by nesting, so they are left out.
  const edges: ElkExtendedEdge[] = layoutEdges
    .filter((e) => !isAncestorOrSelf(e.source, e.target, parentOf) && !isAncestorOrSelf(e.target, e.source, parentOf))
    .map((e) => ({ id: e.id, sources: [e.source], targets: [e.target] }));

  return {
    id: "explore-root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "RIGHT",
      "elk.spacing.nodeNode": "28",
      "elk.layered.spacing.nodeNodeBetweenLayers": "64",
      "elk.spacing.componentComponent": "40",
      "elk.hierarchyHandling": "INCLUDE_CHILDREN",
      "elk.edgeRouting": "ORTHOGONAL",
      "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
    },
    children: (childMap.get(undefined) ?? []).map(toElk),
    edges,
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

export async function layoutExploreNodes(
  input: ExploreLayoutInput,
  // Kept for call-site compatibility. Re-seeding old positions after a sibling grows is what
  // caused overlapping boxes, so positions always come from a fresh ELK pass now.
  _prevPositions?: Map<string, { x: number; y: number }>,
): Promise<ElkLayoutResult> {
  void _prevPositions;
  if (!input.graphNodes.length) return new Map();
  const ELK = (await import("elkjs/lib/elk.bundled.js")).default;
  const elk = new ELK();
  return flattenElk(await elk.layout(buildElkGraph(input)));
}
