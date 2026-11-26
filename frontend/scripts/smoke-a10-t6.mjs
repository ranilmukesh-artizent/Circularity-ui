/**
 * Plan 10, T6 browser check (read-only): the sparkle icon appears only on Ask Circularity's entry and panel header,
 * no Modeler text carries a check, cross or warning glyph, and "Ask about RT-1048" opens the assistant.
 *
 *   node scripts/smoke-a10-t6.mjs [baseUrl] [account ...]
 */
import { readFileSync } from 'node:fs';
import { chromium } from '@playwright/test';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const ACCOUNTS = ['admin', 'executive', 'planner-a', 'planner-b', 'planner-c', 'approver', 'engineer', 'finance', 'developer', 'wm-1', 'wm-2'];
const only = process.argv.slice(3);
const accounts = only.length ? only : ACCOUNTS;
const EXTRA = ['#/product/RT-1048', '#/tasks', '#/alerts', '#/checks', '#/reports', '#/modeler'];

// the spark icon's inner markup, read from the generated asset file (the demo's icon set)
const assets = readFileSync(new URL('../src/assets/assets.gen.ts', import.meta.url), 'utf8');
const ICON = JSON.parse(/export const ICON[^=]*= (\{.*?\});/s.exec(assets)[1]);
const SPARK = /^<svg[^>]*>([\s\S]*)<\/svg>$/.exec(ICON.spark.trim())[1].replace(/\s+/g, '');

const browser = await chromium.launch({ channel: 'chrome', headless: true });
let failures = 0;
const fail = (m) => {
  failures++;
  console.log('FAIL ' + m);
};

for (const acct of accounts) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await page.goto(base + '/#/signin');
  await page.fill('#si-id', acct);
  await page.fill('#si-pw', 'demo');
  await page.click('button[type=submit]');
  await page.waitForSelector('#view', { timeout: 15000 });
  await page.waitForTimeout(800);
  const links = await page.$$eval('a[href^="#/"]', (as) => [...new Set(as.map((a) => a.getAttribute('href')))]);
  const routes = [...new Set([...links, ...EXTRA])].filter((h) => !/signin/.test(h));
  let sparks = 0;
  for (const href of routes) {
    await page.goto(base + '/' + href);
    await page.waitForFunction(() => !document.querySelector('[role=status]')?.textContent?.includes('Loading'), null, { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(300);
    // spark svgs outside the entry button (.frask) and the assistant panel's own header
    const n = await page.evaluate((spark) => {
      const ok = '.frask, .afp, .as-panel, .as-dock, .mdl-agent';
      return [...document.querySelectorAll('svg')].filter((s) => s.innerHTML.replace(/\s+/g, '') === spark && !s.closest(ok)).length;
    }, SPARK);
    if (n) {
      sparks += n;
      fail(`${acct} ${href}: ${n} spark icon(s) outside the entry and the panel header`);
    }
    if (/#\/modeler/.test(href)) {
      const glyphs = await page.evaluate(() => /[✓✕⚠]/.test(document.querySelector('#view')?.innerText ?? ''));
      if (glyphs) fail(`${acct} ${href}: a check, cross or warning glyph in the Modeler`);
    }
  }
  console.log(`${acct}: ${routes.length} pages, ${sparks} stray spark icons`);
  await ctx.close();
}

// "Ask about RT-1048" opens the assistant with the case in its context
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await page.goto(base + '/#/signin');
  await page.fill('#si-id', 'planner-a');
  await page.fill('#si-pw', 'demo');
  await page.click('button[type=submit]');
  await page.waitForSelector('#view', { timeout: 15000 });
  await page.goto(base + '/#/product/RT-1048/overview');
  await page.getByRole('button', { name: 'Ask about RT-1048' }).first().click();
  const ctxLine = await page.getByText('Case: RT-1048').first().waitFor({ timeout: 8000 }).then(() => true, () => false);
  if (!ctxLine) fail('Ask about RT-1048 did not show "Case: RT-1048" in the assistant context line');
  else console.log('Ask about RT-1048: assistant opened with Case: RT-1048');
  await ctx.close();
}

await browser.close();
process.exit(failures ? 1 : 0);
