/**
 * The Modeler end to end (plan 8, MVP-4.6): Planner A gives Customer A its own industrial flow and adds a rule
 * "exclude resale for grade C" in the inspector; the simulation shows "N of M"; Planner A submits; the Approver
 * approves (shadow) and publishes; after the case is declined, Planner A re-evaluates RT-1079 (Customer A, grade C,
 * recommending resale) and its case page shows the exclusion. Exits non-zero on any missing text.
 * Changes state, and resets nothing itself:
 *   bash scripts/dev/reset.sh && node frontend/scripts/smoke-modeler.mjs http://localhost:5173 && bash scripts/dev/reset.sh
 */
import { chromium } from '@playwright/test';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const CASE = 'RT-1079';
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const fails = [];

function check(ok, what) {
  console.log((ok ? 'ok   ' : 'FAIL ') + what);
  if (!ok) fails.push(what);
}

async function session(acct) {
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } });
  const page = await ctx.newPage();
  page.errors = [];
  page.on('pageerror', (e) => page.errors.push(e.message + ' ' + (e.stack || '').split('\n').slice(0, 3).join(' | ')));
  await page.goto(base + '/#/signin');
  await page.fill('#si-id', acct);
  await page.fill('#si-pw', 'demo');
  await page.click('button[type=submit]');
  await page.waitForURL((u) => !/signin/.test(u.hash), { timeout: 60000 }); // the sign-in redirect must land before the next goto
  await page.waitForTimeout(1500);
  return page;
}

const view = (p) => p.innerText('body'); // toasts are outside #view
async function waitText(p, rx, ms = 30000) {
  for (let t = 0; t < ms; t += 250) {
    if (rx.test(await view(p))) return true;
    await p.waitForTimeout(250);
  }
  return false;
}

// plan 10: the Modeler's rail holds Inspector, Checks, Impact and History as tabs that open on demand at this width
async function railTab(p, name) {
  const tab = p.locator('.mdl-strip').getByRole('tab', { name, exact: false }).first();
  if ((await tab.getAttribute('aria-selected')) !== 'true') await tab.click();
}

// 1. Planner A: the Customer A flow, a rule excluding resale for grade C
const planner = await session('planner-a');
await planner.goto(base + '/#/modeler');
check(await waitText(planner, /Industrial returns · /, 40000), 'planner-a opens the Modeler'); // a cold dev server needs more than 10 s
const fork = planner.getByRole('button', { name: /Give Customer A its own flow/ });
if (await fork.count()) {
  await fork.click();
  check(await waitText(planner, /Industrial returns · Customer A/), 'Customer A gets its own flow');
}
await planner.getByRole('button', { name: 'Add rule' }).click();
await planner.getByLabel('Path').selectOption('resale');
await planner.getByLabel('Action').selectOption('exclude');
await planner.locator('fieldset', { hasText: 'Grade' }).getByLabel('C', { exact: true }).check();
check(await waitText(planner, /IR-01 · never whole-asset resale/), 'the rule reads "IR-01 · never whole-asset resale"');
await planner.waitForTimeout(3000); // the 2 s autosave
await railTab(planner, 'Checks');
check(await waitText(planner, /IR-01 active: grade C: never whole-asset resale\./), 'the checks show the rule active');

// 2. Simulate on the open queue
await railTab(planner, 'Impact');
await planner.getByRole('button', { name: 'Simulate on open queue' }).click();
check(await waitText(planner, /\d+ of \d+ open decisions change/), 'the simulation shows "N of M open decisions change"');
console.log('impact:', ((await view(planner)).match(/\d+ of \d+ open decisions change[^\n]*/) || [''])[0]);

// 3. Submit
await planner.getByRole('button', { name: 'Submit for approval' }).click();
check(await waitText(planner, /In review · v2/), 'submitted: In review');

check(planner.errors.length === 0, 'no page errors on the Modeler (planner) ' + JSON.stringify(planner.errors));

// 4. The Approver approves (shadow) and publishes
const approver = await session('approver');
await approver.goto(base + '/#/modeler?org=' + encodeURIComponent('Customer A'));
check(await waitText(approver, /In review · v2/), 'the approver sees the flow in review');
await approver.getByRole('button', { name: 'Approve', exact: true }).click();
check(await waitText(approver, /Shadow · v2/), 'approved: shadow run');
await approver.getByRole('button', { name: 'Publish' }).click();
check(await waitText(approver, /Published · v2/), 'published v2');

// 5. The case goes back for re-evaluation (the Approver declines it), then Planner A re-evaluates it
const declined = await approver.evaluate(async (id) => {
  const r = await fetch('/api/actions/decision.decline', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + sessionStorage.getItem('circ-api-token') },
    body: JSON.stringify({ case_id: id, reason: 'Re-check with the new business rule.' }),
  });
  return (await r.json()).ok;
}, CASE);
check(declined, CASE + ' declined for re-evaluation');
await planner.goto(base + `/#/product/${CASE}/stage/7`);
await planner.waitForTimeout(2500);
const onModeler = planner.errors.length; // the case pages are not the Modeler's: their errors are reported, not checked
await planner.getByRole('button', { name: new RegExp('Re-evaluate ' + CASE + '|Run re-evaluation') }).first().click();
await waitText(planner, /Re-evaluated/, 5000);
await planner.goto(base + `/#/product/asset/${CASE}`);
let found = await waitText(planner, /Excluded by business rule IR-01/, 6000);
for (const stage of found ? [] : [6, 7]) {
  await planner.goto(base + `/#/product/${CASE}/stage/${stage}`);
  await planner.waitForTimeout(2500);
  for (const tab of ['Compare outcomes', 'Why this outcome', 'Checks']) {
    const t = planner.getByRole('tab', { name: tab });
    if (await t.count()) await t.first().click();
    if (await waitText(planner, /Excluded by business rule IR-01/, 1500)) found = true;
    if (found) break;
  }
  if (found) break;
}
check(found, `the case page shows "Excluded by business rule IR-01"`);

// 6. The assistant (MVP-5.4): the Admin asks for a change to the tool-fleet flow on the workspace
const admin = await session('admin');
await admin.goto(base + '/#/modeler?template=tool_fleet&org=workspace');
check(await waitText(admin, /What I see/, 20000), 'the pinned agent column opens with "What I see"'); // first load of the modeler screen takes ~9 s after sign-in (plan 10: the column replaced the Assistant panel)
await admin.locator('.mdl-agent textarea').fill('Never recycle construction lasers');
await admin.locator('.mdl-agent textarea').press('Enter');
check(await waitText(admin, /Proposed: /, 20000), 'the assistant shows the proposal card ("Proposed: ...")');
check(await waitText(admin, /BR-03: construction lasers: never recycle/), 'the proposal reads "BR-03: construction lasers: never recycle"');
check(await admin.locator('.mdl-node.prop, .mdl-node.rev').count() === 1, 'the proposed rule is drawn dashed on the canvas');

if (planner.errors.length > onModeler) console.log('info: case page errors', JSON.stringify(planner.errors.slice(onModeler)));
const errors = [...planner.errors.slice(0, onModeler).map((e) => 'planner: ' + e), ...approver.errors.map((e) => 'approver: ' + e), ...admin.errors.map((e) => 'admin: ' + e)];
check(errors.length === 0, 'no page errors ' + JSON.stringify(errors));
await browser.close();
if (fails.length) {
  console.log(`\n${fails.length} check(s) failed`);
  process.exit(1);
}
console.log('\nsmoke-modeler: all checks passed');
