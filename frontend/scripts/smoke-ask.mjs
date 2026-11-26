/**
 * Ask Circularity in the browser: sign in, open the panel with Ctrl+J on RT-1048's page, ask,
 * and print the streamed answer, the lookups and the sources. Each run spends one or two language-model requests.
 *   node scripts/smoke-ask.mjs http://localhost:5174 planner-a "Why is RT-1048 recommended for redeploy?"
 */
import { chromium } from '@playwright/test';

const [base = 'http://localhost:5174', acct = 'planner-a', question = 'Why is RT-1048 recommended for redeploy?', at = '#/product/asset/RT-1048'] =
  process.argv.slice(2);
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));

await page.goto(base + '/#/signin');
await page.fill('#si-id', acct);
await page.fill('#si-pw', 'demo');
await page.click('button[type=submit]');
await page.waitForTimeout(1500);
await page.goto(base + '/' + at);
await page.waitForTimeout(1500);
await page.keyboard.press('Control+j');
if (!(await page.$('aside.as-panel'))) {
  console.log('Ctrl+J did not open the panel here; using the top bar button. Page errors so far:', errors);
  await page.click('button.frask');
}
await page.waitForSelector('aside.as-panel', { timeout: 5000 });
console.log('context:', await page.$$eval('.as-ctx', (c) => c.map((x) => x.textContent)));
await page.fill('#as-q-dock', question);
await page.keyboard.press('Enter');
await page.waitForFunction(() => ![...document.querySelectorAll('aside.as-panel button')].some((b) => b.textContent === 'Stop'), null, { timeout: 90000 });
const turn = await page.$eval('aside.as-panel .as-turn:last-child', (n) => n.innerText);
console.log('---\n' + turn + '\n---');
console.log('page errors:', errors);
await browser.close();
