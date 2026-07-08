import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const baseURL = process.env.CATALOGFORGE_URL || "http://127.0.0.1:3000";
const output = path.resolve("../assets/screenshots");
fs.mkdirSync(output, { recursive: true });
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || "/usr/bin/chromium";
const desktop = { width: 1500, height: 980 };
const mobile = { width: 412, height: 915 };
const shots = [
  ["01-landing.png", "/", desktop],
  ["02-operations-dashboard.png", "/workspace/dashboard", desktop],
  ["03-intake-inbox.png", "/workspace/intake", desktop],
  ["04-source-intake.png", "/workspace/source-intake", desktop],
  ["05-document-intelligence.png", "/workspace/documents", desktop],
  ["06-product-master.png", "/workspace/product-master", desktop],
  ["07-product-review.png", "/workspace/review", desktop],
  ["08-data-quality.png", "/workspace/quality", desktop],
  ["09-duplicates.png", "/workspace/duplicates", desktop],
  ["10-taxonomy-governance.png", "/workspace/taxonomy", desktop],
  ["11-vendor-quality.png", "/workspace/vendors", desktop],
  ["12-publish-center.png", "/workspace/publish", desktop],
  ["13-change-sets.png", "/workspace/change-sets", desktop],
  ["14-lineage.png", "/workspace/lineage", desktop],
  ["15-reporting.png", "/workspace/reports", desktop],
  ["16-governance.png", "/workspace/governance", desktop],
  ["18-pipeline.png", "/workspace/pipeline", desktop],
  ["19-operations-console.png", "/workspace/operations", desktop],
  ["21-launch-readiness.png", "/workspace/launch", desktop],
  ["20-mobile.png", "/workspace/dashboard", mobile],
];

async function capture(name, route, viewport, afterLoad) {
  const browser = await chromium.launch({ executablePath, headless: true, args: ["--no-sandbox", "--disable-dev-shm-usage"] });
  const page = await browser.newPage({ viewport, deviceScaleFactor: 1 });
  const errors = [];
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  page.on("pageerror", (error) => errors.push(error.message));
  try {
    await page.goto(`${baseURL}${route}`, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(2600);
    if (afterLoad) await afterLoad(page);
    await page.screenshot({ path: path.join(output, name), fullPage: true });
    console.log(`captured ${name}`);
    if (errors.length) console.warn(`${name} browser warnings: ${[...new Set(errors)].join(" | ")}`);
  } finally {
    await page.close().catch(() => undefined);
    await browser.close().catch(() => undefined);
  }
}

const requested = (process.env.CAPTURE_ONLY || "").split(",").map((item) => item.trim()).filter(Boolean);
const shouldCapture = (name) => requested.length === 0 || requested.includes(name);
for (const [name, route, viewport] of shots) {
  if (shouldCapture(name)) await capture(name, route, viewport);
}
if (shouldCapture("17-command-palette.png")) {
  await capture("17-command-palette.png", "/workspace/dashboard", desktop, async (page) => {
    await page.keyboard.press("Control+K");
    await page.waitForTimeout(350);
  });
}
