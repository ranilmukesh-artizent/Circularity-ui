/**
 * RT-1048 end to end in the browser, against the running stack (B17c). People act in their own sessions; after the
 * approval only source-sim's simulated clock moves (the worker sends the instructions, the mocks' events acknowledge
 * them). A watcher session follows along without reloading. Changes state: run scripts/dev/reset.sh before and after,
 * and wait for the worker's post-reset sync backlog to drain first (the queue has no priorities yet: plan 02), or the
 * first instruction waits behind ~20 source syncs.
 *   node scripts/smoke-rt1048.mjs http://localhost:5173
 */
import { chromium } from '@playwright/test';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const SIM = process.env.SIM_URL || `http://localhost:${process.env.SIM_PORT || 8100}`;
const CASE = 'RT-1048';
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const errors = [];

async function session(acct) {
  const page = await (await browser.newContext()).newPage();
  page.on('pageerror', (e) => errors.push(acct + ': ' + e.message));
  await page.goto(base + '/#/signin');
  await page.fill('#si-id', acct);
  await page.fill('#si-pw', 'demo');
  await page.click('button[type=submit]');
  await page.waitForTimeout(1500);
  return page;
}
// the stage page takes several seconds to render after a sign-in or a reset: wait for its stage line, not a fixed 2.5 s
const go = (p, n) =>
  p
    .goto(`${base}/#/product/${CASE}/stage/${n}`)
    .then(() => p.waitForFunction(() => /Case at Stage \d+ of 10|Every stage is done/.test(document.querySelector('#view')?.innerText || ''), null, { timeout: 45000 }))
    .catch(() => {})
    .then(() => p.waitForTimeout(1500));
const stage = async (p) => {
  const t = await p.innerText('#view');
  if (/Every stage is done/.test(t)) return '10 · Every stage is done';
  return t.match(/Case at Stage (\d+) of 10 · ([^\n]+)/)?.slice(1).join(' · ') ?? '(none)';
};
const say = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

const watcher = await session('planner-a');
await go(watcher, 8);
say('watcher (planner-a) starts at', await stage(watcher));

// 1. Planner A submits
const planner = await session('planner-a');
await go(planner, 7);
const submit = planner.locator('button', { hasText: `Submit ${CASE} for review` });
if (await submit.count()) {
  await submit.first().click();
  await planner.waitForTimeout(1500);
  say('planner-a submitted');
} else say('planner-a: no submit button (already submitted)');

// 2. The Approver approves (the approval card needs the evidence review ticked)
const approver = await session('approver');
await go(approver, 7);
await approver.locator('button', { hasText: /^\s*Approve (?!and send)/ }).first().click();
await approver.getByLabel(/I reviewed evidence snapshot/).check();
await approver.click('text=Approve and send instruction');
await approver.waitForTimeout(1500);
say('approver:', (await approver.$$eval('.toast', (t) => t.map((x) => x.textContent))).join(' | '));

// 3. Only time moves: advance the simulated clock until the case closes (stage 9 waits for Finance)
let s = '';
for (let i = 0; i < 40; i++) {
  s = await stage(watcher);
  if (/^(9|10) /.test(s)) break;
  const r = await fetch(SIM + '/_sim/clock/advance', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ hours: 3 }) });
  if (!r.ok) throw new Error('clock advance failed: ' + r.status);
  await watcher.waitForTimeout(3000);
  if (i % 3 === 0) say(`+${(i + 1) * 3} h, watcher sees`, await stage(watcher));
}
say('watcher (no reload) sees', s);

// 4. Finance confirms the outcome
const finance = await session('finance');
await go(finance, 9);
const confirm = finance.locator('button', { hasText: 'Confirm the outcome' });
if (!(await confirm.count())) throw new Error('Finance has no "Confirm the outcome" button; stage is ' + (await stage(finance)));
await confirm.first().click();
await finance.waitForTimeout(2000);
say('finance:', (await finance.$$eval('.toast', (t) => t.map((x) => x.textContent))).join(' | '));
await go(finance, 10);
// the case closes on the server at once; the pages follow through the action's refresh and the live stream. Poll
// (up to 20 s) rather than read once, and say how long each took, so a slow refresh and a missing one are told apart.
const until10 = async (p, who) => {
  const t0 = Date.now();
  for (;;) {
    const st = await stage(p);
    if (/^10 · Every stage is done/.test(st) || Date.now() - t0 > 20000) {
      say(`${who} sees after ${((Date.now() - t0) / 1000).toFixed(1)} s:`, st);
      return /^10 · Every stage is done/.test(st);
    }
    await p.waitForTimeout(500);
  }
};
await until10(finance, 'stage 10 for finance');
const done = await until10(watcher, 'watcher (no reload)');
say('page errors:', errors.length ? errors : 'none');
say(done ? 'RT-1048 reached stage 10 (every stage done)' : 'RT-1048 did NOT reach stage 10');
await browser.close();
process.exit(errors.length || !done ? 1 : 0);
