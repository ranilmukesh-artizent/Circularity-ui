/**
 * Plan 9, Phase 12 demo smoke (P9-12.12, stories NS-IT-01, NS-IT-02, NS-CPE-01, NS-BAT-02, NS-CORE-03, NS-MED-03, NS-MED-01, NS-B2C-02,
 * NS-RC-01, NS-IND-01): the next segments seen in the browser, one line per step (PASS, or FAIL with the step and what was missing, then
 * exit 1 at once). Chrome through Playwright, every check through the UI unless the line says "(action: ...)": the reads and the clicks
 * the app has no control for yet (registering an extra system, publishing a pack, opening a case from the mocks' data, the standing
 * policy, the mocks' own clock) use the app's own action call or the mock's API.
 *
 *   1  developer registers and connects it_cmdb, it_logistics, rf_rental, cpe_bss, bat_bms, core_ret, mc_tradein and b2c_ret for
 *      Customer A and runs their syncs (action: source.reconnect, source.sync; the shipped packs are published first, action:
 *      pack.import/submit/approve). My work lists "Serial on the manifest not received" (the two serials of PU-01 that never
 *      arrived). The case of SN-IT-0017 (a desktop with an SSD and no erasure record) shows "Sanitisation record missing for media".
 *   2  The CPE lot LOT-R7-B-W47 (500 routers) is approved by the standing policy ("approved by policy"); LOT-R7-B-W48 (900) waits in
 *      the approver's My work (action: standingPolicy.save/submit/approve, case.open, decision.submit).
 *   3  The used car of VIN SYNUC000000000044 (its pack needs replacing) opens a battery case linked from it; the battery case shows
 *      "Battery passport not yet required (from 18 Feb 2027, indicative)" (action: the car's case.open; the battery assessment
 *      is asked of the inspection mock and its clock moves one day, then uc_insp syncs).
 *   4  The core C-0004 (declared an alternator, a starter arrived) is held for fraud review; approver releases it with a reason
 *      on the case page (action: case.open).
 *   5  A medical capital device for another market with no UDI (SYN-MC-0005) shows "UDI missing"; engineer records the assessment
 *      "servicing" on its case page (Record assessment) (action: case.open).
 *   6  An unsold jacket (RET-0004) shows "Destruction of unsold apparel and footwear is banned; reuse, donation or recycling first"
 *      (action: case.open).
 *   7  The rental fleet's excavator M-0001 (sample RF-S1) recommends Re-rent at net 27,600.00 (action: case.open).
 *   8  RT-1048's case shows the recommendation and net it has in fixtures/golden/cases.json (nothing moved since the demo).
 *
 * Needs the worker (syncs, case jobs) and source-sim (the mocks and its clock). No vendor product is claimed connected: every system is
 * synthetic. Changes state (the sim clock moves one day in step 3). The lead runs it, holding the api test lock meanwhile:
 *   bash scripts/dev/reset.sh && bash scripts/dev/wait-idle.sh
 *   node frontend/scripts/smoke-p9-12.mjs http://localhost:5173
 *   bash scripts/dev/reset.sh
 * It resets nothing itself. Screenshots of a failing step go to SMOKE_SHOTS (default: <OS temp>/smoke-p9-12). SIM_URL / SIM_PORT name
 * source-sim. The last line is "smoke-p9-12: all 8 steps passed".
 */
import { chromium } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const SIM = process.env.SIM_URL || `http://localhost:${process.env.SIM_PORT || 8100}`;
const shots = process.env.SMOKE_SHOTS || path.join(tmpdir(), 'smoke-p9-12');
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const ORG = 'Customer A';
const SOURCES = ['it_cmdb', 'it_logistics', 'rf_rental', 'cpe_bss', 'bat_bms', 'core_ret', 'mc_tradein', 'b2c_ret'];
const CAR_SOURCES = ['uc_lease', 'uc_title', 'uc_insp', 'uc_recall', 'uc_dms', 'uc_price', 'uc_auction'];
const PACKS = { itad: '1.9.11', telecom_cpe: '1.9.12', battery: '1.9.13', auto_core: '1.9.14', used_cars: '1.9.15', medical_capital: '1.9.16', b2c_serial: '1.9.17', rental_fleet: '1.9.18' };
const POLICY = { max_value: 20000, min_confidence: 0.75, routes: ['refurbish_redeploy'] }; // "lots under $20,000" (the 500-router lot is worth 15,500)
const BAN = 'Destruction of unsold apparel and footwear is banned; reuse, donation or recycling first';
const NOT_YET = 'Battery passport not yet required (from 18 Feb 2027, indicative)';
const VIN44 = 'SYNUC000000000044';
const UI = 400000; // the dev stack answers slowly while the worker syncs and other stacks share the machine
const FIRST = 400000; // a first page load after sign-in
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
  await p.locator('#view').first().waitFor({ timeout: FIRST }); // the post-sign-in redirect lands first, or a goto right after races it
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
  await p.goto(url);
  await p.reload();
  await p.locator(ready).first().waitFor({ timeout: FIRST });
}
const sim = (route, body, headers = {}) =>
  fetch(SIM + route, { method: 'POST', headers: { 'content-type': 'application/json', ...headers }, body: JSON.stringify(body) });

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
/** The text of the places a case shows what a person reads: Overview, the stages and their tabs (read fresh, once per case). */
const PLACES = [
  'overview', 'stage/2', 'stage/3', 'stage/4', 'stage/4?tab=evidence', 'stage/5', 'stage/6', 'stage/6?tab=compare', 'stage/6?tab=evidence',
  'stage/6?tab=packet', 'stage/6?tab=why', 'stage/7', 'stage/7?tab=checks', 'stage/8',
];
const seen = {}; // case id -> the text of its pages
async function caseText(p, id, fresh = false) {
  if (!fresh && seen[id]) return seen[id];
  let all = '';
  for (const place of PLACES) {
    await open(p, `${base}/#/product/${id}/${place}`);
    await p.waitForFunction(() => { const t = document.querySelector('#view')?.innerText || ''; return t.trim() !== '' && !/^Loading...$/.test(t.trim()); }, null, { timeout: 60000 }).catch(() => {}); // the page can still say Loading... on a busy stack
    await p.waitForTimeout(400);
    all += '\n' + (await p.innerText('#view').catch(() => ''));
  }
  seen[id] = all;
  return all;
}
const inCase = async (p, id, rx, label, fresh) => {
  const t = await caseText(p, id, fresh);
  if (!rx.test(t)) throw new Error(`case ${id} does not show ${label}`);
  return t;
};
const caseOf = async (p, id) => (await getJson(p, '/api/screens/case/' + encodeURIComponent(id))).case;
const money = (n) => Number(n).toLocaleString('en-US'); // 9600 -> "9,600"

/** Open a case as planner.a (action: case.open). */
async function openCase(template_key, asset_key, reason, facts) {
  const planner = await as('planner.a');
  return (await must(planner, 'case.open', { org_unit_id: ORG, template_key, asset_key, reason, facts })).case_id;
}
const serialKey = (s) => `${ORG}:${s}`; // schema.serial_key / tag_key / vin_key: `<org unit>:<id>`
const pack = (file) => JSON.parse(readFileSync(path.join(ROOT, 'backend/di/services/modeler/packs', file + '.json'), 'utf8'));
async function syncAll(dev, ids) {
  for (const sid of ids) await must(dev, 'source.reconnect', { source_id: sid }); // (action) registers an extra system, then connects it
  for (const sid of ids) await must(dev, 'source.sync', { source_id: sid });
  for (const sid of ids) {
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
}

// ---------------------------------------------------------------- 1
await step('1 Connect the eight systems; My work lists "Serial on the manifest not received"; an SSD without a record names its media', async () => {
  const dev = await as('developer');
  // the shipped packs, published as the org's (admin imports and submits, approver approves); one already published is left as it is
  const admin = await as('admin');
  const approver = await as('approver');
  for (const [key, version] of Object.entries(PACKS)) {
    const doc = pack(key);
    doc.version = version;
    const imp = await callAction(admin, 'pack.import', { doc });
    if (!imp.ok) continue;
    await must(admin, 'pack.submit', { id: imp.output.id });
    await must(approver, 'pack.approve', { id: imp.output.id });
  }
  await syncAll(dev, SOURCES);
  await open(dev, base + '/#/integration/overview', 'tr[data-int]');
  for (const sid of SOURCES) await dev.locator(`tr[data-int="${sid}"]`).first().waitFor({ timeout: UI });

  // the end of the it_logistics sync (job case.recordMatch) opens one critical item for each serial of the manifest that did not arrive
  let where = '';
  for (const acct of ['warehouse1', 'warehouse2', 'admin', 'planner.a', 'approver', 'ops']) {
    const q = await as(acct);
    for (let k = 0; k < 6 && !where; k++) {
      await open(q, base + '/#/mywork');
      await q.waitForTimeout(4000); // My work reads about 160 items: 800 ms is before it draws
      if (/Serial on the manifest not received/.test(await text(q))) where = acct;
      else await q.waitForTimeout(4000); // the job runs after the sync
    }
    if (where) break;
  }
  if (!where) throw new Error('"Serial on the manifest not received" is in nobody\'s My work (warehouse1, warehouse2, admin, planner.a, approver, ops)');

  // SN-IT-0017 never arrived and has no erasure record: its desktop's SSD is named (opening it closes its missing item, so this comes second)
  const id = await openCase('itad', serialKey('SN-IT-0017'), 'lease_end', { serial: 'SN-IT-0017' });
  const p = await as('planner.a');
  await inCase(p, id, /Sanitisation record missing for media/, '"Sanitisation record missing for media ..."');
  return `${SOURCES.length} systems synced; My work of ${where}; case ${id}`;
});

// ---------------------------------------------------------------- 2
await step('2 The CPE lot of 500 is "approved by policy"; the lot of 900 waits in the approver\'s My work', async () => {
  const admin = await as('admin');
  const approver = await as('approver');
  const pol = await must(admin, 'standingPolicy.save', { pack: 'telecom_cpe', org_unit_id: ORG, name: 'Lots under $20,000', rules: POLICY, owner: 'admin' });
  await must(admin, 'standingPolicy.submit', { id: pol.id });
  await must(approver, 'standingPolicy.approve', { id: pol.id });
  const small = await openCase('telecom_cpe', serialKey('LOT-R7-B-W47'), 'rma', {});
  const big = await openCase('telecom_cpe', serialKey('LOT-R7-B-W48'), 'rma', {});
  await must(admin, 'decision.submit', { case_id: small });
  await must(admin, 'decision.submit', { case_id: big });
  const p = await as('planner.a');
  await inCase(p, small, /approved by policy/i, '"approved by policy"', true);
  await open(approver, base + '/#/mywork');
  await waitText(approver, new RegExp(`${big}|LOT-R7-B-W48`), `the lot of 900 (${big}) is not in the approver's My work`, UI);
  const t = await caseText(p, big, true);
  if (/approved by policy/i.test(t)) throw new Error(`the lot of 900 (${big}) was approved by policy: it must wait for a person`);
  return `${small} approved by policy ${pol.id}; ${big} waits for the approver`;
});

// ---------------------------------------------------------------- 3
let BATTERY = '';
await step(`3 The battery case linked from VIN ...044 shows "${NOT_YET}"`, async () => {
  const dev = await as('developer');
  await syncAll(dev, CAR_SOURCES);
  const car = await openCase('used_cars', serialKey(VIN44), 'lease_end', { vin: VIN44, mileage: 38000, return_date: '2026-10-03' });
  // the car's battery assessment: asked of the inspection mock, done a simulated day later; the next uc_insp sync values the car again
  const made = await sim('/vehicle-inspection/api/battery-assessments', { vin: VIN44 }, { 'x-api-key': 'uc_insp-demo-key', 'Idempotency-Key': 'smoke-p9-12-44' });
  if (!made.ok) throw new Error(`the inspection mock refused the battery assessment of ${VIN44}: ${made.status}`);
  await sim('/_sim/clock/advance', { days: 1 });
  const p = await as('planner.a');
  BATTERY = await until(
    async () => {
      await must(dev, 'source.sync', { source_id: 'uc_insp' });
      await p.waitForTimeout(5000);
      const c = await caseOf(p, car);
      return (c.linked || []).find((x) => x.template === 'battery')?.case || null;
    },
    `the used car ${car} (${VIN44}) opened no battery case after its assessment`,
    SYNC,
    p,
  );
  await inCase(p, BATTERY, new RegExp(NOT_YET.replace(/[().]/g, '\\$&')), `"${NOT_YET}"`, true);
  return `car ${car} -> battery case ${BATTERY}`;
});

// ---------------------------------------------------------------- 4
await step('4 A core with a family mismatch is held; approver releases it with a reason', async () => {
  // C-0004: declared ALT-1450, a starter (STR-2210) arrived: the signal part_family_mismatch of the core returns system (core_ret)
  const id = await openCase('auto_core', serialKey('C-0004'), 'manual', { family: 'alternator', deposit: 85 });
  const p = await as('planner.a');
  await until(
    async () => {
      await open(p, `${base}/#/product/${id}/overview`);
      return /Held for fraud review/.test(await text(p));
    },
    `the core ${id} (C-0004) is not held for fraud review (no "Held for fraud review" banner on its Overview)`,
    SYNC,
    p,
  );
  if (!/part_family_mismatch/.test(await p.innerText('[data-testid="fraud-hold"]'))) throw new Error('the hold does not name the signal part_family_mismatch');
  const ap = await as('approver'); // fraud.release needs approve.decisions: planner.a only sees the hold
  await open(ap, `${base}/#/product/${id}/overview`);
  await ap.locator('#fraud-reason').fill('Checked the photos with the dealer; the part is the declared one.');
  await ap.getByRole('button', { name: 'Release', exact: true }).click();
  await waitText(ap, new RegExp(`${id} released from fraud review`), 'no "released from fraud review" confirmation', UI);
  const c = await caseOf(ap, id);
  if (c.fraud?.status !== 'released') throw new Error(`the hold of ${id} is "${c.fraud?.status}", not released`);
  return `${id} held (part_family_mismatch), seen by planner.a, released by approver`;
});

// ---------------------------------------------------------------- 5
await step('5 A device for another market with no UDI shows "UDI missing"; engineer records the assessment "servicing"', async () => {
  // SYN-MC-0005: a patient monitor of the US register, no UDI; to be sold in the EU
  const facts = {
    tag: 'SYN-MC-0005', cls: 'infusion_pump', age_years: 4, resale_price: 4000, refurb_cost: 1200, parts_value: 500, single_use: false,
    origin_market: 'US', target_market: 'EU', service_record_ref: 'SR-0005', recalls_closed: true,
  };
  const id = await openCase('medical_capital', serialKey('SYN-MC-0005'), 'trade_in', facts);
  const p = await as('planner.a');
  await inCase(p, id, /UDI missing/, '"UDI missing"');
  const eng = await as('engineer');
  let found = false;
  for (const place of PLACES) {
    await open(eng, `${base}/#/product/${id}/${place}`);
    if (await eng.getByRole('button', { name: 'Record assessment', exact: true }).count()) {
      found = true;
      break;
    }
  }
  if (!found) throw new Error(`no "Record assessment" button on the pages of ${id} for engineer`);
  await eng.getByRole('button', { name: 'Record assessment', exact: true }).first().click();
  const dlg = eng.getByRole('dialog');
  await dlg.getByRole('heading', { name: /Record assessment/ }).first().waitFor({ timeout: UI });
  await dlg.getByLabel(/Planned work/i).fill('Battery and seal replacement');
  await dlg.getByLabel('Outcome').selectOption('servicing'); // its label is "Servicing"
  await dlg.getByLabel('Reason').fill('Replace the battery and the housing seals; no change to intended use or performance.');
  await dlg.getByRole('button', { name: 'Save assessment', exact: true }).click();
  await waitText(eng, new RegExp(`Assessment recorded for ${id}: Servicing.`), 'no toast "Assessment recorded for <id>: Servicing."', UI);
  const rec = eng.locator('[data-testid="assessment-recorded"]');
  await rec.first().waitFor({ timeout: UI });
  if (!/Servicing, recorded by engineer/.test(await rec.first().innerText())) throw new Error('the assessment bar does not say "Servicing, recorded by engineer"');
  return `${id}: "UDI missing"; assessment servicing recorded by engineer`;
});

// ---------------------------------------------------------------- 6
await step('6 An unsold jacket: "Destruction of unsold apparel and footwear is banned; ..."', async () => {
  // RET-0004: JK-221-M, unsold, no exception evidence (the ban is the portal's own record, no named retailer)
  const facts = { itemId: 'RET-0004', serial: 'SN-B2C-0004', imei: null, itemClass: 'apparel', sku: 'JK-221-M', unsold: true, exceptionEvidence: null, ref: 80, qty: 1 };
  const id = await openCase('b2c_serial', 'SN-B2C-0004', 'rma', facts);
  const p = await as('planner.a');
  await inCase(p, id, new RegExp(BAN.replace(/[;,]/g, '[;,]')), `"${BAN}"`);
  return `case ${id}`;
});

// ---------------------------------------------------------------- 7
await step('7 The rental fleet excavator recommends Re-rent at net 27,600.00', async () => {
  // M-0001: the pack's own replay sample RF-S1 (facts "model.field" -> the nested case the valuer reads), as the api tests open it
  const sample = pack('rental_fleet').replay.example.samples.find((s) => s.id === 'RF-S1');
  const facts = { cls: sample.facts['asset.asset_class'] };
  for (const [k, v] of Object.entries(sample.facts)) {
    const [model, field] = k.split('.');
    (facts[model] ||= {})[field] = v;
  }
  const id = await openCase('rental_fleet', serialKey('M-0001'), 'rental_return', facts);
  const p = await as('planner.a');
  const t = await inCase(p, id, /Re-rent/, '"Re-rent"');
  if (!/27,600(\.00)?/.test(t)) throw new Error(`case ${id} (M-0001) does not show the net 27,600.00`);
  const c = await caseOf(p, id);
  if (c.recommendation?.id !== 'rerent') throw new Error(`case ${id} recommends "${c.recommendation?.id}", not rerent`);
  return `case ${id} recommends Re-rent`;
});

// ---------------------------------------------------------------- 8
await step('8 RT-1048 shows the recommendation and net of the demo', async () => {
  const gold = JSON.parse(readFileSync(path.join(ROOT, 'fixtures/golden/cases.json'), 'utf8')).find((c) => c.id === 'RT-1048');
  const rec = gold.recommendation;
  const p = await as('planner.a');
  const t = await caseText(p, 'RT-1048', true);
  if (!t.includes(rec.plan)) throw new Error(`RT-1048 does not show its recommendation "${rec.plan}"`);
  if (!t.includes(money(rec.net))) throw new Error(`RT-1048 does not show its net ${money(rec.net)}`);
  const c = await caseOf(p, 'RT-1048');
  if (c.recommendation?.id !== rec.id) throw new Error(`RT-1048 recommends "${c.recommendation?.id}", the demo "${rec.id}"`);
  return `${rec.plan}, net ${money(rec.net)}`;
});

if (errors.length) {
  say('FAIL page errors:', JSON.stringify(errors));
  await browser.close();
  process.exit(1);
}
await browser.close();
console.log('\nsmoke-p9-12: all 8 steps passed');
