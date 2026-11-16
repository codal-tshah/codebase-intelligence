import { describe, expect, it } from "vitest";
import { createExploreState, exploreReducer, expandedKey } from "./useExploreState";

describe("exploreReducer", () => {
  it("toggle adds id and records history for back", () => {
    let s = createExploreState([]);
    s = exploreReducer(s, { type: "toggle", id: "a" });
    expect(s.expanded).toEqual(["a"]);
    s = exploreReducer(s, { type: "back" });
    expect(s.expanded).toEqual([]);
  });

  it("clearExplore resets without growing history", () => {
    let s = createExploreState(["x"]);
    s = exploreReducer(s, { type: "toggle", id: "y" });
    s = exploreReducer(s, { type: "clearExplore" });
    expect(s.expanded).toEqual([]);
    expect(s.history).toEqual([]);
  });

  it("collapseToLevel trims expanded and offsets", () => {
    let s = createExploreState(["a", "b"], { a: 80 });
    s = exploreReducer(s, { type: "collapseToLevel", level: 1, orderedAncestors: ["a", "b"] });
    expect(s.expanded).toEqual(["a"]);
    expect(s.childOffsets).toEqual({ a: 80 });
  });
});

describe("expandedKey", () => {
  it("sorts ids", () => {
    expect(expandedKey(["b", "a"])).toBe("a,b");
  });
});
