import { expect, test } from "@playwright/test";
import { fixtureProject, openView } from "./helpers";

test("api.listItems inspector shows HTTP evidence and source", async ({ page }) => {
  const p = await fixtureProject(page);
  await openView(page, p.id, "api-flow");
  await page.keyboard.press("ControlOrMeta+k");
  const dialog = page.getByRole("dialog", { name: "Command palette" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Search").fill("api.listItems");
  await expect(dialog.getByRole("option").first()).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(dialog).toBeHidden();
  await expect(page.locator(".detail-card h2")).toContainText("listItems");

  const evidence = page.locator(".detail-card .evidence-line").first();
  await expect(evidence).toBeVisible();
  await expect(evidence).toContainText(/high/i);
  await expect(evidence).toContainText(/structural|parsed|source/i);

  await expect(page.getByText("HTTP requests")).toBeVisible();
  const httpSection = page.locator(".relations", { has: page.getByText("HTTP requests") });
  await expect(httpSection.getByText(/High/i).first()).toBeVisible();
  await expect(httpSection.locator(".mono")).toContainText("/api/items");

  await expect(page.locator(".code-block .code-path, .file-path")).toContainText(/client\.ts/i);
});
