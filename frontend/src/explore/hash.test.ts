import { describe, expect, it } from "vitest";
import { decodeExpandedIds, encodeExpandedIds } from "./hash";

describe("explore hash", () => {
  it("round-trips expanded ids", () => {
    const ids = ["a", "b", "c"];
    expect(decodeExpandedIds(encodeExpandedIds(ids))).toEqual(ids);
  });

  it("dedupes and caps length", () => {
    const long = Array.from({ length: 100 }, (_, i) => `n${i}`);
    const enc = encodeExpandedIds([...long, ...long]);
    expect(enc.length).toBeLessThanOrEqual(1800);
    expect(decodeExpandedIds(enc).length).toBeGreaterThan(0);
  });
});
