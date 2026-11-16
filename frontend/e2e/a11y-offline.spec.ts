import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { fixtureProject, openView } from "./helpers";

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

async function axe(page: import("@playwright/test").Page) {
  const result = await new AxeBuilder({ page })
    .withTags(TAGS)
    // The minimap is a decorative, pointer-only overview (aria-hidden alternatives exist: Controls + keyboard).
    .exclude(".react-flow__minimap")
    .analyze();
  return result.violations.map((v) => `${v.id} (${v.impact}): ${v.nodes.length} × ${v.nodes[0]?.target.join(" ")}`);
}

for (const view of ["layers", "explore", "api-flow"]) {
  test(`axe: no WCAG A/AA violations on ${view}`, async ({ page }) => {
    const p = await fixtureProject(page);
    await openView(page, p.id, view);
    await page.locator(".react-flow__node-arch").first().click();
    // the neighbourhood fetch restyles nodes with a 200ms fade; measure after it settles
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(400);
    expect(await axe(page)).toEqual([]);
  });
}

test("axe: ingest screen", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Add a repository" }).first().click();
  expect(await axe(page)).toEqual([]);
});

test("axe: Ask panel and command palette", async ({ page }) => {
  const p = await fixtureProject(page);
  await openView(page, p.id, "layers");
  await page.getByRole("tab", { name: "Ask" }).click();
  expect(await axe(page)).toEqual([]);
  await page.getByRole("tab", { name: "Improve" }).click();
  await page.locator(".suggestions, .panel-body p.muted").first().waitFor();
  expect(await axe(page)).toEqual([]);
  await page.keyboard.press("ControlOrMeta+k");
  await expect(page.getByRole("dialog", { name: "Command palette" })).toBeVisible();
  await page.waitForTimeout(400); // let the open animation finish (axe measures mid-fade opacity)
  expect(await axe(page)).toEqual([]);
});

test("offline: no request leaves localhost and the bundled fonts load", async ({ page }) => {
  const external: string[] = [];
  await page.route("**/*", (route) => {
    const host = new URL(route.request().url()).hostname;
    if (host === "localhost" || host === "127.0.0.1") return route.continue();
    external.push(route.request().url());
    return route.abort();
  });
  const p = await fixtureProject(page);
  await openView(page, p.id, "layers");
  await page.evaluate(() => document.fonts.ready);
  const fonts = await page.evaluate(() => ({
    ui: document.fonts.check('500 14px "Schibsted Grotesk"'),
    mono: document.fonts.check('400 12px "IBM Plex Mono"'),
    display: document.fonts.check('400 26px "Newsreader Variable"'),
  }));
  expect(external).toEqual([]);
  expect(fonts).toEqual({ ui: true, mono: true, display: true });
});
