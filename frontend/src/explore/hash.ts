/** Compact encode/decode of expanded node ids for URL hash (cap length). */

const MAX_HASH_EXPANDED_LEN = 1800;

/** Prefer shortest stable representation: comma-separated ids, capped. */
export function encodeExpandedIds(ids: string[]): string {
  const s = [...new Set(ids)].sort().join(",");
  if (s.length <= MAX_HASH_EXPANDED_LEN) return s;
  return s.slice(0, MAX_HASH_EXPANDED_LEN);
}

export function decodeExpandedIds(raw: string | undefined | null): string[] {
  if (!raw || !raw.trim()) return [];
  const parts = raw.split(",").map((p) => p.trim()).filter(Boolean);
  return [...new Set(parts)];
}
