/**
 * Two people, two browser sessions, one decision (VITE_BACKEND=api): Planner A watches RT-1048's stage 7 while the
 * Approver approves it. Checks the approval goes through di-api and that Planner A's page updates from the live
 * stream without a reload, and that the instructions go out (stage 8). Changes state: reset afterwards.
 *   node scripts/smoke-approve.mjs http://localhost:5174
 */
import { chromium } from '@playwright/test';

const base = process.argv[2] || 'http://localhost:5174';
const CASE = 'RT-1048';
const browser = await chromium.launch({ channel: 'chrome', headless: true });

async function session(acct) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  page.errors = [];
  page.on('pageerror', (e) => page.errors.push(e.message));
  await page.goto(base + '/#/signin');
  await page.fill('#si-id', acct);
  await page.fill('#si-pw', 'demo');
  await page.click('button[type=submit]');
  await page.waitForTimeout(1500);
  return page;
}

const status = async (p) => (await p.innerText('#view')).match(/Case at Stage \d+ of 10 · [^\n]+/)?.[0] ?? '(none)';

const watcher = await session('planner-a');
await watcher.goto(base + `/#/product/${CASE}/stage/7`);
await watcher.waitForTimeout(2500);
console.log('planner-a sees before:', await status(watcher));

const approver = await session('approver');
await approver.goto(base + `/#/product/${CASE}/stage/7`);
await approver.waitForTimeout(2500);
const btn = approver.locator('button', { hasText: /^\s*Approve (?!and send)/ }).first();
const before = await status(watcher);
await btn.click();
await approver.waitForSelector('text=Approve and send instruction', { timeout: 10000 });
await approver.getByLabel(/I reviewed evidence snapshot/).check();
const t0 = Date.now();
await approver.click('text=Approve and send instruction');
await approver.waitForTimeout(1500);
console.log('approver toast:', (await approver.$$eval('.toast', (t) => t.map((x) => x.textContent))).join(' | ') || '(none)');

// the watcher does not reload: the stream must bring the change
let seen = '';
for (let i = 0; i < 20 && (!seen || seen === before); i++) {
  await watcher.waitForTimeout(250);
  seen = await status(watcher);
}
console.log(`planner-a sees after (no reload, ${Date.now() - t0} ms):`, seen);

await approver.goto(base + `/#/product/${CASE}/stage/8`);
await approver.waitForTimeout(3000);
const s8 = (await approver.innerText('#view')).split('\n').filter((l) => /Sterling|Depot Repair|Transportation|Manhattan|S\/4|sent|acknowledged|queued/i.test(l)).slice(0, 8);
console.log('stage 8:', s8);
console.log('page errors:', watcher.errors, approver.errors);
await browser.close();
