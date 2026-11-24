import { describe, expect, it } from "vitest";
import { evidenceSummary, tierLabel } from "./evidence";
import type { EvidenceInfo } from "./types";

describe("evidence", () => {
  it("formats tier labels", () => {
    expect(tierLabel("high")).toBe("High");
    expect(tierLabel("unknown")).toBe("Unknown");
  });

  it("summarizes evidence", () => {
    const ev: EvidenceInfo = {
      tier: "medium",
      reason_code: "http_proxy_prefix_match",
      reason: "Matched after proxy prefix",
    };
    expect(evidenceSummary(ev)).toBe("Medium — Matched after proxy prefix");
    expect(evidenceSummary(undefined)).toBeNull();
  });
});
