import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const MIXED =
  process.env.E2E_MIXED_FIXTURE_PATH ??
  path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../backend/benchmarks/fixtures/mixed_monorepo");

test.describe("mixed monorepo dashboard", () => {
  test.skip(Boolean(process.env.E2E_FIXTURE_PATH), "needs local analyze API (not container-only path)");

  test("packages, Next routes, and HTTP evidence after analyze", async ({ page }) => {
    const analyze = await page.request.post("/api/projects/analyze", {
      data: { path: MIXED },
    });
    expect(analyze.ok()).toBeTruthy();
    const body = (await analyze.json()) as { project: { id: string; name: string } };
    const { id, name } = body.project;
    await page.goto(`/#/p=${id}&v=explore`);
    await page.locator(".react-flow__node-arch").first().waitFor({ timeout: 60_000 });

    await expect(page.locator(".overview-title")).toContainText(name);
    await page.keyboard.press("ControlOrMeta+k");
    const dialog = page.getByRole("dialog", { name: "Command palette" });
    await dialog.getByLabel("Search").fill("/items");
    await expect(dialog.getByRole("option").first()).toBeVisible({ timeout: 15_000 });
    await page.keyboard.press("Enter");
    await expect(page.locator(".detail-card h2")).toContainText("/items");
    await expect(page.getByText(/high|literal/i).first()).toBeVisible();
  });
});
