import { describe, expect, it } from "vitest";
import { computePopoverPosition } from "./Popover";
import { orthogonalPath } from "./RoutedEdge";
import { levelOptions, ALL_LEVELS } from "../explore/ExploreToolbar";
import { timeAgo } from "../indexJobs";

const vp = { width: 1280, height: 800 };
const anchor = (top: number, left: number, w = 80, h = 30) => ({ top, bottom: top + h, left, right: left + w, width: w });

describe("computePopoverPosition", () => {
  it("opens below the trigger when there is room", () => {
    const p = computePopoverPosition(anchor(100, 200), { width: 160, height: 300 }, vp);
    expect(p).toMatchObject({ top: 134, left: 200, flipped: false });
  });

  it("flips above near the bottom edge and caps the height to the free space", () => {
    const p = computePopoverPosition(anchor(700, 200), { width: 160, height: 400 }, vp);
    expect(p.flipped).toBe(true);
    expect(p.top).toBeGreaterThanOrEqual(8);
    expect(p.maxHeight).toBeLessThanOrEqual(700 - 4 - 8);
  });

  it("shifts left so a wide menu never leaves the viewport (bottom-end aligns right edges)", () => {
    const p = computePopoverPosition(anchor(40, 1240, 32), { width: 248, height: 200 }, vp, "bottom-start");
    expect(p.left + 248).toBeLessThanOrEqual(1280 - 8);
    const end = computePopoverPosition(anchor(40, 1200, 32), { width: 248, height: 200 }, vp, "bottom-end");
    expect(end.left).toBe(1232 - 248);
  });
});

describe("levelOptions", () => {
  it("offers 1..maxDepth (capped at 10) plus All", () => {
    expect(levelOptions(6, { includeAll: true }).map((o) => o.value)).toEqual([1, 2, 3, 4, 5, 6, ALL_LEVELS]);
    expect(levelOptions(14, { includeAll: false })).toHaveLength(10);
  });
});

describe("orthogonalPath", () => {
  it("snaps ELK's route to the handles and keeps segments axis-aligned", () => {
    const pts = [
      { x: 0, y: 12 },
      { x: 40, y: 12 },
      { x: 40, y: 90 },
      { x: 100, y: 90 },
    ];
    const { path } = orthogonalPath(pts, 0, 10, 100, 95, 0);
    expect(path).toBe("M0,10 L40,10 Q40,10 40,10 L40,95 Q40,95 40,95 L100,95");
  });

  it("builds an S-route when ELK gave a straight line but the handles differ", () => {
    const { path } = orthogonalPath([{ x: 0, y: 0 }, { x: 100, y: 0 }], 0, 0, 100, 40, 0);
    expect(path.startsWith("M0,0 L50,0")).toBe(true);
    expect(path.endsWith("L100,40")).toBe(true);
  });
});

describe("timeAgo", () => {
  it("formats recent times and treats naive ISO strings as UTC", () => {
    const now = Date.parse("2026-11-16T12:00:00Z");
    expect(timeAgo("2026-11-16T11:58:00", now)).toBe("2 min ago");
    expect(timeAgo("2026-11-16T09:00:00+00:00", now)).toBe("3 h ago");
    expect(timeAgo(null, now)).toBe("never");
  });
});
