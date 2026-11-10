import { describe, expect, it } from "vitest";
import { buildFlow } from "./flow";
import type { GraphPayload } from "./types";

describe("buildFlow explore dimming", () => {
  const payload: GraphPayload = {
    view: "explore",
    nodes: [
      { id: "a", label: "a", node_type: "Package", properties: {} },
      { id: "b", label: "b", node_type: "Package", properties: {} },
    ],
    edges: [],
  };
  const base = { layers: [], hiddenLayers: new Set<string>(), filter: "", overlay: null };

  it("does not dim the canvas when the selected node is not visible", () => {
    const flow = buildFlow(payload, { ...base, selectedId: "hidden", exploreNeighborIds: new Set(["x"]) });
    expect(flow.nodes.every((n) => n.data.state !== "dim")).toBe(true);
  });

  it("dims non-neighbours when the selected node is visible", () => {
    const flow = buildFlow(payload, { ...base, selectedId: "a", exploreNeighborIds: new Set<string>() });
    expect(flow.nodes.find((n) => n.id === "b")?.data.state).toBe("dim");
  });
});

describe("buildFlow selection highlight", () => {
  const base = { layers: [], hiddenLayers: new Set<string>(), filter: "", overlay: null };

  it("Explore: selecting a group keeps its subtree highlighted and hides nested CONTAINS edges", () => {
    const payload: GraphPayload = {
      view: "explore",
      nodes: [
        { id: "core", label: "core", node_type: "Package", properties: { explore_expanded: true, parent_id: null } },
        { id: "mod", label: "mod", node_type: "Module", properties: { explore_expanded: true, parent_id: "core" } },
        { id: "fn", label: "fn", node_type: "Function", properties: { parent_id: "mod" } },
        { id: "other", label: "other", node_type: "Package", properties: { parent_id: null } },
      ],
      edges: [
        { id: "c1", source: "core", target: "mod", edge_type: "CONTAINS" },
        { id: "d1", source: "fn", target: "other", edge_type: "CALLS" },
      ],
    };
    const flow = buildFlow(payload, { ...base, selectedId: "core", exploreNeighborIds: new Set() });
    const state = Object.fromEntries(flow.nodes.map((n) => [n.id, n.data.state]));
    expect(state.core).toBe("selected");
    expect(state.mod).not.toBe("dim");
    expect(state.fn).not.toBe("dim");
    expect(state.other).toBe("dim");
    expect(flow.edges.some((e) => e.id === "c1")).toBe(false);
    // parents are emitted before children (React Flow sub-flow requirement)
    const order = flow.nodes.map((n) => n.id);
    expect(order.indexOf("core")).toBeLessThan(order.indexOf("mod"));
    expect(order.indexOf("mod")).toBeLessThan(order.indexOf("fn"));
  });

  it("other views: selecting a node highlights its direct neighbours and incident edges", () => {
    const payload: GraphPayload = {
      view: "layers",
      nodes: ["a", "b", "c"].map((id) => ({ id, label: id, node_type: "Module", properties: {} })),
      edges: [
        { id: "ab", source: "a", target: "b", edge_type: "IMPORTS" },
        { id: "bc", source: "b", target: "c", edge_type: "IMPORTS" },
      ],
    };
    const flow = buildFlow(payload, { ...base, selectedId: "a" });
    const state = Object.fromEntries(flow.nodes.map((n) => [n.id, n.data.state]));
    expect(state).toMatchObject({ a: "selected", b: "overlay", c: "dim" });
    const ab = flow.edges.find((e) => e.id === "ab")!;
    const bc = flow.edges.find((e) => e.id === "bc")!;
    expect(Number(ab.style?.opacity)).toBe(1);
    expect(Number(bc.style?.opacity)).toBeLessThan(0.2);
    expect(ab.label).toBeTruthy();
  });
});
