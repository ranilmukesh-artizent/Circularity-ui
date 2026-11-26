/**
 * Plan 10, T7 visual check (read-only): the Modeler canvas in light and dark (node refresh, the revision mark on a
 * node, the minimap following the theme), the Workflow Studio canvas (must look as before), and the contrast of the
 * assistant's status-line and provenance-tag text against their backgrounds in both themes (>= 4.5:1).
 *
 *   node frontend/scripts/smoke-a10-t7.mjs http://localhost:5187 [outDir]
 *
 * Screenshots go to <outDir>/p10-t7-*.png (default: the current directory). Changes nothing: it signs in as admin and
 * only reads. The proposed-node mark is drawn onto one node in the DOM (a class and a tag), not through an apply.
 */
import { chromium } from '@playwright/test';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const out = process.argv[3] || '.';
let failed = 0;
const check = (ok, msg) => { console.log((ok ? 'ok   ' : 'FAIL ') + msg); if (!ok) failed++; };

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));

await page.goto(base + '/#/signin');
await page.fill('#si-id', 'admin');
await page.fill('#si-pw', 'demo');
await page.click('button[type=submit]');
await page.waitForSelector('.sidebar, nav, #view', { timeout: 20000 });

const theme = (t) => page.evaluate((v) => { localStorage.setItem('circ-theme', v); document.documentElement.dataset.theme = v; }, t);
const shot = (name) => page.screenshot({ path: `${out}/p10-t7-${name}.png`, fullPage: false });

// ---- the Modeler canvas ----
await page.goto(base + '/#/modeler');
await page.waitForSelector('.mdl-canvas .mdl-node', { timeout: 40000 });
await page.locator('.mdl-canvas').scrollIntoViewIfNeeded();
await page.waitForTimeout(800);
// draw the revision mark on one rule or outcome node, as the proposal would (class + tag), without applying anything
await page.evaluate(() => {
  const n = document.querySelector('.mdl-node.t-path, .mdl-node.t-rule');
  if (!n) return;
  n.classList.add('prop', 'rev');
  n.insertAdjacentHTML('afterbegin', '<svg class="rev-ol" aria-hidden="true"><rect class="dash" x=".75" y=".75" rx="7.25"></rect></svg><span class="rev-tag mono">Δ2</span>');
});
for (const t of ['light', 'dark']) {
  await theme(t);
  await page.waitForTimeout(300);
  await shot(`modeler-${t}`);
  const mm = await page.evaluate(() => {
    const el = document.querySelector('.mdl-canvas .react-flow__minimap');
    return el ? getComputedStyle(el).backgroundColor : null;
  });
  const rgb = (mm ?? '').match(/\d+/g)?.map(Number) ?? [];
  const lum = rgb.length >= 3 ? (rgb[0] + rgb[1] + rgb[2]) / 3 : null;
  check(lum !== null && (t === 'dark' ? lum < 80 : lum > 200), `minimap background follows the ${t} theme (${mm})`);
  const kind = await page.$eval('.mdl-node .kind', (e) => e.textContent).catch(() => null);
  check(!!kind && kind !== kind.toUpperCase(), `node kind line is sentence case ("${kind}")`);
}
check(await page.$('.mdl-node .mdl-key') !== null, 'a locked node shows the key icon');
check(await page.$('.mdl-node.rev .rev-tag') !== null, 'the revision tag is drawn on the proposed node');
await theme('light');

// ---- the Workflow Studio canvas (unchanged) ----
await page.goto(base + '/#/integration/studio/WF-103');
await page.waitForTimeout(1500);
await page.waitForSelector('.graphbox', { timeout: 20000 }).catch(() => {});
await page.waitForTimeout(1000);
check(await page.$('.graphbox') !== null, 'the Workflow Studio canvas opens');
for (const t of ['light', 'dark']) { await theme(t); await page.waitForTimeout(300); await shot(`workflow-${t}`); }
check(await page.$('.graphbox .mdl-node') === null, 'the Workflow Studio canvas uses no Modeler node');
await theme('light');

// ---- contrast of the assistant's status-line and tag text, in both themes ----
for (const t of ['light', 'dark']) {
  await theme(t);
  const rows = await page.evaluate(() => {
    const probe = document.createElement('div');
    probe.className = 'as-panel';
    probe.style.cssText = 'position:fixed;left:0;top:0;visibility:hidden';
    probe.innerHTML = '<p class="as-status">Checked</p><p class="as-basis amber">Nearest pack</p><div class="as-card held"><span class="as-prov retrieved">Retrieved</span><span class="as-prov rules">Rules</span><span class="as-prov model">Model</span><span class="as-prov simulated">Simulated</span><span class="as-prov agent">Prepared by agent</span></div>';
    document.body.appendChild(probe);
    const parse = (c) => c.match(/[\d.]+/g).map(Number);
    const lin = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    const L = (c) => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
    const over = (fg, bg) => { const a = fg[3] ?? 1; return [0, 1, 2].map((i) => fg[i] * a + bg[i] * (1 - a)); };
    const bgOf = (el) => {
      const chain = [];
      for (let e = el; e; e = e.parentElement) { const c = parse(getComputedStyle(e).backgroundColor); if (c[3] === undefined || c[3] > 0) chain.push(c); if ((c[3] ?? 1) === 1) break; }
      return chain.reverse().reduce((acc, c) => over(c, acc), parse(getComputedStyle(document.body).backgroundColor).slice(0, 3));
    };
    const out = [];
    for (const el of probe.querySelectorAll('.as-status, .as-basis, .as-prov')) {
      const fg = parse(getComputedStyle(el).color); const bg = bgOf(el);
      const l1 = L(over(fg, bg)), l2 = L(bg);
      out.push({ what: el.className, ratio: (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05) });
    }
    probe.remove();
    return out;
  });
  for (const r of rows) check(r.ratio >= 4.5, `${t}: ${r.what} contrast ${r.ratio.toFixed(2)}:1`);
}
await theme('light');
check(errors.length === 0, 'no page errors' + (errors.length ? ': ' + errors[0] : ''));
await browser.close();
process.exit(failed ? 1 : 0);
