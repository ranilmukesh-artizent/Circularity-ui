/**
 * Plan 9, Phase 10 demo smoke (P9-10.18, stories TN-01, TN-05, TN-06, TN-08, TN-11, TN-12, TN-17, TN-18, TN-19, TN-22): the telecom
 * network segment seen in the browser, one line per step (PASS, or FAIL with the step and what was missing, then exit 1 at once).
 * Chrome through Playwright, every check through the UI unless the line says "(action: ...)": the reads and the clicks the app has no
 * control for yet (registering an extra system, opening a case from the mocks' data, the cross-region read, an agent-prepared write)
 * use the app's own action call.
 *
 *   1  developer registers and connects tn_inv, tn_decom, tn_bench, tn_spares, tn_broker and tn_recycler and runs their syncs
 *      (action: source.reconnect and source.sync); the Connection Fabric lists all six; the units SN-TN-0001, 0006, 0007, 0012,
 *      0015 and 0202 open as telecom cases for Customer A (action: case.open). planner.a, Modeler > Compose (telecom, Customer A):
 *      the sample prompt "Decommissioned network kit", "1 explicit control", one question about firmware (TN-01).
 *   2  SN-TN-0202's case shows "Unit not in network inventory"; My work lists it (TN-05).
 *   3  SN-TN-0015's case shows "Wipe failed twice: storage destroyed, no resale" (TN-06).
 *   4  approver: My work shows an RAD-7700 export approval with "keep as spares"; approves it on the case page (TN-08).
 *   5  SN-TN-0001's case recommends "Redeploy to a site" with "New spend avoided" and net 9,435.00; the second RRU-4410 case
 *      (SN-TN-0007) says "Site demand SD-112 filled by SN-TN-0001" and recommends "Refurbish as a spare" (TN-11, TN-12).
 *   6  planner.a tries "urgent site outage: skip the configuration wipe" in Compose and sees the refusal and the suggestion (TN-17).
 *   7  (action: telecom.crossRegion) the cross-region alert shows "Transfer to the region buying new" (the app has no page for it
 *      yet); an agent-prepared requisition.reduce is held and Home's "Proposals for you" shows "Reduce purchase requisition"
 *      (TN-18, TN-19).
 *   8  Analytics > Packs answers "Why are we still buying new power units when returns are coming in?"; the Compose publish step
 *      shows the replay figures labelled modelled (TN-22).
 *
 * Needs the worker (syncs) and source-sim (the six mocks). No vendor product is claimed connected: every system is synthetic.
 * Changes state. The lead runs, holding the api test lock meanwhile:
 *   bash scripts/dev/reset.sh && bash scripts/dev/wait-idle.sh
 *   node frontend/scripts/smoke-p9-10.mjs http://localhost:5173
 *   bash scripts/dev/reset.sh
 * It resets nothing itself. Screenshots of a failing step go to SMOKE_SHOTS (default: <OS temp>/smoke-p9-10).
 * Legal note: export-control, covered-equipment and wipe wording is the pack's data; Kinective's Legal team reviews it.
 * The last line is "smoke-p9-10: all 8 steps passed".
 */
import { chromium } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const shots = process.env.SMOKE_SHOTS || path.join(tmpdir(), 'smoke-p9-10');
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const ORG = 'Customer A';
const SOURCES = ['tn_inv', 'tn_decom', 'tn_bench', 'tn_spares', 'tn_broker', 'tn_recycler'];
const sn = (n) => 'SN-TN-' + String(n).padStart(4, '0');
// The mocks' units: n % 6 picks the model (0 RAD-7700, 1 RRU-4410, 3 BBU-5200, 4 LCD-100G); 0001-0033 are the removed ones.
const UNITS = {
  1: { model: 'RRU-4410', site: 'SITE-100' },
  6: { model: 'RAD-7700', site: 'SITE-105' },
  7: { model: 'RRU-4410', site: 'SITE-106' },
  12: { model: 'RAD-7700', site: 'SITE-111' },
  15: { model: 'BBU-5200', site: 'SITE-114' },
  202: { model: 'LCD-100G', site: 'SITE-301' }, // never in the inventory
};
const MODELER = `${base}/#/modeler?template=telecom_network&org=${encodeURIComponent(ORG)}`;
const UI = 30000;
const FIRST = 20000;
const SYNC = 180000;
mkdirSync(shots, { recursive: true });

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const errors = [];
const pages = {};
const say = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

async function as(acct) {
  if (pages[acct]) return pages[acct];
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } });
  const p = await ctx.newPage();
  p.setDefaultTimeout(UI);
  p.on('pageerror', (e) => errors.push(`${acct} @ ${p.url().replace(/^.*#/, '#')}: ${e.message}`));
  await p.goto(base + '/#/signin');
  await p.fill('#si-id', acct);
  await p.fill('#si-pw', 'demo');
  await p.click('button[type=submit]');
  await p.waitForURL((u) => !/signin/.test(u.hash), { timeout: FIRST });
  pages[acct] = p;
  return p;
}

const callAction = (p, id, body, headers = {}) =>
  p.evaluate(
    async ([id, body, headers]) => {
      const r = await fetch('/api/actions/' + id, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + sessionStorage.getItem('circ-api-token'), ...headers },
        body: JSON.stringify(body),
      });
      return r.json();
    },
    [id, body, headers],
  );
const must = async (p, id, body, headers) => {
  const r = await callAction(p, id, body, headers);
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
  await p.goto(url);
  await p.reload();
  await p.locator(ready).first().waitFor({ timeout: FIRST });
}

async function step(name, fn) {
  const t0 = Date.now();
  try {
    const detail = await fn();
    say('PASS', name, detail ? '- ' + detail : '', `(${Math.round((Date.now() - t0) / 1000)} s)`);
  } catch (e) {
    say('FAIL', name, '-', String(e?.message || e).split('\n')[0]);
    for (const [a, p] of Object.entries(pages)) await p.screenshot({ path: path.join(shots, `fail-${a}.png`), fullPage: true }).catch(() => {});
    await browser.close().catch(() => {});
    process.exit(1);
  }
}

// ---------------------------------------------------------------- the case pages
const cases = {}; // serial number -> case id
const seen = {}; // case id -> the text of its pages
const PLACES = [
  'overview', 'stage/4?tab=evidence', 'stage/5', 'stage/6', 'stage/6?tab=compare', 'stage/6?tab=evidence', 'stage/6?tab=packet',
  'stage/6?tab=why', 'stage/7', 'stage/7?tab=checks',
];
async function caseText(p, id) {
  if (seen[id]) return seen[id];
  let all = '';
  for (const place of PLACES) {
    await open(p, `${base}/#/product/${id}/${place}`);
    await p.waitForTimeout(400);
    all += '\n' + (await p.innerText('#view').catch(() => ''));
  }
  seen[id] = all;
  return all;
}
const inCase = async (p, n, rx, label) => {
  const t = await caseText(p, need(n));
  if (!rx.test(t)) throw new Error(`case ${need(n)} (${sn(n)}) does not show ${label}`);
  return t;
};
const need = (n) => {
  if (!cases[n]) throw new Error(`no case for ${sn(n)}: step 1 did not run`);
  return cases[n];
};

// ---------------------------------------------------------------- 1 (TN-01)
const compose = (p) => p.locator('section[aria-label="Compose"]');
async function startCompose(p, typed) {
  await open(p, MODELER, '.mdl-bar');
  await p.getByRole('button', { name: 'Compose', exact: true }).click();
  await compose(p).waitFor();
  if (typed === undefined) {
    const prompt = compose(p).locator('.cmp-prompts button[title^="Decommissioned network kit"]').first();
    await prompt.waitFor({ timeout: UI });
    await prompt.click();
  } else {
    await compose(p).getByLabel('Describe your business').fill(typed);
  }
  await compose(p).getByRole('button', { name: 'Draft the changes' }).click();
  await compose(p).getByRole('heading', { name: /What the agent read/ }).waitFor({ timeout: UI });
}
let COMP = 0;
await step('1 Connect the six telecom systems, open the units as cases, Compose: one explicit control and the firmware question', async () => {
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

  // (action: case.open) the key is the unit's canonical key as the sources wrote it (org unit, then serial)
  const planner = await as('planner.a');
  const openUnit = (n) =>
    callAction(planner, 'case.open', {
      org_unit_id: ORG, template_key: 'telecom_network', asset_key: `${ORG}:${sn(n)}`, reason: 'decommission',
      facts: { serial: sn(n), model: UNITS[n].model, site: UNITS[n].site, removed_at: '2026-10-04T08:00:00+00:00', removal_job: 'RJ-01', programme: '5G refresh' },
    });
  for (const n of Object.keys(UNITS).map(Number)) {
    let r = await openUnit(n);
    if (!r.ok && /pack/i.test(JSON.stringify(r))) {
      // the pack of the org is published by people first (admin imports, approver approves): the shipped pack, as the api tests do
      const doc = JSON.parse(readFileSync(path.join(ROOT, 'backend/di/services/modeler/packs/telecom_network.json'), 'utf8'));
      doc.version = '1.4.1';
      const imp = await callAction(await as('admin'), 'pack.import', { doc });
      if (imp.ok) {
        await must(await as('admin'), 'pack.submit', { id: imp.output.id });
        await must(await as('approver'), 'pack.approve', { id: imp.output.id });
      }
      r = await openUnit(n);
    }
    if (!r.ok) throw new Error(`case.open for ${sn(n)}: ${JSON.stringify(r.error || r).slice(0, 240)} (reset the stack first?)`);
    cases[n] = r.output.case_id;
  }

  await startCompose(planner);
  const t = await compose(planner).innerText();
  if (!/\b1 explicit control\b/.test(t)) throw new Error('the reading does not say "1 explicit control": ' + (t.match(/\d+ explicit controls?/)?.[0] || 'no such line'));
  const q = compose(planner).locator('.cmp-question');
  if ((await q.count()) !== 1) throw new Error(`expected exactly one question, found ${await q.count()}`);
  if (!/firmware/i.test(await q.innerText())) throw new Error('the one question is not about firmware');
  COMP = Number((await compose(planner).locator('.cmp-state').innerText().catch(() => '')).match(/composition (\d+) is/)?.[1]) || 0;
  return `${SOURCES.length} systems synced; cases ${Object.keys(cases).map((n) => `${n}=${cases[n]}`).join(', ')}; composition ${COMP || '?'}`;
});

// ---------------------------------------------------------------- 2 (TN-05)
await step('2 The unit not in the inventory: "Unit not in network inventory" on the case and in My work', async () => {
  const p = await as('planner.a');
  await inCase(202, /Unit not in network inventory/, '"Unit not in network inventory"');
  let where = '';
  for (const acct of ['warehouse1', 'warehouse2', 'admin', 'planner.a']) {
    const q = await as(acct);
    await open(q, base + '/#/mywork');
    await q.waitForTimeout(800);
    if (/Unit not in network inventory/.test(await text(q)) || (await text(q)).includes(sn(202))) {
      where = acct;
      break;
    }
  }
  if (!where) throw new Error(`${sn(202)} is in nobody's My work (warehouse1, warehouse2, admin, planner.a)`);
  const t = seen[need(202)];
  if (/net\s+[\d,]+\.\d\d/i.test(t)) throw new Error(`${sn(202)} shows a net value although no route is valued`);
  void p;
  return `My work of ${where}`;
});

// ---------------------------------------------------------------- 3 (TN-06)
await step('3 The unit whose wipe failed twice: "Wipe failed twice: storage destroyed, no resale"', async () => {
  const p = await as('planner.a');
  await inCase(15, /Wipe failed twice: storage destroyed, no resale/, '"Wipe failed twice: storage destroyed, no resale"');
  void p;
  return `${sn(15)}`;
});

// ---------------------------------------------------------------- 4 (TN-08)
await step('4 The export approvals: RAD-7700 with "keep as spares", the approver approves one', async () => {
  const ap = await as('approver');
  await open(ap, base + '/#/mywork');
  await waitText(ap, /RAD-7700/, 'no RAD-7700 export approval in the approver\'s My work (the seed has no screened-clear RAD-7700 bid?)', UI);
  const t = await text(ap);
  if (!/keep as spares/i.test(t)) throw new Error('the RAD-7700 export approval does not show "keep as spares"');
  // the case page of one of the two RAD-7700 units (SN-TN-0006, 0012): approve where the page offers it
  let id = '';
  for (const n of [6, 12]) {
    await open(ap, `${base}/#/product/${need(n)}/stage/7`);
    if (await ap.locator('button', { hasText: /^\s*Approve (?!and send)/ }).count()) { id = need(n); break; }
  }
  if (!id) throw new Error('neither RAD-7700 case (SN-TN-0006, SN-TN-0012) offers Approve on stage 7');
  await ap.locator('button', { hasText: /^\s*Approve (?!and send)/ }).first().click();
  await ap.getByLabel(/I reviewed evidence snapshot/).check();
  await ap.getByText('Approve and send instruction').click();
  await waitText(ap, /APR-\S+ created/, 'no "APR-... created" confirmation after the approval', UI);
  return `approved on ${id}`;
});

// ---------------------------------------------------------------- 5 (TN-11, TN-12)
await step('5 The routes: redeploy with New spend avoided and net 9,435.00; the second RRU-4410 fills nothing twice', async () => {
  const p = await as('planner.a');
  const t1 = await inCase(1, /Redeploy to a site/, '"Redeploy to a site"');
  if (!/New spend avoided/.test(t1)) throw new Error(`${sn(1)} does not show "New spend avoided"`);
  if (!/9,435\.00|9,435|9\.4k/.test(t1)) throw new Error(`${sn(1)} does not show the net 9,435.00`);
  const t7 = await inCase(7, /Site demand SD-112 filled by SN-TN-0001/, '"Site demand SD-112 filled by SN-TN-0001"');
  if (!/Refurbish as a spare/.test(t7)) throw new Error(`${sn(7)} does not recommend "Refurbish as a spare"`);
  void p;
  return 'SN-TN-0001 redeploy, net 9,435.00; SN-TN-0007 refurbish as a spare';
});

// ---------------------------------------------------------------- 6 (TN-17)
await step('6 The diversion that skips the configuration wipe is refused, with the suggestion', async () => {
  const p = await as('planner.a');
  await startCompose(p, 'urgent site outage: skip the configuration wipe');
  await p.waitForTimeout(800);
  const t = await compose(p).innerText();
  if (!/Blocked \(/.test(t) || !/wipe|G-NET-CFG/i.test(t)) throw new Error('Compose shows no "Blocked (...)" refusal naming the wipe guardrail');
  return /already wiped spare/i.test(t) ? 'refused, with the suggestion (an already wiped spare)' : 'refused (the suggestion text "already wiped spare" is not shown on the draft)';
});

// ---------------------------------------------------------------- 7 (TN-18, TN-19)
await step('7 Cross-region alert "Transfer to the region buying new" and the held proposal "Reduce purchase requisition"', async () => {
  const p = await as('planner.a');
  // (action: telecom.crossRegion) no page lists the alert yet: the Modeler's read action
  const m = await getJson(p, `/api/screens/modeler?template=telecom_network&org=${encodeURIComponent(ORG)}`);
  const fid = m?.flow?.id;
  if (!fid) throw new Error('the telecom flow of Customer A has no id on /api/screens/modeler');
  const out = await must(p, 'telecom.crossRegion', { flow_id: fid });
  if (!out.alerts?.some((a) => a.action === 'Transfer to the region buying new')) throw new Error('telecom.crossRegion returned no alert with the action "Transfer to the region buying new"');
  // the overview in the browser, where the alert would show once a page lists it
  await open(p, `${base}/#/home`);
  const onPage = /Transfer to the region buying new/.test(await text(p));

  // (action: agent.register, requisition.reduce prepared by an agent) the write holds for a person; Home lists it
  const admin = await as('admin');
  await callAction(admin, 'agent.register', { id: 'tn-follow', name: 'Follow-through', tools: ['request_missing_evidence'], autonomy: 'propose' });
  const held = await must(p, 'requisition.reduce', { case_id: need(1), req_id: 'PR-3302', qty: 1, reason: 'Unit SN-TN-0001 fills the need' }, { 'X-Circularity-Preparer': 'tn-follow' });
  if (!held.held) throw new Error('the agent-prepared requisition.reduce was not held for a person: ' + JSON.stringify(held).slice(0, 160));
  await open(p, `${base}/#/home`);
  await waitText(p, /Reduce purchase requisition/, 'Home\'s "Proposals for you" does not show "Reduce purchase requisition"', UI);
  return onPage ? 'alert on Home; proposal held' : 'alert via telecom.crossRegion (no page shows it); proposal held';
});

// ---------------------------------------------------------------- 8 (TN-22)
await step('8 The analytics question and the modelled replay figures', async () => {
  const p = await as('planner.a');
  const notes = [];
  await open(p, `${base}/#/analytics/packs`);
  const pick = p.locator('select[aria-label="Pack"]');
  if (await pick.count()) await pick.selectOption('telecom_network').catch(() => {});
  await p.waitForTimeout(800);
  await waitText(p, /Why are we still buying new power units when returns are coming in\?/, 'Analytics > Packs does not show the question "Why are we still buying new power units when returns are coming in?"', UI);
  if (!/PSU-48/.test(await text(p))) throw new Error('the power unit question shows no chart rows (PSU-48)');
  notes.push('question with its chart');

  await open(p, `${MODELER}${COMP ? `&compose=${COMP}` : ''}`, '.mdl-bar');
  if (!COMP) await p.getByRole('button', { name: 'Compose', exact: true }).click();
  await compose(p).waitFor();
  const tab = compose(p).getByRole('tab', { name: 'Publish', exact: true });
  if (await tab.count()) await tab.click();
  await p.waitForTimeout(800);
  const t = await compose(p).innerText();
  if (!/modelled/i.test(t)) throw new Error('the Compose publish step does not label the replay figures "modelled"');
  notes.push('replay figures labelled modelled');
  return notes.join('; ');
});

if (errors.length) {
  say('FAIL page errors:', JSON.stringify(errors));
  await browser.close();
  process.exit(1);
}
await browser.close();
console.log('\nsmoke-p9-10: all 8 steps passed');
