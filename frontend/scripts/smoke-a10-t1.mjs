/**
 * Plan 10, T1: the one assistant's dock and Ask mode. As planner-a: focus the top-bar entry, Ctrl+J on Home opens the
 * dock, click a starter, see a done status line and an answer, Esc closes and focus returns to the entry. Read-only.
 *   node scripts/smoke-a10-t1.mjs [baseUrl] [account]
 * With SHOTS=<dir> it also saves light and dark screenshots of the open dock there.
 */
import { chromium } from '@playwright/test';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const acct = process.argv[3] || 'planner-a';
const shots = process.env.SHOTS;
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
let failed = 0;
const check = (ok, what) => {
  console.log((ok ? 'ok   ' : 'FAIL ') + what);
  if (!ok) failed++;
};

await page.goto(base + '/#/signin');
await page.fill('#si-id', acct);
await page.fill('#si-pw', 'demo');
await page.click('button[type=submit]');
await page.waitForSelector('#view', { timeout: 15000 });
await page.waitForTimeout(1200);

await page.focus('button.frask');
await page.keyboard.press('Control+j');
await page.waitForSelector('aside.as-dock', { timeout: 5000 });
check(await page.$eval('#as-q-dock', (el) => el === document.activeElement), 'the composer has focus when the dock opens');
check((await page.$$('aside.as-panel')).length === 1, 'one panel on the page');
const ctxLine = await page.$eval('.as-ctx', (n) => n.textContent);
check(/Looking at: /.test(ctxLine ?? ''), 'the context line says what it may read: ' + ctxLine);
check((await page.$$('[role=radio]')).length >= 1, 'the mode radio is there');

const starter = await page.$('.as-starters button');
check(!!starter, 'a starter is offered');
if (starter) {
  const text = (await starter.textContent()) ?? '';
  await starter.click();
  await page.waitForSelector('.as-turn .as-status.done', { timeout: 90000 });
  const turn = await page.$eval('.as-turn', (n) => n.innerText);
  check(turn.includes(text.trim()), 'the person\'s words show as a line');
  check((await page.$eval('.as-turn .as-status.done', (n) => n.textContent ?? '')).length > 0, 'a done status line shows');
  check(((await page.$eval('.as-text', (n) => n.textContent).catch(() => '')) ?? '').length > 0, 'an answer shows');
  check(!/You:|Thinking/.test(turn), 'no "You:" and no "Thinking…"');
}
if (shots) {
  await page.screenshot({ path: `${shots}/p10-t1-home-dock-light.png` });
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${shots}/p10-t1-home-dock-dark.png` });
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'light'));
}

await page.keyboard.press('Escape');
await page.waitForSelector('aside.as-dock', { state: 'detached', timeout: 5000 });
check(await page.$eval('button.frask', (el) => el === document.activeElement), 'Esc closes the dock and focus returns to the entry');
check(errors.length === 0, 'no page errors ' + errors.join(' | '));
await browser.close();
process.exit(failed ? 1 : 0);
