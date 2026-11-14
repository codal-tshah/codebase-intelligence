/** Compact encode/decode of expanded node ids for URL hash (cap length). */

const MAX_HASH_EXPANDED_LEN = 1800;

/** Prefer shortest stable representation: comma-separated ids, capped. */
export function encodeExpandedIds(ids: string[]): string {
  const s = [...new Set(ids)].sort().join(",");
  if (s.length <= MAX_HASH_EXPANDED_LEN) return s;
  // Cut at an id boundary so the last id is never a truncated (wrong) id. Hash only: API
  // requests send the full list.
  const cut = s.slice(0, MAX_HASH_EXPANDED_LEN + 1).lastIndexOf(",");
  return cut > 0 ? s.slice(0, cut) : "";
}

export function decodeExpandedIds(raw: string | undefined | null): string[] {
  if (!raw || !raw.trim()) return [];
  const parts = raw.split(",").map((p) => p.trim()).filter(Boolean);
  return [...new Set(parts)];
}
