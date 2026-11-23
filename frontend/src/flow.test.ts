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

  it("other views: server neighbourhood ids keep on-canvas nodes beyond one hop undimmed", () => {
    const payload: GraphPayload = {
      view: "architecture",
      nodes: ["a", "b", "c"].map((id) => ({ id, label: id, node_type: "Module", properties: {} })),
      edges: [{ id: "ab", source: "a", target: "b", edge_type: "IMPORTS" }],
    };
    const flow = buildFlow(payload, { ...base, selectedId: "a", exploreNeighborIds: new Set(["c"]) });
    const state = Object.fromEntries(flow.nodes.map((n) => [n.id, n.data.state]));
    expect(state.c).toBe("default");
  });

  it("marks direction: upstream nodes/edges vs downstream, with hop counts and raised z-index", () => {
    const payload: GraphPayload = {
      view: "call-graph",
      nodes: ["caller", "sel", "callee", "deep", "x"].map((id) => ({
        id,
        label: id,
        node_type: "Function",
        properties: {},
      })),
      edges: [
        { id: "e1", source: "caller", target: "sel", edge_type: "CALLS" },
        { id: "e2", source: "sel", target: "callee", edge_type: "CALLS" },
        { id: "e3", source: "callee", target: "deep", edge_type: "CALLS" },
        { id: "e4", source: "x", target: "deep", edge_type: "CALLS" },
      ],
    };
    const one = buildFlow(payload, { ...base, selectedId: "sel" });
    const d = Object.fromEntries(one.nodes.map((n) => [n.id, n.data]));
    expect(d.caller.traceRole).toBe("up");
    expect(d.callee.traceRole).toBe("down");
    expect(d.deep.state).toBe("dim"); // 2 hops: outside the default 1-hop trace
    const e1 = one.edges.find((e) => e.id === "e1")!;
    expect(e1.data?.traceRole).toBe("up");
    expect(e1.className).toBe("edge--hl");

    const deep = buildFlow(payload, { ...base, selectedId: "sel", trace: { direction: "down", depth: Infinity } });
    const dd = Object.fromEntries(deep.nodes.map((n) => [n.id, n.data]));
    expect(dd.deep.traceRole).toBe("down");
    expect(dd.deep.traceHop).toBe(2);
    expect(dd.caller.state).toBe("dim"); // upstream excluded by direction
    expect(Number(deep.edges.find((e) => e.id === "e4")!.style?.opacity)).toBeLessThan(0.2);
  });

  it("bundles parallel edges into one line with a type breakdown", () => {
    const payload: GraphPayload = {
      view: "layers",
      nodes: ["a", "b"].map((id) => ({ id, label: id, node_type: "Module", properties: {} })),
      edges: [
        { id: "i", source: "a", target: "b", edge_type: "IMPORTS" },
        { id: "c", source: "a", target: "b", edge_type: "CALLS" },
        { id: "c2", source: "a", target: "b", edge_type: "CALLS" },
      ],
    };
    const flow = buildFlow(payload, { ...base, selectedId: null });
    expect(flow.edges).toHaveLength(1);
    expect(flow.edges[0].data?.byType).toEqual({ IMPORTS: 1, CALLS: 2 });
    expect(String(flow.edges[0].label)).toBe("calls ×2 · imports");
    expect(flow.edges[0].style?.strokeDasharray).toBeUndefined(); // drawn as the solid CALLS style
  });

  it("large graphs draw unselected edges as faint context beneath nodes", () => {
    const nodes = Array.from({ length: 200 }, (_, i) => ({
      id: `n${i}`,
      label: `n${i}`,
      node_type: "Module",
      properties: {},
    }));
    const edges = nodes.slice(1).map((n, i) => ({ id: `e${i}`, source: "n0", target: n.id, edge_type: "IMPORTS" }));
    const flow = buildFlow({ view: "layers", nodes, edges }, { ...base, selectedId: null });
    expect(flow.edges.every((e) => e.zIndex === 0 && !e.markerEnd && Number(e.style?.opacity) < 0.3)).toBe(true);
  });
});

describe("buildFlow helper text", () => {
  const base = { layers: [], hiddenLayers: new Set<string>(), filter: "", overlay: null, selectedId: null };
  const nodes = [
    {
      id: "j",
      label: "sync_orders",
      node_type: "Function",
      summary: "Saves orders",
      properties: { job: { kind: "scheduled", schedule: "0 * * * *" } },
    },
    { id: "f", label: "save", node_type: "Function", summary: "Writes Order", properties: {} },
  ];

  it("flow views put the summary on the card and make room for it", () => {
    const flow = buildFlow({ view: "jobs", nodes, edges: [] }, base);
    const job = flow.nodes.find((n) => n.id === "j")!;
    const fn = flow.nodes.find((n) => n.id === "f")!;
    expect(job.data.helper).toBe("Saves orders");
    expect(job.data.job?.schedule).toBe("0 * * * *");
    expect(job.height!).toBeGreaterThan(fn.height!); // schedule line reserved too
  });

  it("other views keep the summary as a tooltip only", () => {
    const flow = buildFlow({ view: "layers", nodes, edges: [] }, base);
    expect(flow.nodes.find((n) => n.id === "f")?.data.helper).toBeUndefined();
  });
});

describe("buildFlow focus mode and node flags", () => {
  const base = { layers: [], hiddenLayers: new Set<string>(), filter: "", overlay: null };
  const payload: GraphPayload = {
    view: "call-graph",
    nodes: [
      { id: "a", label: "a", node_type: "Function", properties: {} },
      { id: "b", label: "b", node_type: "Function", properties: {}, confidence: 0.5 },
      { id: "j", label: "nightly", node_type: "Function", properties: { job: { kind: "periodic" } } },
    ],
    edges: [],
  };

  it("does not dim unrelated nodes when focus mode is off", () => {
    const flow = buildFlow(payload, { ...base, selectedId: "a", dimUnrelated: false });
    expect(flow.nodes.find((n) => n.id === "b")?.data.state).toBe("default");
    expect(flow.nodes.find((n) => n.id === "a")?.data.state).toBe("selected");
  });

  it("dims unrelated nodes by default", () => {
    const flow = buildFlow(payload, { ...base, selectedId: "a" });
    expect(flow.nodes.find((n) => n.id === "b")?.data.state).toBe("dim");
  });

  it("flags low-confidence nodes as inferred and tints jobs", () => {
    const flow = buildFlow(payload, { ...base, selectedId: null });
    expect(flow.nodes.find((n) => n.id === "b")?.data.inferred).toBe(true);
    expect(flow.nodes.find((n) => n.id === "a")?.data.inferred).toBe(false);
    expect(flow.nodes.find((n) => n.id === "j")?.data.color).toBe("#9A5466");
  });
});

describe("zoomBucket", () => {
  it("maps zoom to semantic levels", async () => {
    const { zoomBucket } = await import("./graphTheme");
    expect([0.2, 0.49, 0.5, 0.89, 0.9, 1.5].map(zoomBucket)).toEqual(["far", "far", "mid", "mid", "near", "near"]);
  });
});
