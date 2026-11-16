import { describe, expect, it } from "vitest";
import type { Edge, Node } from "@xyflow/react";
import type { ArchNodeData } from "../flow";
import type { GraphPayload } from "../types";
import { absoluteBoxes, safeFilename, toMarkdown, toMermaid, toSvg } from "./exportView";

const payload: GraphPayload = {
  view: "api-flow",
  nodes: [
    { id: "ep:/api/items", label: 'GET "/api/items" <x>', node_type: "Endpoint", layer: "api", source_path: "app/api.py" },
    { id: "m|Item", label: "Item|table", node_type: "Model", layer: "data" },
  ],
  edges: [
    { id: "e1", source: "ep:/api/items", target: "m|Item", edge_type: "READS_MODEL" },
    { id: "e2", source: "ep:/api/items", target: "m|Item", edge_type: "CALLS", confidence: 0.4 },
  ],
};

describe("toMermaid", () => {
  it("renumbers ids and escapes labels", () => {
    const out = toMermaid(payload);
    expect(out.startsWith("flowchart LR")).toBe(true);
    expect(out).toContain('n0["GET #quot;/api/items#quot; #lt;x#gt;');
    expect(out).toContain('n1[("Item|table');
    expect(out).toContain("n0 -->|reads| n1");
    expect(out).toContain("n0 -.->|calls| n1"); // low confidence is dashed
    expect(out).not.toContain("ep:/api/items");
  });
});

describe("toMarkdown", () => {
  it("escapes table pipes and embeds the mermaid block", () => {
    const md = toMarkdown(payload, { project: "shop", view: "API flow" });
    expect(md).toContain("# shop — API flow");
    expect(md).toContain("```mermaid");
    expect(md).toContain("Item\\|table");
    expect(md).toContain("| 40% |");
  });
});

describe("toSvg", () => {
  const node = (id: string, x: number, y: number, extra: Partial<Node<ArchNodeData>> = {}): Node<ArchNodeData> => ({
    id,
    type: "arch",
    position: { x, y },
    width: 200,
    height: 80,
    data: { label: `<${id}>`, nodeType: "Module", color: "#55708F", fanIn: 0, fanOut: 0, state: "default" },
    ...extra,
  });

  it("resolves parent-relative positions", () => {
    const boxes = absoluteBoxes([node("p", 100, 50), node("c", 10, 60, { parentId: "p" })]);
    expect(boxes.get("c")).toMatchObject({ x: 110, y: 110 });
  });

  it("escapes labels and draws every node and edge", () => {
    const edges: Edge[] = [{ id: "e", source: "a", target: "b", style: { stroke: "#123456" } }];
    const svg = toSvg([node("a", 0, 0), node("b", 300, 0)], edges);
    expect(svg).toContain("&lt;a&gt;");
    expect(svg).not.toContain("<a>");
    expect(svg.match(/<g>/g)?.length).toBe(2);
    expect(svg).toContain('stroke="#123456"');
  });
});

describe("safeFilename", () => {
  it("strips unsafe characters", () => {
    expect(safeFilename("my repo/../x", "API flow")).toBe("my-repo-..-x-api-flow");
  });
});
