import type { Page } from "@playwright/test";

export type Project = { id: string; name: string };

export async function fixtureProject(page: Page): Promise<Project> {
  const res = await page.request.get("/api/projects");
  const projects = (await res.json()) as Project[];
  const p = projects.find((x) => x.name === "fullstack_app");
  if (!p) throw new Error("fullstack_app fixture is not indexed");
  return p;
}

/** Open the dashboard on a project/view and wait for the diagram. */
export async function openView(page: Page, projectId: string, view: string) {
  await page.goto(`/#/p=${projectId}&v=${view}`);
  await page.locator(".react-flow__node-arch").first().waitFor();
}
