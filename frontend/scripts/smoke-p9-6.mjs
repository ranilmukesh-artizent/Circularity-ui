/**
 * Plan 9, Phase 6 demo smoke (P9-6): device recommerce, one line per step (PASS, or FAIL with the step and the text that
 * was missing, then exit 1 at once). Every step reads what a person sees on the page (tabs, cards, panels) and presses the
 * page's own controls (tabs, Build lots, Propose, Accept, Fit price model, Approve, Confirm the outcome). A control that is
 * missing fails the step; no step replaces one with an API call. The only calls outside the pages are SETUP that has no
 * control: registering and binding the three mocks (`source.reconnect`, `source.update`, `source.sync`, as smoke-p9-4 does),
 * opening the 40 devices of BATCH-0007 one by one (`case.open`: the mock marks that batch bulk, which opens one ungated lot
 * case), and what the outside world does (a wipe certificate, buyers' bids, the simulated clock).
 *
 *   1  Admin registers `dvreg`, `dvlab` and `dvmkt` and syncs them (market first without its sales, then the lab, which opens
 *      the cases, then the sales, so a sale lands after its case exists). Cases open for the lab's trade-ins.
 *   2  The case of IMEI 359990000000428 (iPhone 14, 128 GB) shows the Device tab: "quote $410", "partner P01".
 *   3  Its Quote and Compliance tabs pass; the blacklisted 359990000000219 waits for Compliance; the P02 device
 *      359990000000043 shows "Diversion: second grading check (partner P02)".
 *   4  The sample's Payout tab reads "$410 → $385.40 (−6%)"; BATCH-0007 shows "12 of 40 waiting" for wipe certificates; a
 *      certificate posted in the lab mock releases one case ("11 of 40 waiting" on another).
 *   5  The sample's Channels tab lists Buy Now, Offers, Auction and Wholesale lot with P10 to P90 and "feed 5 Oct 2026", the
 *      repair line "battery swap +$28 price, −$24 cost, +5 days" and the Replacement stock row; 359990000000051 (parts
 *      status unknown) reads "No genuine-parts declaration (GR-D9)".
 *   6  Admin fits a device price model in the Models panel and proposes it; the row shows MAE, the interval coverage, the
 *      proposal and "Shadow: n of 30 evaluations"; the Approver's Approve button says why it waits for the shadow.
 *   7  My work: planner.a builds the wholesale lots, buyers' bids reach the market (the mock), the lot shows the dropped B05
 *      bid, is proposed above $25,000 and waits for the Approver (owner "Commercial manager").
 *   8  A Buy Now case is submitted by planner.a and approved by the Approver; the listing reaches the market; a seeded sale
 *      of its IMEI settles it (Settlement tab); only time moves; Finance confirms the outcome.
 *   9  My work: "Move 12 Offers listings to Auction: 14 days, no offer"; planner.a accepts it into the draft.
 *  10  Analytics, Packs, Questions: both device questions answer with a chart, the sentence and example records.
 *
 * Needs the worker (syncs, instructions) and source-sim with the three device mocks (restart it after a change). Changes
 * state, and resets nothing itself. The lead runs:
 *   bash scripts/dev/reset.sh && bash scripts/dev/wait-idle.sh
 *   node frontend/scripts/smoke-p9-6.mjs http://localhost:5173
 *   bash scripts/dev/reset.sh
 * (hold the api test lock meanwhile). The app's clock must be the simulated one at 2026-10-07 (the mocks' as-of date).
 * Screenshots of a failing step go to SMOKE_OUT (default: <OS temp>/smoke-p9-6).
 * The last line is "smoke-p9-6: all <N> steps passed", N being the number of steps that ran.
 */
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const SIM = process.env.SIM_URL || `http://localhost:${process.env.SIM_PORT || 8100}`;
const out = process.env.SMOKE_OUT || path.join(tmpdir(), 'smoke-p9-6');
const ORG = 'Customer A';
const SOURCES = ['dvreg', 'dvlab', 'dvmkt'];
const SAMPLE = '359990000000428'; // iPhone 14, 128 GB, grade B, quote $410, partner P01, battery 84%
const BLACKLISTED = '359990000000219'; // reported stolen, not in a bulk batch
const P02 = '359990000000043'; // iPhone 15, partner P02, clean registry, wiped
const NO_PARTS = '359990000000051'; // parts declaration "unknown", clean registry
const BATCH = 'BATCH-0007';
const BATCH_FIRST = 240; // BATCH-0007 holds the devices 240 to 279 (i // 40 + 1 == 7); 12 of them have no wipe certificate
const UNWIPED = ['272', '247', '250', '267', '246', '251', '242', '260', '261', '279', '269', '277'].map((n) => `3599900000${n.padStart(5, '0')}`);
const MKT = SIM + '/device-market/v1';
const LAB = SIM + '/device-lab/v1';
const UI = 30000;
const SYNC = 240000;
mkdirSync(out, { recursive: true });

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
  await p.waitForURL((u) => !/signin/.test(u.hash), { timeout: UI });
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
const getJson = (p, url) =>
  p.evaluate(
    async (url) => (await fetch(url, { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('circ-api-token') } })).json(),
    url,
  );
const must = async (p, id, body) => {
  const r = await callAction(p, id, body);
  if (!r.ok) throw new Error(`${id}: ${JSON.stringify(r.error || r).slice(0, 200)} (reset the stack first?)`);
  return r.output;
};
const until = async (fn, msg, ms, p) => {
  const end = Date.now() + ms;
  for (;;) {
    const v = await fn().catch(() => null);
    if (v) return v;
    if (Date.now() > end) throw new Error(msg);
    await p.waitForTimeout(1000);
  }
};
const deep = (o, pred) => {
  if (o && typeof o === 'object') {
    if (!Array.isArray(o) && pred(o)) return o;
    for (const v of Object.values(o)) {
      const f = deep(v, pred);
      if (f) return f;
    }
  }
  return null;
};

// ---- the outside world (the mocks): what a buyer, the lab or the market does, never a way around a page
const mock = async (url, init = {}) => {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error(`${init.method || 'GET'} ${url}: ${r.status} ${(await r.text()).slice(0, 160)} (are the device mocks served? restart source-sim)`);
  return r.json();
};
const mkt = (p, init) => mock(MKT + p, { ...init, headers: { 'X-Api-Key': 'dvmkt-demo-key', 'content-type': 'application/json', ...(init?.headers || {}) } });
const labToken = async () =>
  (await mock(LAB + '/oauth/token', {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: 'grant_type=client_credentials&client_id=di-connector&client_secret=dvlab-demo-secret',
  })).access_token;
const advance = (hours) => mock(SIM + '/_sim/clock/advance', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ hours }) });

// ---- sources: setup the pages have no control for
const sourceOf = async (p, sid) => deep(await getJson(p, '/api/screens/integration/sources/' + encodeURIComponent(sid)), (o) => o.id === sid && 'method' in o);
const lastRun = async (p, sid) => (await getJson(p, '/api/screens/integration/sources/' + encodeURIComponent(sid)))?.sync_history?.[0] || null;
async function syncAndWait(p, sid) {
  const before = JSON.stringify(await lastRun(p, sid));
  await must(p, 'source.sync', { source_id: sid });
  return until(
    async () => {
      const h = await lastRun(p, sid);
      return h && JSON.stringify(h) !== before && h.ok ? h : null;
    },
    `${sid} did not finish a sync`,
    SYNC,
    p,
  );
}
/** Limit what a source's published ingest workflow reads (conn.cfg.resources), as smoke-p9-3 does for the fleet source. */
async function readOnly(p, sid, resources) {
  const wf = readOnly.wf[sid] || (readOnly.wf[sid] = await must(p, 'workflow.create', { type: 'ingest', src: sid }));
  const w = (await getJson(p, '/api/screens/workflows/' + encodeURIComponent(wf.id))).workflow;
  const g = JSON.parse(JSON.stringify(w.graph));
  const conn = g.nodes.find((n) => n.k === 'conn');
  conn.cfg = { ...(conn.cfg || {}), resources, mode: 'full' };
  await must(p, 'workflow.save', { id: wf.id, name: w.name, owner: w.owner, trig: w.trig, graph: g });
  await must(p, 'workflow.publish', { id: wf.id });
}
readOnly.wf = {};

// ---- cases
const caseOf = async (p, key) => {
  const r = await must(p, 'cases.list', { q: key, limit: 5 });
  return (r.rows || []).find((x) => x.id)?.id || null;
};
const caseScreen = async (p, id) => (await getJson(p, '/api/screens/case/' + encodeURIComponent(id))).case;
const needCase = async (p, imei) => {
  const id = await until(() => caseOf(p, imei), `no case for IMEI ${imei} (step 1 did not open it: is the device flow published for ${ORG}?)`, UI, p);
  return id;
};
/** The text of one detail tab of a stage page, opened with the tab's own button (a missing tab fails the step). */
async function tabText(p, id, stage, key, label) {
  await p.goto(`${base}/#/product/${id}/stage/${stage}`);
  await p.locator('#view').waitFor();
  const tab = p.locator(`[role="tab"]#stt-${key}`);
  await tab.waitFor({ timeout: UI }).catch(() => {
    throw new Error(`case ${id} stage ${stage} has no "${label}" tab`);
  });
  await tab.click();
  const panel = p.locator(`#stp-${key} [role="tabpanel"]`);
  await panel.waitFor({ timeout: UI });
  await p.waitForTimeout(400);
  return panel.innerText();
}
const tabHas = async (p, id, stage, key, label, rx, what) => {
  let t = '';
  await until(
    async () => {
      t = await tabText(p, id, stage, key, label);
      return rx.test(t);
    },
    `the "${label}" tab of case ${id} does not show ${what}`,
    UI,
    p,
  ).catch((e) => {
    throw new Error(`${e.message}: ${t.replace(/\s+/g, ' ').slice(0, 220)}`);
  });
  return t;
};

let stepsRun = 0;
async function step(name, fn) {
  stepsRun += 1;
  const t0 = Date.now();
  try {
    const detail = await fn();
    say('PASS', name, detail ? '· ' + detail : '', `(${Math.round((Date.now() - t0) / 1000)} s)`);
  } catch (e) {
    say('FAIL', name, '·', String(e?.message || e).split('\n')[0]);
    for (const [a, p] of Object.entries(pages)) await p.screenshot({ path: path.join(out, `fail-${a}.png`), fullPage: true }).catch(() => {});
    await browser.close().catch(() => {});
    process.exit(1);
  }
}

// ---------------------------------------------------------------- 1
await step('1 Sources: dvreg, dvlab and dvmkt registered and synced, the device cases open', async () => {
  const admin = await as('admin');
  const dev = await as('developer');
  for (const sid of SOURCES) await must(dev, 'source.reconnect', { source_id: sid }); // (action) registers an extra system, then connects it
  // trade-ins and listings belong to an org unit (a trade-in of a source bound to none stays pending): bind the lab and the market
  for (const sid of ['dvlab', 'dvmkt']) {
    const src = await until(() => sourceOf(dev, sid), `${sid} is not registered`, UI, dev);
    const d = {
      type: src.type, name: src.name, vendor: src.vendor, ver: src.ver, env: src.env, url: src.url, method: src.method,
      cfg: { ...(src.cfg || {}) }, interval: src.interval, auth: src.auth, owner: src.owner,
    };
    const maps = (src.mappings || []).filter(Array.isArray);
    await must(admin, 'source.update', { mode: 'edit', id: sid, d, maps, ops: { read: src.read || [], write: src.write || [] }, note: '', org_unit_id: ORG });
  }
  await syncAndWait(dev, 'dvreg'); // the registry first: a device with no registry check is held
  await readOnly(dev, 'dvmkt', ['prices', 'launches', 'listings', 'bids', 'replacementDemand']); // the feed before the cases; sales after them
  await syncAndWait(dev, 'dvmkt');
  await syncAndWait(dev, 'dvlab'); // its post-sync hook opens one case per received device (and one lot case per bulk batch)
  await readOnly(dev, 'dvmkt', ['sales']);
  await syncAndWait(dev, 'dvmkt'); // a sale new to us settles the cases it names: they exist now
  await readOnly(dev, 'dvmkt', ['prices', 'launches', 'listings', 'bids', 'sales', 'replacementDemand']);
  const id = await needCase(admin, SAMPLE);
  const rows = await must(admin, 'cases.list', { q: 'IMEI:', limit: 1000 });
  return `sample case ${id}; ${(rows.rows || []).length} IMEI cases listed`;
});

// ---------------------------------------------------------------- 2
await step('2 Device tab: the sample IMEI shows quote $410 and partner P01', async () => {
  const admin = await as('admin');
  const id = await needCase(admin, SAMPLE);
  const t = await tabHas(admin, id, 5, 'device', 'Device', /iPhone 14 · 128 GB · declared B · quote \$410 · partner P01/, '"iPhone 14 · 128 GB · declared B · quote $410 · partner P01"');
  if (!new RegExp(`IMEI\\s*${SAMPLE}`).test(t)) throw new Error('the Device tab does not show the IMEI ' + SAMPLE);
  return `${id}: ` + t.split('\n').find((l) => /quote \$410/.test(l));
});

// ---------------------------------------------------------------- 3
await step('3 Quote and Compliance pass; the blacklisted device waits for Compliance; the P02 device shows its diversion', async () => {
  const admin = await as('admin');
  const id = await needCase(admin, SAMPLE);
  await tabHas(admin, id, 5, 'quote', 'Quote', /Quote matches the device read/, '"Quote matches the device read"');
  const c = await tabHas(admin, id, 5, 'compliance', 'Compliance', /Registry: clear/, '"Registry: clear"');
  if (!/Data wipe: .*verified/.test(c)) throw new Error('the Compliance tab does not show a verified wipe certificate: ' + c.replace(/\s+/g, ' ').slice(0, 200));
  const bad = await needCase(admin, BLACKLISTED);
  await tabHas(admin, bad, 5, 'compliance', 'Compliance', /Registry: reported[ _]stolen/, '"Registry: reported stolen"');
  await tabHas(admin, bad, 5, 'compliance', 'Compliance', /Waiting for Compliance/, '"Waiting for Compliance"');
  const p02 = await needCase(admin, P02);
  await tabHas(admin, p02, 5, 'device', 'Device', /Diversion: second grading check \(partner P02\)/, '"Diversion: second grading check (partner P02)"');
  return `${id} passes; ${bad} waits for Compliance; ${p02} has the second grading check`;
});

// ---------------------------------------------------------------- 4
await step('4 Payout and wipe: $410 -> $385.40 (-6%); BATCH-0007 waits for 12 of 40 certificates; one posted certificate releases a case', async () => {
  const admin = await as('admin');
  const id = await needCase(admin, SAMPLE);
  await tabHas(admin, id, 5, 'payout', 'Payout', /\$410 → \$385\.40 \(−6%\)/, '"$410 → $385.40 (−6%)"');
  // the mock marks BATCH-0007 bulk, so the sync opened one ungated lot case: open its 40 devices one by one (case.open, no control)
  const planner = await as('planner.a');
  for (let i = BATCH_FIRST; i < BATCH_FIRST + 40; i++) {
    const imei = `3599900000${String(i).padStart(5, '0')}`;
    if (await caseOf(admin, imei)) continue;
    await must(planner, 'case.open', { org_unit_id: ORG, template_key: 'device', asset_key: `IMEI:${imei}`, reason: 'trade_in', facts: { imei } });
  }
  const waitingText = /Waiting for the wipe certificate \(batch BATCH-0007: (\d+) of 40 waiting\)/;
  const a = await needCase(admin, UNWIPED[0]);
  const t0 = await tabHas(admin, a, 5, 'compliance', 'Compliance', waitingText, '"Waiting for the wipe certificate (batch BATCH-0007: 12 of 40 waiting)"');
  if (waitingText.exec(t0)[1] !== '12') throw new Error('the batch shows ' + waitingText.exec(t0)[0] + ', not 12 of 40');
  // the lab's wipe tool posts a certificate for one device; the event queues a delta sync of dvlab (the case releases on its own)
  const token = await labToken();
  await mock(LAB + '/wipes', {
    method: 'POST',
    headers: { 'content-type': 'application/json', Authorization: 'Bearer ' + token },
    body: JSON.stringify({ imei: UNWIPED[0], method: 'Purge', toolVersion: '4.2.1', verification: 'pass', operator: 'OP-77', at: '2026-10-07T09:30:00+00:00' }),
  });
  const dev = await as('developer');
  let nudged = false;
  const t1 = await until(
    async () => {
      const t = await tabText(admin, a, 5, 'compliance', 'Compliance');
      if (/Data wipe: Purge · tool 4\.2\.1 · verified · operator OP-77/.test(t)) return t;
      if (!nudged) {
        nudged = true;
        await must(dev, 'source.sync', { source_id: 'dvlab' }); // the webhook may not reach a dev stack: the same delta sync by hand
      }
      return null;
    },
    `the case of ${UNWIPED[0]} is not released by its certificate OP-77`,
    SYNC,
    admin,
  );
  const b = await needCase(admin, UNWIPED[1]);
  await tabHas(admin, b, 5, 'compliance', 'Compliance', /Waiting for the wipe certificate \(batch BATCH-0007: 11 of 40 waiting\)/, '"11 of 40 waiting" for another device of the batch');
  return `${a} released (${t1.split('\n').find((l) => /Data wipe/.test(l))}); ${b} still waits, 11 of 40`;
});

// ---------------------------------------------------------------- 5
await step('5 Channels: Buy Now, Offers, Auction, Wholesale lot with P10-P90 and the feed week; the repair line; replacement stock; GR-D9', async () => {
  const admin = await as('admin');
  const id = await needCase(admin, SAMPLE);
  const t = await tabHas(admin, id, 6, 'channels', 'Channels', /Buy Now · /, 'the channel rows');
  const rows = t.split('\n').map((l) => l.trim());
  for (const name of ['Buy Now', 'Offers', 'Auction']) {
    const row = rows.find((l) => l.startsWith(name + ' · '));
    if (!row) throw new Error(`the Channels tab has no ${name} row`);
    if (!/ net · [\d.]+ days · \$[\d,]+–\$[\d,]+ · feed 5 Oct 2026/.test(row)) throw new Error(`the ${name} row has no P10–P90 and "feed 5 Oct 2026": ${row}`);
  }
  if (!rows.some((l) => l.startsWith('Wholesale lot · '))) throw new Error('the Channels tab has no Wholesale lot row');
  if (!rows.some((l) => /battery swap \+\$28 price, −\$24 cost, \+5 days/.test(l))) throw new Error('no row carries "battery swap +$28 price, −$24 cost, +5 days"');
  const rep = rows.find((l) => l.startsWith('Replacement stock'));
  if (!rep) throw new Error('the Channels tab has no Replacement stock row');
  const parts = await needCase(admin, NO_PARTS);
  const t2 = await tabHas(admin, parts, 6, 'channels', 'Channels', /No genuine-parts declaration \(GR-D9\)/, '"No genuine-parts declaration (GR-D9)"');
  return `${rows.find((l) => l.startsWith('Buy Now · '))}; replacement: ${rep}; ${parts}: ${t2.split('\n').find((l) => /GR-D9/.test(l)).trim().slice(0, 90)}`;
});

// ---------------------------------------------------------------- 6
await step('6 Models: Admin fits a device price model; MAE, coverage, the proposal and the shadow count show', async () => {
  const admin = await as('admin');
  await admin.goto(`${base}/#/agents`);
  const panel = admin.locator('#agModels');
  await panel.waitFor();
  await panel.locator('#ag-mdl-template').selectOption('device');
  await panel.locator('#ag-mdl-fit-price').click(); // a missing "Fit price model" button fails here
  const row = panel.locator('tr[data-model]:has([data-testid="price-note"])').first();
  const note = await until(
    async () => {
      const x = await row.locator('[data-testid="price-note"]').innerText();
      return /MAE \$\d.*inside the range \d+% \(target 80%\)/.test(x) ? x : null;
    },
    'no price candidate row with MAE and "inside the range N% (target 80%)" (fewer than 300 rows? is dvmkt synced?)',
    SYNC,
    admin,
  );
  await row.getByRole('button', { name: 'Propose promotion' }).click();
  await until(async () => /Proposed by /.test(await row.innerText()), 'the row does not show "Proposed by admin"', UI, admin);
  const shadow = await until(
    async () => {
      const x = await row.locator('[data-testid="price-shadow"]').innerText();
      return /^Shadow: \d+ of 30 evaluations/.test(x) ? x : null;
    },
    'the row does not show "Shadow: n of 30 evaluations"',
    UI,
    admin,
  );
  const appr = await as('approver');
  await appr.goto(`${base}/#/agents`);
  const arow = appr.locator('#agModels tr[data-model]:has([data-testid="price-note"])').first();
  await arow.waitFor();
  const n = Number(/Shadow: (\d+) of/.exec(await arow.locator('[data-testid="price-shadow"]').innerText())?.[1] ?? '0');
  const approve = arow.getByRole('button', { name: 'Approve promotion' });
  if (n < 30) {
    if (!(await approve.isDisabled())) throw new Error(`the Approver can promote with only ${n} shadowed evaluations`);
    const why = await arow.innerText();
    if (!/A price model is shadowed on 30 evaluations before promotion \(\d+ so far\)\./.test(why)) throw new Error('the Approve button gives no shadow reason: ' + why.replace(/\s+/g, ' ').slice(0, 200));
  }
  return `${note.slice(0, 90)}; ${shadow}`;
});

// ---------------------------------------------------------------- 7
await step('7 My work: the wholesale lot shows the dropped B05 bid and waits for the Approver (Commercial manager)', async () => {
  const planner = await as('planner.a');
  await planner.goto(`${base}/#/mywork`);
  const card = planner.locator('[data-testid="lots-card"]');
  await card.waitFor();
  const select = card.getByLabel('Org unit to build lots for');
  if (await select.count()) await select.selectOption(ORG);
  await card.getByRole('button', { name: 'Build lots' }).click(); // a missing "Build lots" button fails here
  const lot = await until(
    async () => {
      const lis = await card.locator('li[data-status="bidding"]').all();
      return lis.length ? lis[0] : null;
    },
    'Build lots made no lot: no device is routed to wholesale and awaiting approval (lot.build takes those cases)',
    UI,
    planner,
  );
  const ref = /LOT-[A-Z]-\d{4}/.exec(await lot.innerText())?.[0];
  const units = Number(/(\d+) units/.exec(await lot.innerText())?.[1] ?? '0');
  if (!ref || !units) throw new Error('the built lot shows no lot reference and unit count: ' + (await lot.innerText()).slice(0, 160));
  // the buyers bid in the market (the mock): five approved buyers and B05, the highest gross, who is not approved. The best net is
  // set so the lot is worth about $31,000 (over the $25,000 of GR-D10), whatever its size.
  const net = Math.ceil(31000 / units);
  const bid = (code, n, fees, log) =>
    mkt('/bids', { method: 'POST', body: JSON.stringify({ lotRef: ref, buyerCode: code, units, amount: n + fees + log, fees, logistics: log, currency: 'USD', receivedAt: '2026-10-07T08:00:00+00:00' }) });
  await bid('B02', net, 8, 6);
  await bid('B01', net - 8, 6, 4);
  await bid('B03', net - 10, 6, 5);
  await bid('B05', net + 30, 12, 8);
  await syncAndWait(await as('developer'), 'dvmkt');
  await planner.reload();
  const li = planner.locator('[data-testid="lots-card"]').locator(`li[data-status="bidding"]:has-text("${ref}")`);
  await until(async () => /Dropped B05: Buyer B05 is not an approved wholesale buyer/.test(await li.innerText()), `${ref} does not show "Dropped B05: Buyer B05 is not an approved wholesale buyer"`, UI, planner);
  await li.getByRole('button', { name: 'Propose' }).click();
  const prop = planner.locator(`[data-testid="lots-card"] li[data-status="proposed"]:has-text("${ref}")`);
  await prop.waitFor({ timeout: UI });
  const text = await prop.innerText();
  if (!/best approved bid \$[\d,.]+ a unit · \$3\d,\d{3}/.test(text)) throw new Error('the lot does not show its best approved bid and a value near $31,000: ' + text.replace(/\s+/g, ' ').slice(0, 200));
  if (!/Waits for the Approver role \(Commercial manager\)/.test(text)) throw new Error('the lot does not wait for the Approver (Commercial manager): ' + text.replace(/\s+/g, ' ').slice(0, 200));
  return `${ref}: ${text.split('\n').find((l) => /best approved bid/.test(l))}`;
});

// ---------------------------------------------------------------- 8
await step('8 Buy Now: approved, listed, a seeded sale settles it, Finance confirms the outcome', async () => {
  const admin = await as('admin');
  const planner = await as('planner.a');
  const approver = await as('approver');
  // a device the market's seeded sales name, whose case recommends Buy Now and awaits approval
  let sales = (await mkt('/sales?limit=500')).items || [];
  sales = sales.filter((s) => (s.imeis || []).length === 1 && s.listingId);
  let id = null;
  let imei = null;
  for (const s of sales.slice(0, 250)) {
    const cid = await caseOf(admin, s.imeis[0]);
    if (!cid) continue;
    const c = await caseScreen(admin, cid).catch(() => null);
    if (c && c.owner === ORG && c.recommendation?.id === 'buynow' && c.stage === 'awaiting_approval' && !c.blocked && !c.approval) {
      id = cid;
      imei = s.imeis[0];
      break;
    }
  }
  if (!id) throw new Error('no case recommends Buy Now and awaits approval for a device the market sold (seeded sales)');
  // planner.a submits and the Approver approves, with the page's own buttons
  await planner.goto(`${base}/#/product/${id}/stage/7`);
  const submit = planner.locator('button', { hasText: `Submit ${id} for review` });
  await submit.first().waitFor({ timeout: UI });
  await submit.first().click();
  await approver.goto(`${base}/#/product/${id}/stage/7`);
  const approve = approver.locator('button', { hasText: /^\s*Approve (?!and send)/ }).first();
  await approve.waitFor({ timeout: UI });
  await approve.click();
  await approver.getByLabel(/I reviewed evidence snapshot/).check();
  await approver.click('text=Approve and send instruction');
  // the worker sends the list step; the market holds the listing
  await until(async () => ((await mkt(`/listings?imei=${imei}`)).items || []).some((l) => l.listingId === `LST-${id}-buynow`), `the market has no listing LST-${id}-buynow (worker running, instructions on?)`, SYNC, admin);
  // only time moves from here (the systems acknowledge); the sale landed after the case existed (step 1) and settled it
  const dev = await as('developer');
  await tabHas(admin, id, 9, 'settlement', 'Settlement', /Sold \$[\d.,]+ · fees \$[\d.,]+ · returns \$[\d.,]+ · [\d.]+% of forecast/, '"Sold $… · fees $… · returns $… · …% of forecast"').catch(async (e) => {
    await syncAndWait(dev, 'dvmkt');
    throw e;
  });
  const fin = await as('finance');
  await until(
    async () => {
      await fin.goto(`${base}/#/product/${id}/stage/9`);
      await fin.locator('#view').waitFor();
      if (await fin.locator('button', { hasText: 'Confirm the outcome' }).count()) return true;
      await advance(3);
      await fin.waitForTimeout(2500);
      return false;
    },
    'Finance has no "Confirm the outcome" button (the case did not close: worker running?)',
    SYNC,
    fin,
  );
  await fin.locator('button', { hasText: 'Confirm the outcome' }).first().click();
  await until(async () => (await caseScreen(fin, id)).outcome, 'the outcome was not confirmed', UI, fin);
  const t = await tabText(fin, id, 9, 'settlement', 'Settlement');
  return `${id} (${imei}): ${t.split('\n').find((l) => /Sold/.test(l)).trim()}`;
});

// ---------------------------------------------------------------- 9
await step('9 Ageing: "Move 12 Offers listings to Auction: 14 days, no offer"; planner.a accepts it into the draft', async () => {
  const planner = await as('planner.a');
  await planner.goto(`${base}/#/mywork`);
  const card = planner.locator('[data-testid="ageing-card"]');
  await card.waitFor({ timeout: UI }).catch(() => {
    throw new Error('My work has no Ageing listings card (are the market listings in the org unit?)');
  });
  const li = card.locator('li[data-kind]', { hasText: 'Move 12 Offers listings to Auction: 14 days, no offer' });
  await li.first().waitFor({ timeout: UI }).catch(async () => {
    throw new Error('no suggestion "Move 12 Offers listings to Auction: 14 days, no offer": ' + (await card.innerText()).replace(/\s+/g, ' ').slice(0, 200));
  });
  const line = (await li.first().innerText()).split('\n')[0];
  await li.first().getByRole('button', { name: 'Accept' }).click();
  await planner.getByText('Added to your draft; a different person approves it').first().waitFor({ timeout: UI });
  return line;
});

// ---------------------------------------------------------------- 10
await step('10 Analytics: both device questions answer with a chart, the sentence and example records', async () => {
  const admin = await as('admin');
  await admin.goto(`${base}/#/analytics`);
  await admin.locator('#view').waitFor();
  await admin.getByRole('radio', { name: 'Packs' }).or(admin.getByRole('button', { name: 'Packs' })).first().click();
  const sec = admin.locator('[data-testid="pack-questions"]');
  await sec.waitFor({ timeout: UI });
  const ask = async (question, id, rx) => {
    await sec.getByRole('button', { name: question }).click();
    const a = sec.locator(`[data-question="${id}"]`);
    await a.waitFor({ timeout: UI });
    if (!(await a.locator('[role="img"]').count())) throw new Error(`"${question}" shows no chart`);
    const s = await a.locator('[data-k="sentence"]').innerText();
    if (!rx.test(s)) throw new Error(`"${question}" answers: ${s}`);
    if (!(await a.locator('table[aria-label="Example records"] tbody tr').count())) throw new Error(`"${question}" shows no example records`);
    return s;
  };
  const one = await ask('Why did price realised drop?', 'price_after_launch', /Galaxy S24 fell from \d+% to \d+% of the feed in the 3 weeks after its successor launched on 14 Sep 2026/);
  const two = await ask('Who causes grading disputes?', 'disputes_by_partner', /Partners P02 and P04 cause 58% of grading disputes/);
  return `${one.slice(0, 70)}…; ${two.slice(0, 70)}…`;
});

await browser.close();
if (errors.length) {
  say('FAIL page errors:', errors.slice(0, 5).join(' | '));
  process.exit(1);
}
say(`smoke-p9-6: all ${stepsRun} steps passed`);
