import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Make sure the fullstack fixture is indexed before the specs run (idempotent, ~1s).
 * Against a container, set E2E_FIXTURE_PATH to the path the server sees (e.g. /repos/fullstack_app).
 */
export const FIXTURE =
  process.env.E2E_FIXTURE_PATH ??
  path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../backend/benchmarks/fixtures/fullstack_app");

export default async function globalSetup() {
  const base = process.env.E2E_BASE_URL ?? "http://localhost:5173";
  const res = await fetch(`${base}/api/projects/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: FIXTURE }),
  });
  if (!res.ok) throw new Error(`could not index the fixture: ${res.status} ${await res.text()}`);
}
