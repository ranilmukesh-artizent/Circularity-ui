// Dev helper: screenshot routes of the running dev server, signed in as an account.
// usage: node scripts/screenshot.mjs <outDir> <account|-> <route> [route…]      e.g. node scripts/screenshot.mjs ./shots approver home product/received
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';

const [out, acct, ...routes] = process.argv.slice(2);
const base = process.env.BASE_URL ?? 'http://localhost:5173/';
mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ channel: process.env.PW_CHANNEL ?? 'chrome' });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));

await page.goto(base + '#/signin');
if (acct && acct !== '-') {
  await page.fill('#si-id', acct);
  await page.fill('#si-pw', 'demo-password');
  await page.click('button[type=submit]');
  await page.waitForTimeout(400);
}
for (const r of routes.length ? routes : ['']) {
  await page.goto(base + '#/' + r);
  await page.waitForTimeout(500);
  const f = `${out}/${(acct || 'anon') + '_' + (r || 'root').replace(/[^\w-]+/g, '_')}.png`;
  await page.screenshot({ path: f, fullPage: false });
  console.log(f, '→', page.url().replace(base, ''));
}
if (errors.length) console.log('ERRORS:\n' + errors.join('\n'));
await browser.close();
