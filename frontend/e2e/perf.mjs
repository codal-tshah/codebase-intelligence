// Measure dashboard responsiveness on a large indexed repo:
//   node e2e/perf.mjs [projectNameSubstring] [baseUrl]
// Prints load/expand timings, frame rate while panning, and long tasks. Uses the system Chrome.
import { chromium } from "@playwright/test";

const want = process.argv[2] ?? "netbox";
const base = process.argv[3] ?? "http://localhost:5173";
const projects = await (await fetch(`${base}/api/projects`)).json();
const p = projects.find((x) => x.name.includes(want));
if (!p) throw new Error(`no project matching ${want}`);

const browser = await chromium.launch({ channel: "chrome" });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.addInitScript(() => {
  window.__long = [];
  new PerformanceObserver((l) => l.getEntries().forEach((e) => window.__long.push(e.duration))).observe({ entryTypes: ["longtask"] });
});

async function timeView(view) {
  await page.goto("about:blank");
  const t0 = Date.now();
  await page.goto(`${base}/#/p=${p.id}&v=${view}`);
  await page.locator(".react-flow__node-arch").first().waitFor({ timeout: 60000 });
  const ms = Date.now() - t0;
  const count = await page.locator(".react-flow__node").count();
  return { view, ms, renderedNodes: count };
}

async function fps(ms = 2000) {
  const box = await page.locator(".react-flow__pane").boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  const counter = page.evaluate(
    (dur) =>
      new Promise((resolve) => {
        let frames = 0;
        let worst = 0;
        let last = performance.now();
        const start = last;
        const tick = (t) => {
          frames++;
          worst = Math.max(worst, t - last);
          last = t;
          if (t - start < dur) requestAnimationFrame(tick);
          else resolve({ fps: Math.round((frames * 1000) / (t - start)), worstFrameMs: Math.round(worst) });
        };
        requestAnimationFrame(tick);
      }),
    ms,
  );
  const steps = Math.round(ms / 16);
  for (let i = 0; i < steps; i++) await page.mouse.wheel(i % 40 < 20 ? 12 : -12, i % 30 < 15 ? 8 : -8);
  return counter;
}

const out = {};
out.explore = await timeView("explore");
await page.waitForLoadState("networkidle");
await page.evaluate(() => (window.__long = []));
const chevron = page.locator(".arch-chevron[aria-expanded='false']").first();
const label = (await chevron.getAttribute("aria-label")).replace(/^Expand /, "");
const t0 = Date.now();
await chevron.dispatchEvent("click");
await page.locator(".arch-group-head", { hasText: label }).first().waitFor({ timeout: 60000 });
out.expandMs = Date.now() - t0;
out.expandedNodes = await page.locator(".react-flow__node").count();
out.expandLongTasksMs = await page.evaluate(() => window.__long.map(Math.round));
out.explorePan = await fps();
out.layers = await timeView("layers");
await page.evaluate(() => (window.__long = []));
out.layersPan = await fps();
out.layersPanLongTasks = await page.evaluate(() => window.__long.length);
out.callGraph = await timeView("call-graph");
out.er = await timeView("er");
console.log(JSON.stringify({ project: p.name, ...out }, null, 2));
await browser.close();
