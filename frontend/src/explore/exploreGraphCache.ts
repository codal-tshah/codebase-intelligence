/** LRU cache for explore graph payloads (instant back/forward). */

import type { GraphPayload } from "../types";

const DEFAULT_CAP = 20;

type Entry = { payload: GraphPayload; at: number };

export class ExploreGraphCache {
  private map = new Map<string, Entry>();
  private cap: number;

  constructor(cap = DEFAULT_CAP) {
    this.cap = cap;
  }

  get(key: string): GraphPayload | undefined {
    const e = this.map.get(key);
    if (!e) return undefined;
    e.at = Date.now();
    this.map.set(key, e);
    return e.payload;
  }

  set(key: string, payload: GraphPayload): void {
    this.map.set(key, { payload, at: Date.now() });
    while (this.map.size > this.cap) {
      let oldestK: string | null = null;
      let oldestT = Infinity;
      for (const [k, v] of this.map) {
        if (v.at < oldestT) {
          oldestT = v.at;
          oldestK = k;
        }
      }
      if (oldestK !== null) this.map.delete(oldestK);
    }
  }
}

export function exploreCacheKey(
  expandedSorted: string[],
  childOffsets: Record<string, number>,
): string {
  const off =
    Object.keys(childOffsets).length === 0
      ? ""
      : Object.entries(childOffsets)
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([k, v]) => `${k}=${v}`)
          .join("&");
  return `${expandedSorted.join(",")}|${off}`;
}
