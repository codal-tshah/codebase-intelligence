import { describe, expect, it } from "vitest";
import { layoutByLayer, layoutNodes } from "./layout";

describe("layout", () => {
  it("wraps a hub's 60 spokes into several columns instead of one tall column", () => {
    const nodes = [{ id: "hub", width: 200, height: 70 }, ...Array.from({ length: 60 }, (_, i) => ({ id: `s${i}`, width: 200, height: 70 }))];
    const edges = nodes.slice(1).map((n) => ({ source: n.id, target: "hub" }));
    const pos = layoutNodes(nodes, edges);
    const spokeXs = new Set(nodes.slice(1).map((n) => pos.get(n.id)!.x));
    expect(spokeXs.size).toBeGreaterThanOrEqual(4);
    const maxY = Math.max(...nodes.map((n) => pos.get(n.id)!.y));
    expect(maxY).toBeLessThan(15 * 90);
    // hub stays to the right of all spokes
    expect(pos.get("hub")!.x).toBeGreaterThan(Math.max(...spokeXs));
  });

  it("layers view puts each layer in its own ordered column", () => {
    const n = (id: string, layer: string, rank = 0) => ({ id, width: 100, height: 50, layer, rank });
    const { positions, lanes } = layoutByLayer([n("t", "test"), n("a", "api", 2), n("d", "data"), n("a2", "api", 5)]);
    expect(lanes.map((l) => l.id)).toEqual(["api", "data", "test"]);
    expect(positions.get("a2")!.y).toBeLessThan(positions.get("a")!.y); // higher rank first
    expect(positions.get("a")!.x).toBeLessThan(positions.get("d")!.x);
  });
});
