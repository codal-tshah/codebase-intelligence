import { createHash } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { FIXTURE } from "./global-setup";
import { fixtureProject, openView } from "./helpers";

/** Hash every file under `root` (names + bytes) so "the source folder was never touched" is exact. */
function treeDigest(root: string): string {
  const h = createHash("sha256");
  const walk = (dir: string) => {
    for (const name of fs.readdirSync(dir).sort()) {
      const p = path.join(dir, name);
      const st = fs.statSync(p);
      if (st.isDirectory()) walk(p);
      else {
        h.update(path.relative(root, p));
        h.update(fs.readFileSync(p));
      }
    }
  };
  walk(root);
  return h.digest("hex");
}

// Against a container the server can't see this machine's temp folder.
test.describe("project lifecycle", () => {
  test.skip(Boolean(process.env.E2E_FIXTURE_PATH), "needs a server that can read the local temp folder");

  test("add a repository, explore it, then remove it without touching the source", async ({ page }) => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "ci-e2e-"));
    const src = path.join(root, "shop-e2e");
    fs.cpSync(FIXTURE, src, {
      recursive: true,
      filter: (p) => !p.includes("node_modules") && !p.includes("__pycache__"),
    });
    const before = treeDigest(src);
    try {
      await page.goto("/");
      await page
        .getByRole("button", { name: /Add a repository|Add repository/ })
        .first()
        .click();
      await page.getByPlaceholder(/github\.com\/owner\/repository/).fill(src);
      await page.getByRole("button", { name: "Analyze local project" }).click();
      await expect(page.locator(".overview-title")).toHaveText("shop-e2e", { timeout: 45_000 });

      // explore: expand a package and select a node (trace bar appears)
      await page
        .getByRole("navigation")
        .getByRole("button", { name: /Explore/ })
        .click();
      const chevron = page.locator(".arch-chevron[aria-expanded='false']").first();
      await chevron.waitFor();
      await chevron.click();
      await expect(page.locator(".arch-node--explore-group").first()).toBeVisible();
      const leaf = page.locator(".react-flow__node-arch").last();
      await leaf.click();
      await expect(page.getByRole("group", { name: "Trace dependencies of the selection" })).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(page.getByRole("group", { name: "Trace dependencies of the selection" })).toHaveCount(0);

      // remove from the projects page
      await page.getByRole("button", { name: /Switch project/ }).click();
      await page.getByRole("button", { name: "Manage projects" }).click();
      await page.getByRole("button", { name: "Remove shop-e2e" }).click();
      const dialog = page.getByRole("alertdialog");
      await expect(dialog).toContainText("never touched");
      await expect(dialog).toContainText(src);
      await dialog.getByRole("button", { name: "Remove project" }).click();
      await expect(page.getByRole("button", { name: "Remove shop-e2e" })).toHaveCount(0);

      const projects = (await (await page.request.get("/api/projects")).json()) as { name: string }[];
      expect(projects.some((p) => p.name === "shop-e2e")).toBe(false);
      expect(fs.existsSync(src)).toBe(true);
      expect(treeDigest(src)).toBe(before);
      const audit = (await (await page.request.get("/api/audit?action=project.delete&limit=5")).json()) as {
        entries: { project_name: string }[];
      };
      expect(audit.entries.some((e) => e.project_name === "shop-e2e")).toBe(true);
    } finally {
      fs.rmSync(root, { recursive: true, force: true });
    }
  });
});

async function expectInViewport(page: Page, selector: string) {
  const box = await page.locator(selector).last().boundingBox();
  const vp = page.viewportSize()!;
  expect(box).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(vp.width + 0.5);
  expect(box!.y + box!.height).toBeLessThanOrEqual(vp.height + 0.5);
}

test("every dropdown opens fully inside the window at laptop width", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  const p = await fixtureProject(page);
  await openView(page, p.id, "explore");

  for (const name of [/Open the tree to level/, /Collapse the tree to level/]) {
    const trigger = page.getByRole("button", { name });
    if (await trigger.isDisabled()) continue;
    await trigger.click();
    await expect(page.getByRole("listbox")).toBeVisible();
    await expectInViewport(page, ".popover");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("listbox")).toHaveCount(0);
    await expect(trigger).toBeFocused(); // focus returns to the trigger
  }

  await page.getByRole("button", { name: "Export this view" }).click();
  await expectInViewport(page, ".popover");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: /Switch project/ }).click();
  await expectInViewport(page, ".popover");
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: "Saved views" }).click();
  await expectInViewport(page, ".popover");
  await page.keyboard.press("Escape");

  // trace depth menu on a selected node
  await page.locator(".react-flow__node-arch").first().click();
  await page.getByRole("button", { name: /Trace depth/ }).click();
  await expectInViewport(page, ".popover");
  await page.getByRole("option", { name: "All hops" }).click();
  await expect(page.getByRole("button", { name: /Trace depth: All hops/ })).toBeVisible();
});
