/**
 * Plan 9, final end-to-end smoke (P9-13.11, stories X-13, X-14, X-16 and the plan's final demo): the five packs from a returned
 * asset to an approved decision whose instructions go out, one line per step (PASS, or FAIL with the step and what was missing,
 * then exit 1 at once). Chrome through Playwright, every check through the UI unless the line says "(action: ...)": the reads and
 * the clicks the app has no control for yet (registering an extra system, opening a case from a mock's data, the standing policy,
 * submitting for review, the mock's clock) use the app's own action call or the mock's API, as the pack smokes do.
 *
 *   1  admin: the Modeler's template picker lists the industrial template and the five packs (tool fleet, device, used cars,
 *      telecom network, medical rental); picking each shows its flow "Published · vN".
 *   For each pack, step "<n>a" (the case) and step "<n>b" (the approvals):
 *   a  The pack's systems are registered, connected and synced (action: source.reconnect, source.sync). The case opens:
 *        tool_fleet  the fleet mock's returns, read by a sync through a published ingest workflow with an Open case step (the
 *                    sync opens the cases; org unit tool-fleet-a; planner.a asks for tenant access and admin grants it);
 *        device      the device lab's trade-ins: the dvlab sync opens one case per received device (Customer A);
 *        used_cars, telecom_network, medical_rental: a sync opens no case for these packs yet, so the records the pack smokes
 *                    use are opened as cases (action: case.open, smoke-p9-9, -10 and -11's data).
 *      No mock takes a posted return event (their returns and trade-ins are read-only seeds), so the "posted return" of the plan
 *      is the mock's seeded record. A My work lists an item of one of the pack's cases (the API row and the page agree): planner.a's,
 *      else that of the role the pack gives the item to (approver, warehouse1, admin; the line says whose).
 *      The case page shows the gate results ("N of M passed" and a gate's name), the recommendation with its confidence
 *      ("<High|Medium|Low> confidence") and the alternatives, and the carbon line: "CO₂e avoided" with each factor's source and
 *      year (cfs-2026.2 holds sample factors for all five packs; medical rental's are transport only). A case whose routes
 *      carry no factor ("no factor source on file") fails the step.
 *   b  admin writes a standing policy for the pack (the pack's value limit, the flow's confidence threshold) and approver approves
 *      it (action: standingPolicy.save/submit/approve); planner.a submits the pack's cases (action: decision.submit) until one is
 *      "approved by policy" (its page shows it); another case that waits for a person (the pack smokes' over-the-limit case where
 *      there is one) is approved by `approver` on its case page (Approve, I reviewed evidence snapshot, Approve and send
 *      instruction). Then only source-sim's clock moves (action: /_sim/clock/advance) until the instructions of both cases are
 *      sent and at least one step of each is acknowledged.
 *
 * Not covered here (the spec's items 4-9: the close, X-13, X-14, X-16, Finance's confirmation and the six model fits) are the
 * subjects of smoke-p9-3 (14, 11), smoke-p9-6 (8) and the plan-9 closing smokes; this script stops at the instructions.
 *
 * Needs the worker (syncs, instructions) and source-sim (the mocks and its clock). No vendor product is claimed connected: every
 * system is synthetic. Changes state. The lead runs, holding the api test lock meanwhile:
 *   bash scripts/dev/reset.sh && bash scripts/dev/wait-idle.sh
 *   node frontend/scripts/smoke-p9-final.mjs http://localhost:5173
 *   bash scripts/dev/reset.sh
 * It resets nothing itself. Screenshots of a failing step go to SMOKE_SHOTS (default: <OS temp>/smoke-p9-final). SIM_URL / SIM_PORT
 * name source-sim. Target: under 15 minutes. The last line is "smoke-p9-final: all 11 steps passed".
 */
import { chromium } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const SIM = process.env.SIM_URL || `http://localhost:${process.env.SIM_PORT || 8100}`;
const shots = process.env.SMOKE_SHOTS || path.join(tmpdir(), 'smoke-p9-final');
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const ORG = 'Customer A';
const TF_ORG = 'tool-fleet-a';
const UI = 300000; // the dev stack answers slowly while the worker syncs and other stacks share the machine
const FIRST = 300000; // a first page load after sign-in
const SYNC = 600000; // a sync waits behind the worker's queue after a reset (36 source syncs on a loaded machine)
// device first: each "b" step moves source-sim's clock (tool fleet's by about 7 days), and then the device market feed of
// 5 Oct is stale, so GR-D8 (price confidence) holds every device case for the pricing analyst (writer 104, run 2)
const PACKS = ['device', 'tool_fleet', 'used_cars', 'telecom_network', 'medical_rental'];
mkdirSync(shots, { recursive: true });

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const errors = [];
const gaps = [];
const pages = {};
const say = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);
const T0 = Date.now();

async function as(acct) {
  if (pages[acct]) return pages[acct];
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } });
  const p = await ctx.newPage();
  p.setDefaultTimeout(UI);
  p.on('pageerror', (e) => errors.push(`${acct} @ ${p.url().replace(/^.*#/, '#')}: ${e.message}`));
  await p.goto(base + '/#/signin', { waitUntil: 'domcontentloaded', timeout: FIRST });
  await p.fill('#si-id', acct);
  await p.fill('#si-pw', 'demo');
  await p.click('button[type=submit]');
  await p.waitForURL((u) => !/signin/.test(u.hash), { timeout: FIRST });
  await p.locator('#view').first().waitFor({ timeout: FIRST }); // the post-sign-in redirect lands first, or a goto right after races it
  await p.waitForTimeout(1500);
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
    if (Date.now() > end) throw new Error(typeof msg === 'function' ? await msg() : msg);
    await p.waitForTimeout(1000);
  }
};
/** Open a route and drop the read cache with a reload (a hash change alone keeps what the page read earlier). */
async function open(p, url, ready = '#view') {
  await p.goto(url, { waitUntil: 'domcontentloaded', timeout: FIRST });
  await p.reload({ waitUntil: 'domcontentloaded', timeout: FIRST });
  await p.locator(ready).first().waitFor({ timeout: FIRST });
}
const advance = async (hours = 3) => {
  const r = await fetch(SIM + '/_sim/clock/advance', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ hours }) });
  if (!r.ok) throw new Error('sim clock advance failed: ' + r.status);
};

async function step(name, fn) {
  const t0 = Date.now();
  try {
    const detail = await fn();
    say('PASS', name, detail ? '· ' + detail : '', `(${Math.round((Date.now() - t0) / 1000)} s)`);
  } catch (e) {
    say('FAIL', name, '·', String(e?.message || e).split('\n').slice(0, 3).join(' | '), (e?.stack || '').match(/smoke-p9-final\.mjs:\d+/)?.[0] ?? '');
    for (const [a, p] of Object.entries(pages)) await p.screenshot({ path: path.join(shots, `fail-${a}.png`), fullPage: true }).catch(() => {});
    await Promise.race([browser.close().catch(() => {}), new Promise((r) => setTimeout(r, 5000))]);
    process.exit(1);
  }
}

// ---------------------------------------------------------------- sources and cases
const packDoc = (key) => JSON.parse(readFileSync(path.join(ROOT, 'backend/di/services/modeler/packs', key + '.json'), 'utf8'));
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
/** An extra system registers read-only ("Read"), and the worker then sends it no instruction ("connected read-only here:
 *  instructions are not sent. Change its access to Read / write"): admin gives it write operations, as a person does in the
 *  Source drawer (action: source.update; writer 104, pre-check of run 2). Everything else of the source is kept. */
async function readWrite(sids, org) {
  const admin = await as('admin');
  for (const sid of sids) {
    const src = await until(() => sourceOf(admin, sid), `${sid} is not registered`, UI, admin);
    if (src.rw && !/^(Read|Read \(import\)|—)$/.test(src.rw)) continue;
    const d = { type: src.type, name: src.name, vendor: src.vendor, ver: src.ver, env: src.env, url: src.url, method: src.method, cfg: { ...(src.cfg || {}) }, interval: src.interval, auth: src.auth, owner: src.owner };
    const read = src.read?.length ? src.read : ['Records'];
    const body = { mode: 'edit', id: sid, d, maps: (src.mappings || []).filter(Array.isArray), ops: { read, write: ['Instructions of approved decisions'] }, note: 'Smoke: send the instructions' };
    await must(admin, 'source.update', org || src.org_unit_id ? { ...body, org_unit_id: org || src.org_unit_id } : body);
  }
}
/** Register and connect systems, then wait for a successful sync of each (as smoke-p9-9, -10 and -11). */
async function connectAll(dev, ids) {
  for (const sid of ids) await must(dev, 'source.reconnect', { source_id: sid }); // (action) registers an extra system, then connects it
  for (const sid of ids) await callAction(dev, 'source.sync', { source_id: sid }); // dropped as a duplicate while the first full sync runs: fine
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
  await readWrite(ids);
}
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
const sourceOf = async (p, sid) => deep(await getJson(p, '/api/screens/integration/sources/' + encodeURIComponent(sid)), (o) => o.id === sid && 'method' in o);
/** Limit what a source's published ingest workflow reads (conn.cfg.resources), as smoke-p9-6 does. */
const wfOf = {};
async function readOnly(p, sid, resources) {
  const wf = wfOf[sid] || (wfOf[sid] = await must(p, 'workflow.create', { type: 'ingest', src: sid }));
  const w = (await getJson(p, '/api/screens/workflows/' + encodeURIComponent(wf.id))).workflow;
  const g = JSON.parse(JSON.stringify(w.graph));
  const conn = g.nodes.find((n) => n.k === 'conn');
  conn.cfg = { ...(conn.cfg || {}), resources, mode: 'full' };
  // an extra system registered here (dvmkt) has no field mapping, and the default graph's Map step then fails the publish
  // checks ("No field mapping is defined for dvmkt yet"): drop the Map step and what follows it, as smoke-p9-3's fleet graph
  // has no Map step either (writer 101, run 3)
  const maps = (await getJson(p, '/api/screens/integration/sources/' + encodeURIComponent(sid)))?.mappings || [];
  if (!maps.length) {
    const drop = new Set(g.nodes.filter((n) => n.k === 'map').map((n) => n.id));
    for (let grew = true; grew; ) {
      grew = false;
      for (const e of g.edges || []) if (drop.has(e.a) && !drop.has(e.b)) { drop.add(e.b); grew = true; }
    }
    g.nodes = g.nodes.filter((n) => !drop.has(n.id));
    g.edges = (g.edges || []).filter((e) => !drop.has(e.a) && !drop.has(e.b));
  }
  await must(p, 'workflow.save', { id: wf.id, name: w.name, owner: w.owner, trig: w.trig, graph: g });
  await must(p, 'workflow.publish', { id: wf.id });
}
const caseIdOf = async (p, q) => ((await must(p, 'cases.list', { q, limit: 5 })).rows || []).find((x) => x.id)?.id || null;
const caseScreen = async (p, id) => (await getJson(p, '/api/screens/case/' + encodeURIComponent(id))).case;
const analysisOf = (p, id) => getJson(p, '/api/screens/case/' + encodeURIComponent(id) + '/analysis');
/** case.open as planner.a; a pack not yet published for the org is published first (admin imports, approver approves). */
async function openCase(template_key, asset_key, reason, facts, org = ORG) {
  const planner = await as('planner.a');
  const body = { org_unit_id: org, template_key, asset_key, reason, facts };
  let r = await callAction(planner, 'case.open', body);
  if (!r.ok && r.error?.code === 'duplicate') return caseIdOf(planner, asset_key.replace(/^.*:/, ''));
  if (!r.ok && /pack|template/i.test(JSON.stringify(r))) {
    const doc = packDoc(template_key);
    doc.version = '1.9.90';
    const imp = await callAction(await as('admin'), 'pack.import', { doc });
    if (imp.ok) {
      await must(await as('admin'), 'pack.submit', { id: imp.output.id });
      await must(await as('approver'), 'pack.approve', { id: imp.output.id });
    }
    r = await callAction(planner, 'case.open', body);
  }
  if (!r.ok) throw new Error(`case.open ${template_key} ${asset_key}: ${JSON.stringify(r.error || r).slice(0, 240)} (reset the stack first?)`);
  return r.output.case_id;
}
// planner.a belongs to Customer A and cannot open the cases of tool-fleet-a: a tenant access request that admin approves (smoke-p9-3)
let plannerGranted = false;
async function plannerAccess() {
  if (plannerGranted) return;
  const planner = await as('planner.a');
  const admin = await as('admin');
  const r = await callAction(planner, 'access.requestTenant', { tenant: TF_ORG, reason: 'Smoke: the tool fleet cases of ' + TF_ORG });
  if (r.ok) await must(admin, 'access.decideRequest', { id: r.output.id, decision: 'approve' });
  else if (!/already|access/i.test(JSON.stringify(r.error || r))) throw new Error('access.requestTenant: ' + JSON.stringify(r.error || r).slice(0, 200));
  await pages['planner.a'].context().close();
  delete pages['planner.a'];
  plannerGranted = true;
}

/** Each pack: how its systems connect and which cases open. `show` is the case whose page is read; `cands` the cases the approvals
 *  try (the policy candidates first); `person` the pack smoke's case that waits for a person, where it has one. */
const P = {};

// ---------------------------------------------------------------- tool fleet (smoke-p9-3, steps 1, 12)
P.tool_fleet = {
  org: TF_ORG,
  async open() {
    const admin = await as('admin');
    const dev = await as('developer');
    const o = await callAction(admin, 'org.create', { id: TF_ORG, parent_id: 'workspace', kind: 'company', name: 'Tool fleet A' });
    if (!o.ok && !/exist|duplicate/i.test(JSON.stringify(o.error))) throw new Error('org.create: ' + JSON.stringify(o.error).slice(0, 200));
    await must(dev, 'source.reconnect', { source_id: 'fleet' });
    const wf = await must(dev, 'workflow.create', { type: 'ingest', src: 'fleet' });
    const w = (await getJson(dev, '/api/screens/workflows/' + encodeURIComponent(wf.id))).workflow;
    const conn = w.graph.nodes.find((n) => n.k === 'conn');
    conn.cfg = { ...(conn.cfg || {}), resources: ['returns'], mode: 'full' };
    const caseNode = {
      id: 'case', k: 'xf', ref: 'x_case', x: conn.x + 120, y: conn.y,
      cfg: { template: 'tool_fleet', reason: 'contract_end', asset_field: 'serial', org_unit_id: TF_ORG, reason_field: 'kind', facts: ['toolClass', 'contractId', 'lineId', 'site'] },
    };
    await must(dev, 'workflow.save', { id: wf.id, name: w.name, owner: w.owner, trig: w.trig, graph: { ...w.graph, nodes: [conn, caseNode], edges: [{ id: `${conn.id}>case`, a: conn.id, b: 'case', locked: false }] } });
    await must(dev, 'workflow.publish', { id: wf.id });
    // the first full sync (queued by the reconnect) may run with the default graph: let it finish, then sync again (mode full)
    const runs = async () => ((await getJson(dev, '/api/screens/integration/sources/fleet')).sync_history || []).length;
    await until(async () => (await runs()) >= 1, 'the first sync of fleet did not finish', SYNC, dev);
    await until(async () => {
      if ((await runs()) >= 2) return true;
      await callAction(dev, 'source.sync', { source_id: 'fleet' });
      await dev.waitForTimeout(8000);
      return (await runs()) >= 2;
    }, 'the second sync of fleet did not run', SYNC, dev);
    const serials = await until(
      async () => {
        const r = JSON.stringify(await getJson(admin, '/api/screens/product/returned'));
        const s = [...new Set(r.match(/\b(?:CMH|BRK|DCD|CRH|AGR|LSR)-\d{5}\b/g) || [])];
        return s.length >= 18 ? s : null;
      },
      'the fleet sync did not open the 18 tool cases in ' + TF_ORG,
      SYNC,
      dev,
    );
    await plannerAccess();
    const ids = [];
    for (const s of serials) ids.push(await caseIdOf(admin, s));
    this.show = await caseIdOf(admin, 'CMH-48213');
    this.ids = ids.filter(Boolean);
    this.cands = this.ids.filter((x) => x !== this.show);
    // a DCD of grade C: the repair ($702) is over GR-14's $600, so a person (the Fleet manager) approves it (smoke-p9-3 step 12)
    this.person = await openCase('tool_fleet', 'DCD-16500', 'manual', { cls: 'DCD', grade: 'C', site: 'Houston', rul: 62 }, TF_ORG);
    return `the fleet sync opened ${this.ids.length} tool cases (${this.show} for CMH-48213)`;
  },
};

// ---------------------------------------------------------------- device (smoke-p9-6, step 1)
P.device = {
  org: ORG,
  async open() {
    const admin = await as('admin');
    const dev = await as('developer');
    // a reconnect queues the source's first sync, and the worker runs them in this order: the market (prices AND sales) must
    // land before the lab's sync opens and values the cases, else GR-D8 holds them "unseen SKU, stale feed" (writer 108)
    for (const sid of ['dvreg', 'dvmkt', 'dvlab']) await must(dev, 'source.reconnect', { source_id: sid });
    for (const sid of ['dvlab', 'dvmkt']) {
      // trade-ins and listings belong to an org unit (a trade-in of a source bound to none stays pending): bind the lab and the market
      const src = await until(() => sourceOf(dev, sid), `${sid} is not registered`, UI, dev);
      const d = { type: src.type, name: src.name, vendor: src.vendor, ver: src.ver, env: src.env, url: src.url, method: src.method, cfg: { ...(src.cfg || {}) }, interval: src.interval, auth: src.auth, owner: src.owner };
      await must(admin, 'source.update', { mode: 'edit', id: sid, d, maps: (src.mappings || []).filter(Array.isArray), ops: { read: src.read || [], write: src.write || [] }, note: '', org_unit_id: ORG });
    }
    await readWrite(['dvlab', 'dvmkt'], ORG); // the listings and payouts are sent to the market and the lab
    await syncAndWait(dev, 'dvreg'); // the registry first: a device with no registry check is held
    // the market feed WITH its sales: without them every SKU is "unseen" and GR-D8 (price confidence) holds 81 of the 82
    // device cases for the pricing analyst, so no standing policy can approve one (writer 108; lead decision 28 Nov)
    await readOnly(dev, 'dvmkt', ['prices', 'launches', 'listings', 'bids', 'sales', 'replacementDemand']);
    await syncAndWait(dev, 'dvmkt');
    await syncAndWait(dev, 'dvlab'); // its post-sync hook opens one case per received device
    const SAMPLE = '359990000000428'; // iPhone 14, 128 GB, grade B, quote $410, partner P01 (smoke-p9-6)
    const sample = await until(() => caseIdOf(admin, SAMPLE), `the dvlab sync opened no case for IMEI ${SAMPLE}`, SYNC, admin);
    const rows = (await must(admin, 'cases.list', { q: 'IMEI:', limit: 400 })).rows || [];
    this.ids = rows.map((r) => r.id).filter(Boolean);
    // the registry mock checks a device once, an hour after it is received (sim/seed/devices.py): at the mocks' as-of date
    // (2026-10-07) the sample's check (2026-09-24) is older than G-DEV-LOCK's 7 days, so the gate holds it for a newer check
    // and it has no recommendation. The case page is read on a device whose check is fresh: the sample when the gate lets it
    // through, else the first device case that awaits approval (writer 104, run 1)
    const ready = ((await must(admin, 'cases.list', { q: 'IMEI:', stage: 'awaiting_approval', limit: 400 })).rows || []).map((r) => r.id).filter(Boolean);
    this.show = ready.includes(sample) || !ready.length ? sample : ready[0];
    this.cands = [this.show, ...ready.filter((x) => x !== this.show).slice(0, 40)];
    this.person = null;
    const why = this.show === sample ? `${sample} for IMEI ${SAMPLE}` : `${this.show}; ${sample} for IMEI ${SAMPLE} waits for a newer registry check`;
    return `the dvlab sync opened ${this.ids.length} device cases, ${ready.length} await approval (${why})`;
  },
};

// ---------------------------------------------------------------- used cars (smoke-p9-9, step 1)
const vin = (n) => 'SYNUC' + String(n).padStart(12, '0');
P.used_cars = {
  org: ORG,
  async open() {
    await connectAll(await as('developer'), ['uc_lease', 'uc_dms', 'uc_title', 'uc_insp', 'uc_recall', 'uc_auction', 'uc_price']);
    const c = {};
    for (const n of [1, 2, 3, 7, 90]) {
      c[n] = await openCase('used_cars', `${ORG}:${vin(n)}`, n > 60 ? 'trade_in' : 'lease_end', { vin: vin(n), mileage: 38000, return_date: '2026-11-20' });
    }
    this.show = c[1]; // UC-S1: Retail · South lot
    this.ids = Object.values(c);
    this.person = c[7]; // UC-S7: recon $2,800 over the $2,500 limit
    this.cands = [c[1], c[90], c[3], c[2]];
    return `cases ${Object.entries(c).map(([n, id]) => `...${String(n).padStart(3, '0')}=${id}`).join(', ')} (action: case.open)`;
  },
};

// ---------------------------------------------------------------- telecom network (smoke-p9-10, step 1)
const sn = (n) => 'SN-TN-' + String(n).padStart(4, '0');
const UNITS = { 1: ['RRU-4410', 'SITE-100'], 6: ['RAD-7700', 'SITE-105'], 7: ['RRU-4410', 'SITE-106'], 12: ['RAD-7700', 'SITE-111'], 15: ['BBU-2200', 'SITE-114'], 202: ['LCD-100G', 'SITE-301'] };
P.telecom_network = {
  org: ORG,
  async open() {
    await connectAll(await as('developer'), ['tn_inv', 'tn_decom', 'tn_bench', 'tn_spares', 'tn_broker', 'tn_recycler']);
    const c = {};
    for (const [n, [model, site]] of Object.entries(UNITS)) {
      c[n] = await openCase('telecom_network', `${ORG}:${sn(n)}`, 'decommission', { serial: sn(n), model, site, removed_at: '2026-10-04T08:00:00+00:00', removal_job: 'RJ-01', programme: '5G refresh' });
    }
    this.show = c[1]; // SN-TN-0001: Redeploy to a site
    this.ids = Object.values(c);
    // the trade compliance approval (AP-TN-EXP, an open item that keeps any policy off the case) opens on the RRU-4410s, whose
    // bids are screened clear: SN-TN-0007 waits for the approver; the RAD-7700 SN-TN-0006 (Refurbish as a spare, no open item)
    // is the policy's (writer 104, pre-check of run 2: the roles were the other way round)
    this.person = c[7];
    this.cands = [c[6], c[1], c[15], c[12]];
    return `cases ${Object.entries(c).map(([n, id]) => `${sn(n)}=${id}`).join(', ')} (action: case.open)`;
  },
};

// ---------------------------------------------------------------- medical rental (smoke-p9-11, step 1)
const TAGS = { 1: 'SYN-MR-IP-0001', 2: 'SYN-MR-IP-0002', 20: 'SYN-MR-IP-0020', 7: 'SYN-MR-PM-0007' };
P.medical_rental = {
  org: ORG,
  async open() {
    await connectAll(await as('developer'), ['mr_rental', 'mr_assets', 'mr_decon', 'mr_biomed', 'mr_parts', 'mr_disposal']);
    const c = {};
    for (const [k, tag] of Object.entries(TAGS)) {
      // the rental mock returns only the infusion pumps: the monitor's return facts are stated by the planner (smoke-p9-11)
      c[k] = await openCase('medical_rental', `${ORG}:${tag}`, 'rental_return', k === '7' ? { tag, hospital: 'HOSP-B', return_date: '2026-11-20' } : { tag });
    }
    this.show = c[1]; // Re-rent · Hospital B (synthetic)
    this.ids = Object.values(c);
    this.person = c[7]; // the $1,350 repair over $1,000
    this.cands = [c[1], c[2], c[20]];
    return `cases ${Object.entries(c).map(([k, id]) => `${TAGS[k]}=${id}`).join(', ')} (action: case.open)`;
  },
};

// ---------------------------------------------------------------- the case page
/**
 * One block of a case page, read as a person sees it: open the place, wait for the block (`sel`), then until `ok(innerText,
 * textContent)` holds; a loaded stack can leave a page at "Loading..." for minutes after a sync, so the place is opened again
 * every 45 s. Returns {inner, all} (all: textContent, which also holds the closed <details> of the CO₂e factors).
 */
async function block(p, id, place, sel, ok, what, ms = UI) {
  let got = { inner: '', all: '' };
  const end = Date.now() + ms;
  while (Date.now() < end) {
    await open(p, `${base}/#/product/${id}/${place}`);
    const until45 = Date.now() + 45000;
    while (Date.now() < until45) {
      const loc = p.locator(sel).first();
      if (await loc.count()) {
        got = { inner: await loc.innerText().catch(() => ''), all: await loc.evaluate((e) => e.textContent || '').catch(() => '') };
        if (ok(got.inner, got.all)) return got;
      }
      await p.waitForTimeout(1500);
    }
  }
  throw new Error(`case ${id} (${place}) does not show ${what}: ${got.inner.replace(/\s+/g, ' ').slice(0, 200) || '(no ' + sel + ')'}`);
}
const esc = (s) => String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

async function showCase(pack) {
  const cfg = P[pack];
  const planner = await as('planner.a');
  const id = cfg.show;
  // My work: an item of one of the pack's cases, in the API and on the page. planner.a's first; a pack whose items belong to
  // another role (used cars: the lien hold and the recon approval are the Approver's; telecom and medical rental: the
  // inventory and decontamination holds are the Warehouse Manager's) is read in the My work of that role, as smoke-p9-9 and
  // -10 do (planner.a, then approver, warehouse1, admin; writer 104, pre-check of run 2). The line names whose list it was.
  let who = null;
  const item = await until(
    async () => {
      for (const acct of ['planner.a', 'approver', 'warehouse1', 'admin']) {
        const hit = ((await getJson(await as(acct), '/api/screens/mywork')).items || []).find((x) => cfg.ids.includes(x.case_id));
        if (hit) {
          who = acct;
          return hit;
        }
      }
      return null;
    },
    `no My work (planner.a, approver, warehouse1, admin) lists an item of the ${pack} cases`,
    120000,
    planner,
  );
  const wp = await as(who);
  await open(wp, base + '/#/mywork');
  // the page shows a page of rows at a time: "Show N more" until the row is drawn (hundreds of rows after the tool and device syncs)
  const rx = new RegExp(esc(item.title.slice(0, 40)));
  await until(
    async () => {
      if (rx.test(await text(wp))) return true;
      const more = wp.locator('button', { hasText: /^\s*Show \d+ more\s*$/ }).first();
      if (await more.count()) await more.click();
      return rx.test(await text(wp));
    },
    `${who}'s My work page does not show "${item.title}"`,
    180000,
    wp,
  );
  // the case: API first (what the page must draw), then the page's blocks
  const c = await until(async () => { const x = await caseScreen(planner, id); return x?.recommendation ? x : null; }, `case ${id} has no recommendation`, UI, planner);
  const a = await analysisOf(planner, id);
  const gates = c.gates || [];
  if (!gates.length) throw new Error(`case ${id} carries no gate results`);
  const rec = c.recommendation;
  const conf = (a.routes || []).find((x) => x.id === rec.id)?.conf;
  const alts = (a.view?.routes_read?.eligible || []).slice(1, 4).map((x) => x.plan);
  // Decide > Evidence: the Gates block, "N of M passed" and each gate's name
  await block(planner, id, 'stage/6?tab=evidence', '#b-gates', (t) => /\d+ of \d+ passed/.test(t) && gates.every((g) => t.includes(g.name)), `the gate results (${gates.map((g) => g.name).join(', ')})`);
  // Decide > Decision packet: the recommendation, its confidence and the alternatives
  await block(
    planner, id, 'stage/6?tab=packet', '#afPacket',
    (t) => t.includes(rec.plan) && /(High|Medium|Low) confidence/.test(t) && /Alternatives/i.test(t) /* the heading is uppercased by CSS: innerText reads ALTERNATIVES */ && (!alts.length || alts.some((x) => t.includes(x))),
    `the recommendation "${rec.plan}" with its confidence and the alternatives (${alts.join(', ') || 'none'})`,
  );
  // Decide > Why this outcome: the outcome table's CO₂e column, each factor with its source and year
  const withCo2 = (c.routes || []).filter((r) => r.co2Prov && (r.co2Prov.factors || []).length);
  // every pack's set holds factors (cfs-2026.2: tool_fleet, device, used_cars, telecom_network, medical_rental)
  if (!withCo2.length) throw new Error(`case ${id} (${pack}) has no route with a CO₂e factor: packs/carbon.json has no ${pack} factors for its routes`);
  // the outcome table lists the eligible pathways only: the recommended route's factors first, else any listed route's
  withCo2.sort((x, y) => (y.id === rec.id) - (x.id === rec.id));
  const shows = (all, r) => all.includes(r.co2Prov.set) && r.co2Prov.factors.every((f) => all.includes(`${f.name} ${f.value}: ${f.source}, ${f.year}`));
  let pv = withCo2[0].co2Prov;
  await block(
    planner, id, 'stage/6?tab=why', 'table.tipt2',
    (t, all) => {
      const r = withCo2.find((x) => shows(all, x));
      if (r) pv = r.co2Prov;
      return /CO₂e avoided/i.test(t) && !!r;
    },
    `the CO₂e line with its factors (${pv.set}: ${pv.factors.map((f) => `${f.name} ${f.value}: ${f.source}, ${f.year}`).join('; ')})`,
  );
  const carbon = `carbon ${pv.set} (${pv.label}): ${pv.factors.map((f) => `${f.name} ${f.source}, ${f.year}`).join('; ')}`;
  return `My work of ${who} "${item.title}"; ${id}: ${gates.filter((g) => g.passed).length} of ${gates.length} gates passed; recommends ${rec.plan} (${conf} confidence), alternatives ${alts.join(', ') || 'none'}; ${carbon}`;
}

// ---------------------------------------------------------------- the approvals
const approvedByPolicy = (c) => !!c?.approval && /polic/i.test(JSON.stringify(c.approval));
async function ensurePolicy(pack, org, below, cands = [], person = null) {
  const admin = await as('admin');
  const st = await must(admin, 'standingPolicy.list', { pack, org_unit_id: org });
  if (st.in_force) return st.in_force.id;
  if (below == null && st.pack_limit == null) {
    // the pack sets no value limit (used cars, telecom network, medical rental): a flat $20,000 is under every used car's value,
    // so the policy covers the cheapest candidate that awaits approval, rounded up to the next $1,000 (writer 104)
    const vals = [];
    for (const id of cands) {
      if (id === person) continue;
      const c = await caseScreen(admin, id);
      if (c && c.stage === 'awaiting_approval' && !c.approval && !c.blocked && typeof c.recommendation?.net === 'number') vals.push(Math.abs(c.recommendation.net));
    }
    if (vals.length) below = Math.ceil(Math.min(...vals) / 1000) * 1000;
  }
  const limit = st.pack_limit ?? 20000;
  const rules = { max_value: below != null ? (st.pack_limit != null ? Math.min(limit, below) : below) : limit, min_confidence: Math.max(0.75, st.threshold || 0) };
  const pol = await must(admin, 'standingPolicy.save', { pack, org_unit_id: org, name: `Smoke final: ${pack}`, rules, owner: 'admin' });
  await must(admin, 'standingPolicy.submit', { id: pol.id });
  await must(await as('approver'), 'standingPolicy.approve', { id: pol.id });
  return pol.id;
}
/** Close the "Not in the system of record" items of a case (the tools are in the fleet system, not the lease system: smoke-p9-3). */
async function clearRecordItems(id) {
  const planner = await as('planner.a');
  const work = (await getJson(planner, '/api/screens/mywork')).items || [];
  for (const x of work.filter((w) => w.kind === 'exception' && w.case_id === id && /Not in the system of record/i.test(w.title))) {
    await callAction(planner, 'work.resolve', { item_id: Number(String(x.id).replace(/^w:/, '')), outcome: 'resolved', note: 'Smoke: the asset is held by the pack system, not the lease system' });
  }
}
async function approveOnPage(id) {
  const ap = await as('approver');
  await open(ap, `${base}/#/product/${id}/stage/7`);
  const btn = ap.locator('button', { hasText: /^\s*Approve (?!and send)/ }).first();
  await btn.waitFor({ timeout: UI }).catch(() => {
    throw new Error(`approver has no Approve button on ${id} (stage 7)`);
  });
  await btn.click();
  await ap.getByLabel(/I reviewed evidence snapshot/).check();
  await ap.getByText('Approve and send instruction').click();
  await until(async () => (await caseScreen(ap, id))?.approval, `${id} shows no approval after approver's Approve and send instruction`, UI, ap);
}
const doneSteps = (c) => (c?.exec?.steps || []).filter((s) => s.state === 'done').length;

async function approvals(pack) {
  const cfg = P[pack];
  const planner = await as('planner.a');
  const admin = await as('admin');
  let below = null;
  if (pack === 'tool_fleet') {
    // without telematics every tool return waits for a person ("No telematics for this tool", life confidence Low 0.50 under
    // the flow's 0.75): the repair log and the telematics are synced (smoke-p9-3 steps 2 and 5); the sync queues a
    // re-evaluation of each tool's open cases, after which a clean return is routed to the standing policy
    const dev = await as('developer');
    for (const sid of ['repairlog', 'tooltel']) {
      await must(dev, 'source.reconnect', { source_id: sid });
      await must(dev, 'source.sync', { source_id: sid });
    }
    await until(
      async () => {
        for (const id of cfg.cands) if ((await getJson(admin, '/api/screens/toolfleet/' + id)).approval?.kind === 'policy') return id;
        return null;
      },
      'no tool return is routed to the standing policy after the repair log and telematics syncs',
      SYNC,
      admin,
    );
  }
  if (!cfg.person) {
    // no case of the pack smoke waits for a person by itself: rank the open cases by the money they move (case_value: the
    // recommended net); the policy covers up to the middle, the highest waits for the approver
    const ranked = [];
    for (const id of cfg.cands) {
      const c = await caseScreen(admin, id);
      // every gate passed: the cheapest device cases are blacklisted ones (G-DEV-LOCK hit, routed to parts), which wait for
      // Compliance whatever the policy says (writer 104, run 2)
      const clean = (c?.gates || []).every((g) => g.passed);
      if (c && clean && c.stage === 'awaiting_approval' && !c.approval && !c.blocked && typeof c.recommendation?.net === 'number') ranked.push([Math.abs(c.recommendation.net), id]);
    }
    ranked.sort((x, y) => x[0] - y[0]);
    if (ranked.length < 2 || ranked[0][0] === ranked[ranked.length - 1][0]) throw new Error(`fewer than two ${pack} cases with different values await approval: ${JSON.stringify(ranked).slice(0, 200)}`);
    below = Math.floor((ranked[0][0] + ranked[ranked.length - 1][0]) / 2);
    cfg.person = ranked[ranked.length - 1][1];
    cfg.cands = ranked.filter(([v]) => v <= below).map((x) => x[1]);
  }
  const pol = await ensurePolicy(pack, cfg.org, below, cfg.cands, cfg.person);
  // the policy approves the first candidate it covers on the submit
  let byPolicy = null;
  const tried = [];
  for (const id of cfg.cands) {
    if (id === cfg.person) continue;
    let c = await caseScreen(admin, id);
    if (!c || c.stage !== 'awaiting_approval' || c.approval || c.blocked) {
      tried.push(`${id} ${c?.stage}${c?.blocked ? ' blocked' : ''}`);
      continue;
    }
    if (pack === 'tool_fleet') {
      // the tool view says who approves a submitted return (smoke-p9-3 step 12): only a "policy" one is worth submitting
      const ap = (await getJson(admin, '/api/screens/toolfleet/' + id)).approval;
      if (!ap || ap.kind !== 'policy') {
        tried.push(`${id} ${ap?.kind || 'no approval route'}`);
        continue;
      }
      await clearRecordItems(id);
    }
    // a device trade-in is not in the returns system either ("RT-n is not in Optoro", the Planner's item): closed as for the tools
    if (pack === 'device') await clearRecordItems(id);
    const r = await callAction(planner, 'decision.submit', { case_id: id });
    c = await until(async () => { const x = await caseScreen(admin, id); return x && (x.approval || x.submitted) ? x : null; }, '', 15000, admin).catch(() => null);
    if (approvedByPolicy(c)) {
      byPolicy = id;
      break;
    }
    tried.push(`${id} ${r.ok ? 'not covered' : (r.error?.message || '').slice(0, 60)} (value ${c?.recommendation?.net ?? '?'})`);
  }
  if (!byPolicy) throw new Error(`policy ${pol} approved none of the ${pack} cases tried: ${tried.join('; ').slice(0, 400)}`);
  const p = await as('planner.a');
  // the approval's journal line, on the Approve stage's History tab ("Approve by standing policy", by "policy SP-n v1")
  await block(p, byPolicy, 'stage/7?tab=history', '#view', (t) => /Approved? by (standing )?policy/i.test(t) && /policy \S+ v\d+/.test(t), '"Approve by standing policy" by "policy <id> vN" in its History');
  // a person approves another: the pack smoke's over-the-limit case, else the next case the policy did not cover
  let person = cfg.person;
  if (!person) {
    for (const id of cfg.cands.filter((x) => x !== byPolicy)) {
      const c = await caseScreen(admin, id);
      if (c && c.stage === 'awaiting_approval' && !c.approval && !c.blocked) {
        person = id;
        break;
      }
    }
  }
  if (!person) throw new Error(`no other ${pack} case awaits approval for the approver`);
  await callAction(planner, 'decision.submit', { case_id: person }); // already submitted (a rerun) or covered: the check below says
  const after = await caseScreen(admin, person);
  if (approvedByPolicy(after)) throw new Error(`${person} was approved by policy: it must wait for a person`);
  await approveOnPage(person);
  // only time moves: the worker sends the instructions, the mocks acknowledge them
  const moved = {};
  for (const id of [byPolicy, person]) moved[id] = { from: doneSteps(await caseScreen(admin, id)), to: 0 };
  await until(
    async () => {
      let all = true;
      for (const id of Object.keys(moved)) {
        const c = await caseScreen(admin, id);
        moved[id].to = doneSteps(c);
        moved[id].of = (c?.exec?.steps || []).length;
        moved[id].stage = c?.stage;
        if (!c?.exec || moved[id].to <= moved[id].from) all = false;
      }
      if (all) return true;
      await advance(3);
      await admin.waitForTimeout(3000);
      return false;
    },
    () => `the execution steps did not advance as the clock moved: ${Object.entries(moved).map(([id, m]) => `${id} ${m.to} of ${m.of ?? '?'} acknowledged (stage ${m.stage})`).join('; ')}`,
    SYNC,
    admin,
  );
  return `${byPolicy} approved by policy ${pol}; ${person} approved by approver; ${Object.entries(moved).map(([id, m]) => `${id} ${m.to} of ${m.of} steps acknowledged`).join(', ')}`;
}

// ---------------------------------------------------------------- 1
const NAMES = {};
if (!process.env.SMOKE_PACKS) await step('1 Modeler: the template picker lists the industrial template and the five packs, each with a published flow', async () => {
  const admin = await as('admin');
  const s = await getJson(admin, '/api/screens/modeler?template=industrial');
  for (const t of s.templates || []) NAMES[t.key] = t.name;
  const want = ['industrial', ...PACKS];
  const absent = want.filter((k) => !NAMES[k]);
  if (absent.length) throw new Error('the Modeler offers no template ' + absent.join(', '));
  await open(admin, `${base}/#/modeler?template=industrial`, '#mdl-tpl');
  const options = await admin.locator('#mdl-tpl option').allInnerTexts();
  const notListed = want.filter((k) => !options.includes(NAMES[k]));
  if (notListed.length) throw new Error(`the template picker does not list ${notListed.map((k) => NAMES[k]).join(', ')}: ${options.join(' | ')}`);
  const seen = [];
  for (const k of want) {
    await admin.locator('#mdl-tpl').selectOption(k);
    await until(async () => new URL(admin.url().replace('#/', '')).searchParams.get('template') === k || admin.url().includes('template=' + k), `picking ${NAMES[k]} did not open its flow`, UI, admin);
    await until(async () => !(await admin.locator('.mdl-pick-note').count()), `the ${NAMES[k]} flow kept loading`, UI, admin);
    const pill = admin.locator('.mdl-life .mdl-st').first();
    await pill.waitFor({ timeout: UI });
    const st = await until(async () => { const v = await pill.innerText(); return /^Published · v\d+/.test(v) ? v : null; }, async () => `the ${NAMES[k]} flow is not published: "${await pill.innerText().catch(() => '?')}"`, 60000, admin);
    seen.push(`${NAMES[k]} ${st}`);
  }
  return seen.join('; ');
});

// ---------------------------------------------------------------- 2 to 11
// SMOKE_PACKS=used_cars,device runs only those packs' steps (a debugging aid on a stack that already ran the earlier ones; the
// gate is the full run, without it)
const ONLY = (process.env.SMOKE_PACKS || '').split(',').filter(Boolean);
let n = 2;
for (const pack of PACKS) {
  if (ONLY.length && !ONLY.includes(pack)) {
    n += 1;
    continue;
  }
  await step(`${n}a ${pack}: the case opens from the pack's systems; My work; gates, recommendation, confidence, alternatives, carbon`, async () => {
    const opened = await P[pack].open();
    return opened + '; ' + (await showCase(pack));
  });
  await step(`${n}b ${pack}: one case approved by the standing policy, one by approver; the execution steps advance as the clock moves`, () => approvals(pack));
  n += 1;
}

if (errors.length) {
  say('FAIL page errors:', JSON.stringify(errors).slice(0, 1500));
  await browser.close();
  process.exit(1);
}
await browser.close();
for (const g of gaps) say('GAP', g);
console.log(`\nsmoke-p9-final: ${ONLY.length ? `the steps of ${ONLY.join(', ')} (subset, not the gate)` : 'all 11 steps'} passed in ${Math.round((Date.now() - T0) / 60000)} min${gaps.length ? ` (${gaps.length} known gap(s) above)` : ''}`);
