import { getJson, postJson } from "./api";
import type { Job } from "./types";

/** Start an index job and poll it until it finishes, reporting progress along the way. */
export async function runIndexJob(projectId: string, opts: { incremental: boolean; onProgress?: (job: Job) => void }): Promise<Job> {
  let job = await postJson<Job>(`/projects/${projectId}/index?incremental=${opts.incremental}`, {});
  opts.onProgress?.(job);
  while (job.status === "pending" || job.status === "running") {
    await new Promise((r) => setTimeout(r, 700));
    job = await getJson<Job>(`/projects/${projectId}/jobs/${job.id}`);
    opts.onProgress?.(job);
  }
  return job;
}

/** "3 min ago" style label for ISO timestamps (falls back to the date). */
export function timeAgo(iso?: string | null, now = Date.now()): string {
  if (!iso) return "never";
  const t = Date.parse(iso.endsWith("Z") || /[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
  if (Number.isNaN(t)) return iso;
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 60) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.round(h / 24);
  return d < 30 ? `${d} d ago` : new Date(t).toLocaleDateString();
}
