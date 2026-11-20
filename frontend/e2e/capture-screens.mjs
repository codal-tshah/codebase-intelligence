// Capture dashboard screenshots for UI review: `node e2e/capture-screens.mjs <out-dir> [baseUrl]`.
// Uses the system Chrome (no browser download) against a running dev server + API.
import { mkdirSync } from "node:fs";
import { chromium } from "@playwright/test";

const out = process.argv[2] ?? "../docs/ui-review/after";
const only = process.env.ONLY; // capture just one named shot
const base = process.argv[3] ?? "http://localhost:5173";
mkdirSync(out, { recursive: true });

const projects = await (await fetch(`${base}/api/projects`)).json();
const byName = (n) => projects.find((p) => p.name === n || p.name.endsWith(`__${n}`));
const small = byName("fullstack_app");
const large = byName("netbox");
if (!small) throw new Error("index backend/benchmarks/fixtures/fullstack_app first");

const browser = await chromium.launch({ channel: "chrome" });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

async function shot(name, hash, after) {
  if (only && name !== only) return;
  await page.goto("about:blank");
  await page.goto(`${base}/#/${hash}`);
  await page
    .waitForSelector(".react-flow__node, .graph-overlay, .ingest-layout", { timeout: 15000 })
    .catch(() => undefined);
  await page.waitForTimeout(900);
  if (after) await after();
  await page.screenshot({ path: `${out}/${name}.png` });
  console.log("saved", name);
}

const views = [
  "layers",
  "explore",
  "architecture",
  "api-flow",
  "call-graph",
  "components",
  "er",
  "integrations",
  "jobs",
];
for (const v of views) await shot(`fullstack-${v}`, `p=${small.id}&v=${v}`);

const tab = (label) => async () => {
  await page.getByRole("tab", { name: label }).click();
  await page.waitForTimeout(700);
};
await shot("fullstack-tab-routes", `p=${small.id}&v=api-flow`, tab("Routes"));
await shot("fullstack-tab-tour", `p=${small.id}&v=layers`, tab("Tour"));
await shot("fullstack-tab-impact", `p=${small.id}&v=layers`, tab("Impact"));
await shot("fullstack-tab-path", `p=${small.id}&v=layers`, tab("Path"));
await shot("fullstack-tab-ask", `p=${small.id}&v=layers`, tab("Ask"));
await shot("tab-improve", `p=${(large ?? small).id}&v=layers`, tab("Improve"));
await shot("fullstack-select-node", `p=${small.id}&v=api-flow`, async () => {
  await page.locator(".react-flow__node-arch").first().click();
  await page.waitForTimeout(800);
});
await shot("fullstack-palette", `p=${small.id}&v=layers`, async () => {
  await page.keyboard.press("Meta+k");
  await page.keyboard.type("item");
  await page.waitForTimeout(700);
});
await shot("ingest", `p=${small.id}&v=layers`, async () => {
  await page.getByRole("button", { name: "Add a repository" }).first().click();
  await page.waitForTimeout(400);
});

if (large) {
  await shot("large-explore", `p=${large.id}&v=explore`);
  await shot("large-explore-expanded", `p=${large.id}&v=explore`, async () => {
    const chevrons = page.locator(".arch-chevron");
    for (let i = 0; i < 2 && (await chevrons.count()) > i; i++) {
      await chevrons.nth(i).dispatchEvent("click");
      await page.waitForTimeout(1800);
    }
  });
  await shot("large-explore-selected", `p=${large.id}&v=explore`, async () => {
    await page.locator(".arch-chevron").first().dispatchEvent("click");
    await page.waitForTimeout(1800);
    await page.locator(".react-flow__node-arch").nth(3).dispatchEvent("click");
    await page.waitForTimeout(1200);
  });
  await shot("large-layers", `p=${large.id}&v=layers`);
  await shot("large-api-flow", `p=${large.id}&v=api-flow`);
}

await shot("fullstack-export-menu", `p=${small.id}&v=api-flow`, async () => {
  await page.getByRole("button", { name: "Export this view" }).click();
  await page.waitForTimeout(300);
});
await shot("fullstack-explore-expanded", `p=${small.id}&v=explore`, async () => {
  const chevrons = page.locator(".arch-chevron[aria-expanded='false']");
  await chevrons.first().dispatchEvent("click");
  await page.waitForTimeout(1500);
  await page.locator(".arch-chevron[aria-expanded='false']").first().dispatchEvent("click");
  await page.waitForTimeout(1500);
});
if (large) {
  await shot("large-layers-zoomed", `p=${large.id}&v=layers`, async () => {
    for (let i = 0; i < 4; i++) {
      await page.getByRole("button", { name: /zoom in/i }).click();
      await page.waitForTimeout(200);
    }
    await page.waitForTimeout(500);
  });
}

// laptop width
await page.setViewportSize({ width: 1280, height: 720 });
await shot("laptop-1280-explore", `p=${small.id}&v=explore`);
await shot("laptop-1280-api-flow-selected", `p=${small.id}&v=api-flow`, async () => {
  await page.locator(".react-flow__node-arch").first().click();
  await page.waitForTimeout(800);
});
await browser.close();
