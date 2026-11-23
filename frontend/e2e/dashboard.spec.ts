import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { fixtureProject, openView } from "./helpers";

const FIXTURE = process.env.E2E_FIXTURE_PATH ?? path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../backend/benchmarks/fixtures/fullstack_app");

test("ingest a local path from the dashboard", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Add a repository" }).first().click();
  const input = page.getByPlaceholder(/github\.com\/owner\/repository/);
  await input.fill("not a path");
  await expect(page.getByText("Enter a github.com repository URL or an absolute path.")).toBeVisible();
  await input.fill(FIXTURE);
  await page.getByRole("button", { name: "Analyze local project" }).click();
  await expect(page.locator(".overview-title")).toHaveText("fullstack_app", { timeout: 30_000 });
  await expect(page.locator(".react-flow__node-arch").first()).toBeVisible();
});

test("switch views from the sidebar", async ({ page }) => {
  const p = await fixtureProject(page);
  await openView(page, p.id, "layers");
  await page.getByRole("navigation").getByRole("button", { name: /API flow/ }).click();
  await expect(page.locator(".canvas-title h2")).toHaveText("API flow");
  await expect(page).toHaveURL(/v=api-flow/);
  await page.getByRole("navigation").getByRole("button", { name: /Data model/ }).click();
  await expect(page.locator(".canvas-title h2")).toHaveText("Data model");
  await expect(page.locator(".react-flow__node-arch").first()).toBeVisible();
});

test("select a node shows details and highlights it", async ({ page }) => {
  const p = await fixtureProject(page);
  await openView(page, p.id, "api-flow");
  // pin by id: React Flow may reorder node elements once one is selected
  const id = await page.locator(".react-flow__node-arch").first().getAttribute("data-id");
  const node = page.locator(`.react-flow__node[data-id="${id}"]`);
  const name = (await node.locator(".arch-node-name").innerText()).trim();
  await node.click();
  await expect(page.locator(".detail-card h2")).toHaveText(name);
  await expect(node.locator(".arch-node--selected")).toHaveCount(1);
  await expect(page).toHaveURL(/n=/);
});

test("keyboard: Enter on a focused node opens it", async ({ page }) => {
  const p = await fixtureProject(page);
  await openView(page, p.id, "api-flow");
  const id = await page.locator(".react-flow__node-arch").first().getAttribute("data-id");
  const node = page.locator(`.react-flow__node[data-id="${id}"]`);
  await node.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(".detail-card h2")).toBeVisible();
});

test("Explore: expand and collapse a package in place", async ({ page }) => {
  const p = await fixtureProject(page);
  await openView(page, p.id, "explore");
  const chevron = page.locator(".arch-chevron[aria-expanded='false']").first();
  const label = (await chevron.getAttribute("aria-label"))!.replace(/^Expand /, "");
  await chevron.click();
  const head = page.locator(".arch-group-head", { hasText: label });
  await expect(head).toBeVisible();
  await expect(page).toHaveURL(/e=/);
  // single-row title (it used to be ~70px and slid under the children)
  expect((await head.boundingBox())!.height).toBeLessThan(48);
  await page.getByRole("button", { name: `Collapse ${label}` }).click();
  await expect(head).toHaveCount(0);
});

test("⌘K finds a symbol and selects it", async ({ page }) => {
  const p = await fixtureProject(page);
  await openView(page, p.id, "layers");
  await page.keyboard.press("ControlOrMeta+k");
  const dialog = page.getByRole("dialog", { name: "Command palette" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Search").fill("list_items");
  await expect(dialog.getByRole("option").first()).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(dialog).toBeHidden();
  await expect(page.locator(".detail-card h2")).toContainText("list_items");
});

test("Ask works in tool-only mode (no LLM)", async ({ page }) => {
  const p = await fixtureProject(page);
  await openView(page, p.id, "layers");
  await page.getByRole("tab", { name: "Ask" }).click();
  await page.getByLabel("Question").fill("Which API endpoints exist?");
  await page.getByLabel("Question").press("ControlOrMeta+Enter");
  const answer = page.locator(".chat-msg.assistant, [class*='assistant']").last();
  await expect(page.getByText(/\/api\/items/).first()).toBeVisible({ timeout: 20_000 });
  await expect(answer).toBeVisible();
});

test("a pasted deep link navigates an open tab", async ({ page }) => {
  const p = await fixtureProject(page);
  await openView(page, p.id, "layers");
  await page.evaluate((id) => {
    window.location.hash = `#/p=${id}&v=er`;
  }, p.id);
  await expect(page.locator(".canvas-title h2")).toHaveText("Data model");
});

test("export menu offers every format and downloads SVG", async ({ page }) => {
  const p = await fixtureProject(page);
  await openView(page, p.id, "api-flow");
  await page.getByRole("button", { name: "Export this view" }).click();
  const menu = page.getByRole("menu", { name: "Export formats" });
  for (const f of ["SVG image", "PNG image", "Mermaid diagram", "Markdown report", "This view as JSON", "Full graph as JSON"]) {
    await expect(menu.getByRole("menuitem", { name: new RegExp(f) })).toBeEnabled();
  }
  const download = page.waitForEvent("download");
  await menu.getByRole("menuitem", { name: /SVG image/ }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("fullstack_app-api-flow.svg");
});

test("Improve tab lists refactoring suggestions that navigate to code", async ({ page }) => {
  const p = await fixtureProject(page);
  await openView(page, p.id, "layers");
  await page.getByRole("tab", { name: "Improve" }).click();
  const panel = page.locator(".suggestions, .panel-body p.muted").first();
  await expect(panel).toBeVisible();
  const first = page.locator(".suggestion .relations button").first();
  if (await first.count()) {
    const name = (await first.locator(".impact-name").innerText()).trim();
    await first.click();
    await expect(page.locator(".detail-card h2")).toContainText(name.split(".").pop()!);
  }
});
