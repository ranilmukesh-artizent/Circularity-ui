/**
 * Plan 10 T5 smoke (read-only: it only opens and reads, it never accepts or rejects):
 *   as approver, Ctrl+J on Home shows "Waiting for you (n)" equal to Home's "Proposals for you" card count, and
 *   "View the run" opens the run drawer on the Agents page.
 *
 *   node scripts/smoke-a10-t5.mjs [baseUrl]
 *
 * Needs the dock (T1) for the first check. With no proposal pending, n is 0 and the card is not drawn.
 */
import { chromium } from '@playwright/test';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await (await browser.newContext()).newPage();
let failures = 0;
const check = (ok, what) => {
  console.log((ok ? 'PASS ' : 'FAIL ') + what);
  if (!ok) failures++;
};

await page.goto(base + '/#/signin');
await page.fill('#si-id', 'approver');
await page.fill('#si-pw', 'demo');
await page.click('button[type=submit]');
await page.waitForSelector('.sidebar, nav, #view', { timeout: 15000 });
await page.goto(base + '/#/home');
await page.waitForTimeout(1500);

const card = await page.locator('#frProps li').count();
await page.keyboard.press('Control+j');
const strip = page.locator('.as-waiting summary');
await strip.waitFor({ timeout: 8000 });
const n = Number(((await strip.textContent()) ?? '').match(/\((\d+)\)/)?.[1] ?? -1);
check(n === card, `Waiting for you (${n}) equals Home's card count (${card})`);

if (n > 0) {
  const link = page.locator('.as-waiting a:has-text("View the run")').first();
  if (await link.count()) {
    await link.click();
    await page.waitForSelector('.drawer, [role=dialog]', { timeout: 8000 }).catch(() => {});
    check(/#\/agents\?run=/.test(page.url()), 'View the run goes to the Agents page with ?run=');
    check((await page.locator('.runview').count()) > 0, 'the run drawer shows the run');
  }
} else console.log('NOTE no proposal pending: View the run not exercised');

await browser.close();
process.exit(failures ? 1 : 0);
