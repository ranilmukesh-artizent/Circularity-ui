/**
 * Plan 9, Phase 9 demo smoke (P9-9.21, stories UC-01, UC-05, UC-06, UC-08, UC-09, UC-11, UC-12, UC-16, UC-19, UC-20): the used-car
 * segment seen in the browser, one line per step (PASS, or FAIL with the step and what was missing, then exit 1 at once). Chrome
 * through Playwright, every check through the UI unless the line says "(action: ...)": the reads and the clicks the app has no
 * control for yet (registering an extra system, opening a case from the mocks' data) use the app's own action call.
 *
 *   1  developer registers and connects uc_lease, uc_dms, uc_title, uc_insp, uc_recall, uc_auction and uc_price and runs their
 *      syncs (action: source.reconnect and source.sync: the Connect dialog offers no extra system); the Connection Fabric lists
 *      all seven; then the cars of the demo (VINs ...001, 002, 003, 007, 090) open as used-car cases for Customer A (action:
 *      case.open: a sync opens no used-car case yet).
 *   2  planner.a, Modeler > Compose (used cars, Customer A): the sample prompt "Lease returns to best channel", "1 explicit
 *      control", one question, the answer "Yes, if repair is under the recon limit", and "hail damage under the recon limit stays
 *      retail-eligible" in the draft.
 *   3  planner.a, VIN ...001's case: grade B from the inspection; VIN ...090's grade reads "estimate". "Older damage history not
 *      connected" (P9-9.13).
 *   4  VIN ...003's case: "Clear title, no open finance" on the routes; My work lists "Lien found after check-in".
 *   5  VIN ...002's case: "Open recall: no retail until remedied"; "Re-check" where the page offers it.
 *   6  VIN ...001's case recommends "Retail · South lot" with net 21,489.50 and lists auction, dealer trade and "Not considered"
 *      for salvage.
 *   7  approver: My work shows "Recon $2,800 over the $2,500 limit" for VIN ...007; approves on the case page; the Execute stage
 *      shows the recon order, lot transfer and listing steps.
 *   8  planner.a tries "dealer trade within the group: skip the title check" in Compose and sees the refusal (P9-9.14).
 *   9  planner.a: the alert "EV crossovers ageing at North lot" (P9-9.18); Analytics > Packs shows "Why are EV crossovers sitting
 *      longer on our lots?" with its chart (P9-9.19); the replay figures labelled modelled on the Compose publish step (P9-9.15).
 *
 * A check that needs a task not built yet (P9-9.13 to 9.16, 9.18, 9.19) looks for its marker file in the repository: while the
 * file is missing the check prints "(skipped: P9-9.x not merged)" and counts as a pass when its text is absent; once the task is
 * merged the same check is a hard one, so the smoke tightens itself. Text that the used-car case pages do not show at all yet
 * (a fact's source and age) is not checked and says so.
 *
 * Needs the worker (syncs) and source-sim (the seven mocks). No vendor product is claimed connected: every system is synthetic.
 * Changes state. The lead runs, holding the api test lock meanwhile:
 *   bash scripts/dev/reset.sh && bash scripts/dev/wait-idle.sh
 *   node frontend/scripts/smoke-p9-9.mjs http://localhost:5173
 *   bash scripts/dev/reset.sh
 * It resets nothing itself. Screenshots of a failing step go to SMOKE_SHOTS (default: <OS temp>/smoke-p9-9).
 * The last line is "smoke-p9-9: all 9 steps passed".
 */
import { chromium } from '@playwright/test';
import { existsSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describeInAssistant, openInSetup, openSetupTab } from './a10-setup.mjs';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const shots = process.env.SMOKE_SHOTS || path.join(tmpdir(), 'smoke-p9-9');
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const ORG = 'Customer A';
const SOURCES = ['uc_lease', 'uc_dms', 'uc_title', 'uc_insp', 'uc_recall', 'uc_auction', 'uc_price'];
const vin = (n) => 'SYNUC' + String(n).padStart(12, '0');
const CARS = [1, 2, 3, 7, 90]; // the demo's cars: UC-S1 (retail South), UC-S2 (recall), UC-S3 (lien), UC-S7 (recon 2,800), 090 (inspection scheduled)
const MODELER = `${base}/#/modeler?template=used_cars&org=${encodeURIComponent(ORG)}`;
const UI = 180000; // the dev stack answers slowly while the worker syncs (compose.systems alone takes seconds)
const FIRST = 180000; // a first page load after sign-in
const SYNC = 180000;
const MARK = {
  '9.13': 'source-sim/sim/vendors/body_shop_legacy/__init__.py',
  '9.14': 'backend/tests/test_uc_customer_layer.py',
  '9.15': 'backend/di/services/modeler/replay_samples/used_cars.py',
  '9.18': 'backend/tests/test_uc_ageing.py',
  '9.19': 'backend/tests/test_uc_analytics.py',
};
mkdirSync(shots, { recursive: true });

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const errors = [];
const pages = {};
const say = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

async function as(acct) {
  if (pages[acct]) return pages[acct];
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } });
  const p = await ctx.newPage();
  p.on('crash', () => say('CRASH', acct, p.url()));
  p.setDefaultTimeout(UI);
  p.on('pageerror', (e) => errors.push(`${acct} @ ${p.url().replace(/^.*#/, '#')}: ${e.message}`));
  await p.goto(base + '/#/signin', { waitUntil: 'domcontentloaded', timeout: 180000 });
  await p.fill('#si-id', acct);
  await p.fill('#si-pw', 'demo');
  await p.click('button[type=submit]');
  await p.waitForURL((u) => !/signin/.test(u.hash), { timeout: FIRST });
  await p.locator('#view').first().waitFor({ timeout: FIRST });
  await p.waitForTimeout(2500); // the shell's own redirect to Home lands a moment after sign-in and would undo a goto made now
  pages[acct] = p;
  return p;
}

const callAction = (p, id, body) =>
  p.evaluate(
    async ([id, body]) => {
      const r = await fetch('/api/actions/' + id, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + sessionStorage.getItem('circ-api-token') },
        body: JSON.stringify(body),
      });
      return r.json();
    },
    [id, body],
  );
const must = async (p, id, body) => {
  const r = await callAction(p, id, body);
  if (!r.ok) throw new Error(`${id}: ${JSON.stringify(r.error || r).slice(0, 240)} (reset the stack first?)`);
  return r.output;
};
const getJson = (p, url) =>
  p.evaluate(async (url) => (await fetch(url, { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('circ-api-token') } })).json(), url);
const text = (p) => p.innerText('body'); // toasts are outside #view
const until = async (fn, msg, ms, p) => {
  const end = Date.now() + ms;
  for (;;) {
    const v = await fn().catch(() => null);
    if (v) return v;
    if (Date.now() > end) throw new Error(msg);
    await p.waitForTimeout(1000);
  }
};
const waitText = (p, rx, msg, ms = UI) => until(async () => rx.test(await text(p)), msg || `"${rx}" never showed`, ms, p);
/** Open a route and drop the read cache with a reload (a hash change alone keeps what the page read earlier). */
async function open(p, url, ready = '#view') {
  const want = url.replace(/^.*#/, '#');
  for (let i = 0; i < 4; i++) {
    await p.goto(url, { waitUntil: 'domcontentloaded', timeout: 180000 });
    await p.waitForTimeout(800);
    if (p.url().includes(want)) break; // else the shell sent us Home: try again
  }
  await p.reload();
  await p.locator(ready).first().waitFor({ timeout: FIRST });
}

async function step(name, fn) {
  const t0 = Date.now();
  try {
    const detail = await fn();
    say('PASS', name, detail ? '- ' + detail : '', `(${Math.round((Date.now() - t0) / 1000)} s)`);
  } catch (e) {
    say('FAIL', name, '-', String(e?.message || e).split('\n').slice(0, 3).join(' | '), (e?.stack || '').match(/smoke-p9-9\.mjs:\d+/)?.[0] ?? '');
    for (const [a, p] of Object.entries(pages)) await p.screenshot({ path: path.join(shots, `fail-${a}.png`), fullPage: true }).catch(() => {});
    await Promise.race([browser.close().catch(() => {}), new Promise((r) => setTimeout(r, 5000))]);
    process.exit(1);
  }
}

/** A check on a task that may not be merged: found is a pass; absent is a skip while the task's marker file is missing, a failure after. */
const merged = (task) => existsSync(path.join(ROOT, MARK[task]));
function needs(task, found, label, notes) {
  if (found) return notes.push(label);
  if (merged(task)) throw new Error(`${label}: not shown, and P9-${task} is merged`);
  notes.push(`${label} (skipped: P9-${task} not merged)`);
}

// ---------------------------------------------------------------- the case pages
const cases = {}; // VIN number -> case id
const seen = {}; // case id -> the text of its pages
/** The text of the places a case shows what a person reads: Overview, the stages that matter and their tabs (read fresh, once per call). */
const PLACES = [
  'overview', 'stage/4?tab=evidence', 'stage/5', 'stage/6', 'stage/6?tab=compare', 'stage/6?tab=evidence', 'stage/6?tab=packet',
  'stage/6?tab=why', 'stage/7', 'stage/7?tab=checks',
];
async function caseText(p, id, fresh = false) {
  if (!fresh && seen[id]) return seen[id];
  let all = '';
  for (const place of PLACES) {
    await open(p, `${base}/#/product/${id}/${place}`);
    await p.waitForTimeout(400);
    all += '\n' + (await p.innerText('#view').catch(() => ''));
  }
  seen[id] = all;
  return all;
}
const inCase = async (p, id, rx, what, fresh) => {
  const t = await caseText(p, id, fresh);
  if (!rx.test(t)) throw new Error(`case ${id} (VIN ${what.vin}) does not show ${what.label}`);
  return t;
};
const need = (n) => {
  if (!cases[n]) throw new Error(`no case for VIN ...${String(n).padStart(3, '0')}: step 1 did not run`);
  return cases[n];
};

// ---------------------------------------------------------------- 1
await step('1 Connect the seven used-car systems, sync them and open the cars as cases', async () => {
  const dev = await as('developer');
  for (const sid of SOURCES) await must(dev, 'source.reconnect', { source_id: sid }); // (action) registers an extra system, then connects it
  for (const sid of SOURCES) await must(dev, 'source.sync', { source_id: sid });
  for (const sid of SOURCES) {
    await until(
      async () => {
        const d = await getJson(dev, '/api/screens/integration/sources/' + sid);
        return d?.sync_history?.length && d.sync_history[0].ok ? true : null;
      },
      `${sid} did not finish a sync`,
      SYNC,
      dev,
    );
  }
  await open(dev, base + '/#/integration/overview', 'tr[data-int]');
  for (const sid of SOURCES) await dev.locator(`tr[data-int="${sid}"]`).first().waitFor({ timeout: UI });

  // (action: case.open) the sync opens no used-car case yet; the key is the car's canonical key as the sources wrote it (org unit, then VIN: the demo seed registers the used-car systems for Customer A, as the other packs' smokes expect)
  const planner = await as('planner.a');
  const openCar = (n) =>
    callAction(planner, 'case.open', {
      org_unit_id: ORG, template_key: 'used_cars', asset_key: `${ORG}:${vin(n)}`, reason: n > 60 ? 'trade_in' : 'lease_end',
      facts: { vin: vin(n), mileage: 38000, return_date: '2026-11-20' },
    });
  for (const n of CARS) {
    let r = await openCar(n);
    if (!r.ok && /pack|template/i.test(JSON.stringify(r))) { // "No pack" before packs as templates, "The template is one of" after
      // the pack of the org is published by people first (admin imports, approver approves): the shipped pack, as the api tests do
      const { readFileSync } = await import('node:fs');
      const doc = JSON.parse(readFileSync(path.join(ROOT, 'backend/di/services/modeler/packs/used_cars.json'), 'utf8'));
      doc.version = '1.9.1';
      const imp = await callAction(await as('admin'), 'pack.import', { doc });
      if (imp.ok) {
        await must(await as('admin'), 'pack.submit', { id: imp.output.id });
        await must(await as('approver'), 'pack.approve', { id: imp.output.id });
      }
      r = await openCar(n);
    }
    if (!r.ok) throw new Error(`case.open for VIN ...${n}: ${JSON.stringify(r.error || r).slice(0, 240)} (reset the stack first?)`);
    cases[n] = r.output.case_id;
  }
  return `${SOURCES.length} systems synced; cases ${CARS.map((n) => `${n}=${cases[n]}`).join(', ')}`;
});

// ---------------------------------------------------------------- 2
const compose = (p) => p.locator('section[aria-label="Compose"]');
async function startCompose(p, typed) {
  await open(p, MODELER, '.mdl-tabs');
  await openSetupTab(p);
  await compose(p).waitFor();
  // plan 10: the Describe step is Ask Circularity's Set up mode, then "Open in Set up" shows the composition
  await describeInAssistant(p, typed === undefined ? { title: 'Lease returns to best channel', timeout: UI } : { typed, timeout: UI });
  await openInSetup(p, UI);
  await compose(p).getByRole('heading', { name: /What the agent read/ }).waitFor({ timeout: UI });
}
let COMP = 0;
await step('2 Compose: the sample prompt, one explicit control, one question, the hail rule in the draft', async () => {
  const p = await as('planner.a');
  await startCompose(p);
  const t = await compose(p).innerText();
  if (!/\b1 explicit control\b/.test(t)) throw new Error('the reading does not say "1 explicit control": ' + (t.match(/\d+ explicit controls?/)?.[0] || 'no such line'));
  const q = compose(p).locator('.cmp-question');
  if ((await q.count()) !== 1) throw new Error(`expected exactly one question, found ${await q.count()}`);
  COMP = Number((await compose(p).locator('.cmp-state').innerText().catch(() => '')).match(/composition (\d+) is/)?.[1]) || 0;
  await q.getByRole('button', { name: 'Yes, if repair is under the recon limit', exact: true }).click();
  await until(async () => /hail damage under the recon limit stays retail-eligible/.test(await compose(p).innerText()), 'the draft does not show "hail damage under the recon limit stays retail-eligible"', UI, p);
  return `composition ${COMP || '?'}`;
});

// ---------------------------------------------------------------- 3
await step('3 The car case: grade B from the inspection, an estimate for the late inspection, what is not connected', async () => {
  const p = await as('planner.a');
  const notes = [];
  const t1 = await inCase(p, need(1), /Grade B\b/, { vin: vin(1), label: '"Grade B"' });
  notes.push('VIN ...001 Grade B' + (/Inspection/.test(t1) ? ' (Inspection)' : ''));
  const t90 = await caseText(p, need(90));
  if (!/\bestimate\b/i.test(t90)) throw new Error(`VIN ...090 (${need(90)}) does not show "estimate" for the grade of a car without a finished inspection`);
  notes.push('VIN ...090 estimate');
  needs('9.13', /Older damage history not connected/.test(t1), '"Older damage history not connected"', notes);
  notes.push('(facts with source and age: not checked, the case pages list no vehicle facts yet)');
  return notes.join('; ');
});

// ---------------------------------------------------------------- 4
await step('4 The lien: "Clear title, no open finance" on the routes, "Lien found after check-in" in My work', async () => {
  const p = await as('planner.a');
  const t = await inCase(p, need(3), /Clear title, no open finance/, { vin: vin(3), label: '"Clear title, no open finance"' });
  const n = (t.match(/Clear title, no open finance/g) || []).length;
  let where = '';
  for (const acct of ['planner.a', 'admin', 'approver']) {
    const q = await as(acct);
    await open(q, base + '/#/mywork');
    await q.waitForTimeout(800);
    if (/Lien found after check-in/.test(await text(q))) {
      where = acct;
      break;
    }
  }
  if (!where) throw new Error('"Lien found after check-in" is in nobody\'s My work (planner.a, admin, approver)');
  return `${n} mentions on the case; My work of ${where}`;
});

// ---------------------------------------------------------------- 5
await step('5 The open recall: "Open recall: no retail until remedied", Re-check', async () => {
  const p = await as('planner.a');
  const id = need(2);
  await inCase(p, id, /Open recall: no retail until remedied/, { vin: vin(2), label: '"Open recall: no retail until remedied"' });
  // "Re-check" shows beside a stale check only; a fresh check has no button
  await open(p, `${base}/#/product/${id}/stage/6?tab=evidence`);
  const btn = p.locator('[data-recheck]').first();
  if (!(await btn.count())) return 'the recall check is fresh: no Re-check offered';
  const before = await p.innerText('#view');
  await btn.click();
  await until(async () => (await p.innerText('#view')) !== before, 'Re-check changed nothing on the page', UI, p);
  return 'Re-check ran and the page changed';
});

// ---------------------------------------------------------------- 6
await step('6 The channels: Retail South lot at 21,489.50, auction, dealer trade, salvage not considered', async () => {
  const p = await as('planner.a');
  const t = await inCase(p, need(1), /Retail\s*[·\-:]\s*South lot/i, { vin: vin(1), label: '"Retail · South lot"' });
  if (!/21,489\.50|21,490|21\.5k/.test(t)) throw new Error('VIN ...001 does not show the net 21,489.50 (or 21,490, 21.5k)');
  for (const [rx, what] of [[/Auction/i, 'auction'], [/Dealer trade/i, 'dealer trade'], [/Not considered/, '"Not considered" for salvage']]) {
    if (!rx.test(t)) throw new Error(`VIN ...001 does not list ${what}`);
  }
  return 'recommends Retail · South lot, net 21,489.50';
});

// ---------------------------------------------------------------- 7
await step('7 Recon over the limit: the manager approves, the Execute stage shows recon order, transfer and listing', async () => {
  const id = need(7);
  const ap = await as('approver');
  await open(ap, base + '/#/mywork');
  await waitText(ap, /Recon \$2,800 over the \$2,500 limit/, "the approval for VIN ...007 is not in the approver's My work", UI);
  await open(ap, `${base}/#/product/${id}/stage/7`);
  await ap.locator('button', { hasText: /^\s*Approve (?!and send)/ }).first().click();
  await ap.getByLabel(/I reviewed evidence snapshot/).check();
  await ap.getByText('Approve and send instruction').click();
  await waitText(ap, /APR-\S+ created/, 'no "APR-... created" confirmation after the approval', UI);
  await open(ap, `${base}/#/product/${id}/stage/8?tab=plan`);
  const need8 = [[/Reconditioning order/, 'the recon order'], [/Transfer to the lot/, 'the lot transfer'], [/Retail listing/, 'the listing']];
  await until(async () => { const v = await ap.innerText('#view'); return need8.every(([rx]) => rx.test(v)); }, 'the Execute stage does not list ' + need8.map((x) => x[1]).join(', '), UI, ap);
  return 'approved; recon order, lot transfer and listing steps listed';
});

// ---------------------------------------------------------------- 8
await step('8 The diversion that skips the title check is refused', async () => {
  const p = await as('planner.a');
  const notes = [];
  await startCompose(p, 'dealer trade within the group: skip the title check');
  await p.waitForTimeout(800);
  const t = await compose(p).innerText();
  needs('9.14', /bypass the compliance guardrail|skips the compliance guardrail|G-VEH-TITLE/i.test(t), 'the refusal names the compliance guardrail', notes);
  return notes.join('; ');
});

// ---------------------------------------------------------------- 9
await step('9 The ageing alert, the analytics question and the modelled replay figures', async () => {
  const p = await as('planner.a');
  const notes = [];
  // the alert, on the pages that list suggestions and alerts
  let alert = false;
  for (const url of [`${base}/#/home`, `${base}/#/modeler/overview`, MODELER]) {
    await open(p, url);
    await p.waitForTimeout(600);
    if (/EV crossovers ageing at North lot/.test(await text(p))) {
      alert = true;
      break;
    }
  }
  needs('9.18', alert, 'the alert "EV crossovers ageing at North lot"', notes);

  // the worked question, in Analytics > Packs
  await open(p, `${base}/#/analytics/packs`);
  const pick = p.locator('select[aria-label="Pack"]');
  if (await pick.count()) await pick.selectOption('used_cars').catch(() => {});
  await p.waitForTimeout(800);
  const q = /Why are EV crossovers sitting longer on our lots\?/.test(await text(p));
  needs('9.19', q, 'the question "Why are EV crossovers sitting longer on our lots?"', notes);
  if (q) {
    const t = await text(p);
    if (!/\bNorth\b/.test(t) || !/\b58\b/.test(t)) throw new Error('the EV crossover question shows no chart rows (North lot at 58 days)');
    notes.push('with its chart');
  }

  // the replay figures, on the Compose publish step of the composition of step 2
  await open(p, `${MODELER}${COMP ? `&compose=${COMP}` : ''}`, '.mdl-tabs');
  if (!COMP) await openSetupTab(p);
  await compose(p).waitFor();
  const tab = compose(p).getByRole('tab', { name: 'Publish', exact: true });
  if (await tab.count()) await tab.click();
  await p.waitForTimeout(800);
  const t = await compose(p).innerText();
  needs('9.15', /modelled/i.test(t) && /uplift|straight-through/i.test(t), 'the replay figures labelled modelled on the publish step', notes);
  return notes.join('; ');
});

if (errors.length) {
  say('FAIL page errors:', JSON.stringify(errors));
  await browser.close();
  process.exit(1);
}
await browser.close();
console.log('\nsmoke-p9-9: all 9 steps passed');
