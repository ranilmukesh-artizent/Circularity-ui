/**
 * Browser smoke test: sign in as each account, open every page and section in its menu, and report pages that do
 * not render (the error boundary, a blank page) and console errors. Uses the installed Chrome (no download).
 *
 *   node scripts/smoke-pages.mjs [baseUrl] [account ...]
 *   node scripts/smoke-pages.mjs http://localhost:5174 admin planner-b
 *
 * Exit code 1 when any page fails. B18 replaces this with the Playwright suites.
 */
import { chromium } from '@playwright/test';

const base = process.argv[2] || 'http://localhost:5173';
const ACCOUNTS = ['admin', 'executive', 'planner-a', 'planner-b', 'planner-c', 'approver', 'engineer', 'finance', 'developer', 'wm-1', 'wm-2'];
const only = process.argv.slice(3);
const accounts = only.length ? only : ACCOUNTS;
const EXTRA = ['#/product/asset/RT-1048', '#/product/RT-1048', '#/tasks', '#/alerts', '#/checks', '#/reports', '#/settings'];

const browser = await chromium.launch({ channel: 'chrome', headless: true });
let failures = 0;

for (const acct of accounts) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => {
    if (m.type() === 'error' && !/favicon|DevTools/.test(m.text())) errors.push('console: ' + m.text().slice(0, 300));
  });

  await page.goto(base + '/#/signin');
  await page.fill('#si-id', acct);
  await page.fill('#si-pw', 'demo');
  await page.click('button[type=submit]');
  await page.waitForSelector('.sidebar, nav, #view', { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(800);

  const links = await page.$$eval('a[href^="#/"]', (as) => [...new Set(as.map((a) => a.getAttribute('href')))]);
  const routes = [...new Set([...links, ...EXTRA])].filter((h) => !/signin/.test(h));
  const bad = [];
  for (const href of routes) {
    errors.length = 0;
    await page.goto(base + '/' + href);
    await page.waitForFunction(() => !document.querySelector('[role=status]')?.textContent?.includes('Loading'), null, { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(400);
    const broken = await page.$('text=This page could not load');
    const msg = broken ? await page.$eval('[role=alert] .note', (n) => n.textContent).catch(() => '') : '';
    const empty = await page.$eval('#view', (v) => v.innerText.trim().length === 0).catch(() => false);
    if (broken || empty || errors.length) bad.push({ href, error: msg || (empty ? 'empty page' : ''), console: errors.slice(0, 3) });
  }
  failures += bad.length;
  console.log(`${acct}: ${routes.length} routes, ${bad.length} failing`);
  for (const b of bad) console.log('   ', b.href, b.error ? '— ' + b.error : '', b.console.length ? '\n      ' + b.console.join('\n      ') : '');
  await ctx.close();
}

await browser.close();
process.exit(failures ? 1 : 0);
