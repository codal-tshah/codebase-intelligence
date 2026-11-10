import { describe, expect, it } from "vitest";
import { buildExploreLayoutModel } from "./layoutExplore";
import type { GraphEdge, GraphNode } from "../types";

describe("buildExploreLayoutModel", () => {
  it("marks expanded parent as group when child has parent_id", () => {
    const nodes: GraphNode[] = [
      {
        id: "pkg",
        label: "app",
        node_type: "Package",
        properties: { explore_expanded: true, parent_id: null },
      },
      {
        id: "mod",
        label: "views",
        node_type: "Module",
        properties: { explore_expanded: false, parent_id: "pkg" },
      },
    ];
    const edges: GraphEdge[] = [];
    const { layoutNodes } = buildExploreLayoutModel({ graphNodes: nodes, graphEdges: edges });
    const pkg = layoutNodes.find((n) => n.id === "pkg");
    expect(pkg?.isGroup).toBe(true);
    expect(pkg?.parentId).toBeUndefined();
    expect(layoutNodes.find((n) => n.id === "mod")?.parentId).toBe("pkg");
  });
});

import { layoutExploreNodes } from "./layoutExplore";

type Box = { x: number; y: number; width: number; height: number };
const overlaps = (a: Box, b: Box) => a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;

describe("layoutExploreNodes (nested ELK)", () => {
  // 3 levels: two root packages; pkgA expanded -> modA1 (expanded -> fnA, fnB), modA2; pkgB collapsed.
  const n = (id: string, parent: string | null, expanded = false): GraphNode => ({
    id,
    label: id,
    node_type: parent ? "Module" : "Package",
    properties: { explore_expanded: expanded, parent_id: parent },
  });
  const nodes: GraphNode[] = [
    n("pkgA", null, true),
    n("pkgB", null),
    n("modA1", "pkgA", true),
    n("modA2", "pkgA"),
    n("fnA", "modA1"),
    n("fnB", "modA1"),
  ];
  const edges: GraphEdge[] = [
    { id: "c1", source: "pkgA", target: "modA1", edge_type: "CONTAINS" },
    { id: "d1", source: "fnA", target: "pkgB", edge_type: "CALLS" },
    { id: "d2", source: "modA2", target: "fnB", edge_type: "IMPORTS" },
  ];

  it("keeps children inside parents and siblings apart at every depth", async () => {
    const pos = await layoutExploreNodes({ graphNodes: nodes, graphEdges: edges });
    const parentOf: Record<string, string | null> = Object.fromEntries(nodes.map((x) => [x.id, x.properties!.parent_id as string | null]));
    for (const child of nodes) {
      const p = parentOf[child.id];
      const c = pos.get(child.id)!;
      expect(c).toBeTruthy();
      if (p) {
        const parent = pos.get(p)!;
        // child coordinates are parent-relative
        expect(c.x).toBeGreaterThanOrEqual(0);
        expect(c.y).toBeGreaterThanOrEqual(0);
        expect(c.x + c.width).toBeLessThanOrEqual(parent.width + 0.5);
        expect(c.y + c.height).toBeLessThanOrEqual(parent.height + 0.5);
      }
    }
    const siblingsOf = (p: string | null) => nodes.filter((x) => parentOf[x.id] === p).map((x) => pos.get(x.id)!);
    for (const p of [null, "pkgA", "modA1"]) {
      const sibs = siblingsOf(p);
      for (let i = 0; i < sibs.length; i++) for (let j = i + 1; j < sibs.length; j++) expect(overlaps(sibs[i]!, sibs[j]!)).toBe(false);
    }
  });
});
