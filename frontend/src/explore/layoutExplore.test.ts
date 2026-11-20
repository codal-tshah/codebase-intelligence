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

import { GROUP_TITLE, layoutExploreNodes } from "./layoutExplore";

type Box = { x: number; y: number; width: number; height: number };
const overlaps = (a: Box, b: Box) =>
  a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;

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
    const parentOf: Record<string, string | null> = Object.fromEntries(
      nodes.map((x) => [x.id, x.properties!.parent_id as string | null]),
    );
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
      for (let i = 0; i < sibs.length; i++)
        for (let j = i + 1; j < sibs.length; j++) expect(overlaps(sibs[i], sibs[j])).toBe(false);
    }
  });
});

describe("layoutExploreNodes (wide groups)", () => {
  it("packs many unconnected children into a screen-shaped grid, not one tall column", async () => {
    const nodes: GraphNode[] = [
      { id: "pkg", label: "plugins", node_type: "Package", properties: { explore_expanded: true, parent_id: null } },
      ...Array.from(
        { length: 40 },
        (_, i): GraphNode => ({
          id: `m${i}`,
          label: `m${i}`,
          node_type: "Module",
          properties: { parent_id: "pkg" },
        }),
      ),
    ];
    const edges: GraphEdge[] = [{ id: "e", source: "m1", target: "m2", edge_type: "IMPORTS" }];
    const pos = await layoutExploreNodes({ graphNodes: nodes, graphEdges: edges });
    const group = pos.get("pkg")!;
    expect(group.height).toBeLessThan(group.width * 1.5);
    const kids = Array.from({ length: 40 }, (_, i) => pos.get(`m${i}`)!);
    for (const a of kids) {
      expect(a.x + a.width).toBeLessThanOrEqual(group.width);
      expect(a.y + a.height).toBeLessThanOrEqual(group.height);
      for (const b of kids) if (a !== b) expect(overlaps(a, b)).toBe(false);
    }
    expect(pos.get("m2")!.x).toBeGreaterThan(pos.get("m1")!.x); // edges still read left to right
  });
});

describe("Explore group title space", () => {
  it("never places a child inside the parent's title row, at any depth", async () => {
    const g = (id: string, parent: string | null, expanded: boolean): GraphNode => ({
      id,
      label: id,
      node_type: parent ? "Module" : "Package",
      properties: { parent_id: parent, explore_expanded: expanded, explore_expandable: true },
    });
    const nodes: GraphNode[] = [
      g("root", null, true),
      g("l1", "root", true),
      g("l2", "l1", true),
      g("l3", "l2", true),
      g("leaf", "l3", false),
      g("sib", "root", false),
    ];
    const pos = await layoutExploreNodes({ graphNodes: nodes, graphEdges: [] });
    for (const n of nodes) {
      const parent = n.properties?.parent_id as string | null;
      if (!parent) continue;
      const c = pos.get(n.id)!;
      const p = pos.get(parent)!;
      expect(c.y).toBeGreaterThanOrEqual(GROUP_TITLE);
      // child stays inside its parent box (positions are parent-relative)
      expect(c.x + c.width).toBeLessThanOrEqual(p.width + 0.5);
      expect(c.y + c.height).toBeLessThanOrEqual(p.height + 0.5);
    }
  });
});

describe("buildElkGraph edge placement", () => {
  it("declares each edge in the lowest common group, between that group's direct children", async () => {
    const { buildElkGraph } = await import("./layoutExplore");
    const nodes: GraphNode[] = [
      { id: "app", label: "app", node_type: "Package", properties: { explore_expanded: true, parent_id: null } },
      { id: "svc", label: "services", node_type: "Package", properties: { explore_expanded: true, parent_id: "app" } },
      { id: "s1", label: "s1", node_type: "Module", properties: { parent_id: "svc" } },
      { id: "repo", label: "repositories", node_type: "Package", properties: { parent_id: "app" } },
      { id: "tests", label: "tests", node_type: "Package", properties: { parent_id: null } },
    ];
    const edges: GraphEdge[] = [
      { id: "a", source: "s1", target: "repo", edge_type: "CALLS" }, // lifted: svc -> repo inside app
      { id: "b", source: "tests", target: "s1", edge_type: "IMPORTS" }, // lifted: tests -> app at root
      { id: "c", source: "app", target: "s1", edge_type: "CONTAINS" }, // ancestor: dropped
    ];
    const g = buildElkGraph({ graphNodes: nodes, graphEdges: edges });
    const app = g.children!.find((c) => c.id === "app")!;
    expect(app.edges!.map((e) => [e.sources[0], e.targets[0]])).toEqual([["svc", "repo"]]);
    expect(g.edges!.map((e) => [e.sources[0], e.targets[0]])).toEqual([["tests", "app"]]);
  });

  it("returns orthogonal routes for sibling edges", async () => {
    const { layoutExploreGraph, routeKey } = await import("./layoutExplore");
    const nodes: GraphNode[] = ["a", "b"].map((id) => ({
      id,
      label: id,
      node_type: "Module",
      properties: { parent_id: null },
    }));
    const { routes } = await layoutExploreGraph({
      graphNodes: nodes,
      graphEdges: [{ id: "e", source: "a", target: "b", edge_type: "CALLS" }],
    });
    const pts = routes.get(routeKey("a", "b"))!;
    expect(pts.length).toBeGreaterThanOrEqual(2);
    for (let i = 1; i < pts.length; i++) {
      const horizontal = Math.abs(pts[i].y - pts[i - 1].y) < 0.01;
      const vertical = Math.abs(pts[i].x - pts[i - 1].x) < 0.01;
      expect(horizontal || vertical).toBe(true);
    }
  });
});
