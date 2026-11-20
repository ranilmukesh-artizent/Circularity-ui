/**
 * Sign-in checks against a running app: wrong account, missing password, a good sign-in that calls di-api's
 * /api/auth/login when the app runs with VITE_BACKEND=api, and the menu badges after signing in.
 *   node scripts/smoke-signin.mjs http://localhost:5174
 */
import { chromium } from '@playwright/test';

const base = process.argv[2] || 'http://localhost:5174';
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage();
const calls = [];
page.on('request', (r) => r.url().includes('/api/') && calls.push(r.method() + ' ' + new URL(r.url()).pathname));

const err = async () => (await page.textContent('#si-err').catch(() => ''))?.trim();
await page.goto(base + '/#/signin');
await page.fill('#si-id', 'nobody');
await page.fill('#si-pw', 'x');
await page.click('button[type=submit]');
await page.waitForTimeout(500);
console.log('unknown account:', await err());
await page.fill('#si-id', 'planner.b@northfield.example');
await page.fill('#si-pw', '');
await page.click('button[type=submit]');
await page.waitForTimeout(500);
console.log('no password:', await err());
await page.fill('#si-pw', 'demo');
await page.click('button[type=submit]');
await page.waitForTimeout(2500);
console.log('landed on:', page.url().replace(base, ''));
console.log('login call:', calls.filter((c) => c.includes('/auth/login')));
console.log('menu badges:', await page.$$eval('.badge, .nb, .cnt', (b) => b.map((x) => x.textContent.trim()).filter(Boolean)));
await page.reload();
await page.waitForTimeout(2000);
console.log('after reload still signed in:', !(await page.$('#si-id')));
await browser.close();
