/**
 * Plan 10 T4 smoke (read-only): the agent-first Modeler layout.
 *
 *   node scripts/smoke-a10-t4.mjs [baseUrl]
 *
 * As planner-a and admin, at 1440 x 900 and 1920 x 1080: the agent column is the leftmost element of the body and its
 * "What I see" title is inside the first viewport; the Flow tab is no taller than 1.2 viewports; the canvas is at least
 * 520px tall; the rail is closed at 1440 and open at 1920; the four rail tabs and the page tabs exist; clicking a check
 * selects its node in the Inspector; Ctrl+J focuses the pinned composer and no dock appears (needs T1; set
 * A10_T4_SKIP_CTRLJ=1 to skip it before T1 is merged). Uses the installed Chrome.
 */
import { chromium } from '@playwright/test';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const skipCtrlJ = process.env.A10_T4_SKIP_CTRLJ === '1';
const SIZES = [{ width: 1440, height: 900, railOpen: false }, { width: 1920, height: 1080, railOpen: true }];
const RAIL_TABS = ['Inspector', 'Checks', 'Impact', 'History'];

const browser = await chromium.launch({ channel: 'chrome', headless: true });
let failures = 0;
const check = (ok, label) => {
  if (!ok) failures++;
  console.log((ok ? '  ok   ' : '  FAIL ') + label);
};

for (const acct of ['planner-a', 'admin']) {
  for (const size of SIZES) {
    console.log(`${acct} at ${size.width} x ${size.height}`);
    const ctx = await browser.newContext({ viewport: { width: size.width, height: size.height } });
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await page.goto(base + '/#/signin');
    await page.fill('#si-id', acct);
    await page.fill('#si-pw', 'demo');
    await page.click('button[type=submit]');
    await page.waitForSelector('#view', { timeout: 15000 });
    await page.goto(base + '/#/modeler');
    await page.waitForSelector('.mdl-cols .mdl-canvas', { timeout: 20000 });
    await page.waitForTimeout(600);

    const box = async (sel) => page.$eval(sel, (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height, b: r.bottom }; }).catch(() => null);
    const agent = await box('.mdl-agent');
    const center = await box('.mdl-center');
    const rail = await box('.mdl-strip');
    check(!!agent && !!center && agent.x < center.x && (!rail || agent.x < rail.x), 'the agent column is the leftmost element of the body');

    const seen = await page.evaluate((vh) => {
      const t = [...document.querySelectorAll('.mdl-agent *')].find((e) => e.children.length === 0 && /^What I see$/i.test(e.textContent.trim()));
      if (!t) return null;
      const r = t.getBoundingClientRect();
      return r.top >= 0 && r.bottom <= vh;
    }, size.height);
    check(seen === true, '"What I see" is inside the first viewport');

    const tall = await page.evaluate(() => document.documentElement.scrollHeight / window.innerHeight);
    check(tall <= 1.2, `the Flow tab is ${tall.toFixed(2)} viewports tall (<= 1.2)`);
    const canvas = await box('.mdl-canvas');
    check(!!canvas && canvas.h >= 520, `the canvas is ${Math.round(canvas?.h ?? 0)}px tall (>= 520)`);

    const panelOpen = (await page.$('.mdl-rail-panel')) !== null;
    check(panelOpen === size.railOpen, `the rail is ${size.railOpen ? 'open' : 'closed'}`);
    for (const name of RAIL_TABS) check((await page.$(`#mdl-railtab-${name.toLowerCase()}`)) !== null, `rail tab ${name}`);
    const pageTabs = await page.$$eval('.mdl-tabs a', (as) => as.map((a) => a.textContent.trim()));
    const want = acct === 'admin' ? ['Flow', 'Customer layer', 'Policies', 'Packs', 'Set up'] : ['Flow', 'Customer layer', 'Policies'];
    check(want.every((w) => pageTabs.includes(w)), `page tabs: ${pageTabs.join(', ')}`);

    // a check selects its node in the Inspector: look through the templates for a flow with a check that names a step
    const templates = await page.$$eval('#mdl-tpl option', (o) => o.map((x) => x.value));
    let clicked = false;
    for (const tpl of templates) {
      if (tpl !== (await page.$eval('#mdl-tpl', (s) => s.value))) {
        await page.selectOption('#mdl-tpl', tpl);
        await page.waitForSelector('.mdl-cols .mdl-canvas', { timeout: 30000 });
        await page.waitForTimeout(1000);
      }
      await page.waitForSelector('#mdl-railtab-checks');
      if ((await page.$eval('#mdl-railtab-checks', (b) => b.getAttribute('aria-selected'))) !== 'true') await page.click('#mdl-railtab-checks');
      await page.waitForSelector('#mdl-rail-checks');
      const fail = await page.$('#mdl-rail-checks .fail button');
      const any = fail ?? (await page.$('#mdl-rail-checks li button'));
      if (!any) continue;
      await any.click();
      await page.waitForTimeout(300);
      const sel = await page.$$eval('.mdl-node.sel', (n) => n.length);
      const inspector = await page.$eval('#mdl-railtab-inspector', (b) => b.getAttribute('aria-selected'));
      check(sel === 1 && inspector === 'true', `a ${fail ? 'failing ' : ''}check selects its node in the Inspector (${tpl})`);
      clicked = true;
      break;
    }
    if (!clicked) console.log('  skip no template has a check that names a step');
    // a pinned tab stays when a step is selected; with nothing pinned the Inspector shows
    await page.click('#mdl-railtab-history');
    await page.waitForSelector('#mdl-rail-history');
    await page.locator('.mdl-node').first().click({ force: true });
    await page.waitForTimeout(300);
    const aria = (id) => page.$eval(id, (b) => b.getAttribute('aria-selected'));
    check((await aria('#mdl-railtab-history')) === 'true', 'a selection keeps the tab the person pinned');
    await page.click('#mdl-railtab-history'); // unpins and closes
    await page.locator('.mdl-node').nth(1).click({ force: true });
    await page.waitForTimeout(300);
    check((await aria('#mdl-railtab-inspector')) === 'true', 'a selection opens the Inspector when nothing is pinned');
    // Esc closes the rail
    await page.focus('#mdl-railtab-inspector');
    await page.keyboard.press('Escape');
    check((await page.$('.mdl-rail-panel')) === null, 'Esc closes the rail');

    if (!skipCtrlJ) {
      await page.locator('.mdl-canvas').click({ position: { x: 5, y: 5 } });
      await page.keyboard.press('Control+j');
      await page.waitForTimeout(300);
      const inColumn = await page.evaluate(() => !!document.activeElement?.closest('.mdl-agent'));
      const dock = await page.$('.as-dock');
      check(inColumn && !dock, 'Ctrl+J focuses the pinned composer and opens no dock');
    }
    check(errors.length === 0, 'no page errors' + (errors.length ? ': ' + errors[0] : ''));
    await ctx.close();
  }
}

await browser.close();
process.exit(failures ? 1 : 0);
