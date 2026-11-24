import type { EvidenceInfo } from "./types";

export type { EvidenceInfo };

export function tierLabel(tier: string): string {
  switch (tier) {
    case "high":
      return "High";
    case "medium":
      return "Medium";
    case "low":
      return "Low";
    case "unknown":
      return "Unknown";
    default:
      return tier;
  }
}

export function evidenceSummary(ev: EvidenceInfo | undefined): string | null {
  if (!ev) return null;
  return `${tierLabel(ev.tier)} — ${ev.reason}`;
}
