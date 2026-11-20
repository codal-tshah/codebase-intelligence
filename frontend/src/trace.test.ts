import { describe, expect, it } from "vitest";
import { bundleLabel, bundleParallelEdges, nodeRole, traceSelection } from "./trace";

const E = (id: string, source: string, target: string, edge_type = "CALLS") => ({ id, source, target, edge_type });

describe("traceSelection", () => {
  // a → b → S → c → d, plus a cycle S → e → S and containment that must be ignored
  const edges = [
    E("ab", "a", "b"),
    E("bS", "b", "S"),
    E("Sc", "S", "c"),
    E("cd", "c", "d"),
    E("Se", "S", "e"),
    E("eS", "e", "S"),
    E("k", "S", "kid", "CONTAINS"),
  ];

  it("depth 1 both ways = direct neighbours, split by direction", () => {
    const t = traceSelection("S", edges, { direction: "both", depth: 1 });
    expect([...t.up.keys()].sort()).toEqual(["b", "e"]);
    expect([...t.down.keys()].sort()).toEqual(["c", "e"]);
    expect(nodeRole("e", t)).toBe("both"); // cycle: depends on S and S depends on it
    expect(nodeRole("kid", t)).toBeNull(); // CONTAINS is never a dependency
    expect(t.edgeRole.get("bS")).toBe("up");
    expect(t.edgeRole.get("Sc")).toBe("down");
  });

  it("follows N hops and records the distance", () => {
    const t = traceSelection("S", edges, { direction: "up", depth: 5 });
    expect(t.up.get("a")).toBe(2);
    expect(t.down.size).toBe(0);
    expect(t.edgeRole.get("ab")).toBe("up");
  });

  it("Infinity walks the whole chain without looping forever", () => {
    const t = traceSelection("S", edges, { direction: "down", depth: Infinity });
    expect(t.down.get("d")).toBe(2);
    expect(t.edgeRole.get("eS")).toBe("down"); // edge back into S is part of the chain
  });
});

describe("bundleParallelEdges", () => {
  it("merges same-direction pairs, keeps opposite directions and CONTAINS separate", () => {
    const out = bundleParallelEdges([
      { ...E("1", "a", "b", "IMPORTS") },
      { ...E("2", "a", "b", "CALLS"), properties: { weight: 3, by_type: { CALLS: 2, READS_MODEL: 1 } } },
      E("3", "b", "a"),
      E("4", "a", "b", "CONTAINS"),
    ]);
    expect(out).toHaveLength(3);
    const ab = out.find((e) => e.id === "1")!;
    expect(ab.memberIds).toEqual(["1", "2"]);
    expect(ab.edge_type).toBe("CALLS");
    expect(ab.weight).toBe(4);
    expect(ab.byType).toEqual({ IMPORTS: 1, CALLS: 2, READS_MODEL: 1 });
    expect(bundleLabel(ab.byType, (t) => t.toLowerCase())).toBe("calls ×2 · imports · reads_model");
  });
});
