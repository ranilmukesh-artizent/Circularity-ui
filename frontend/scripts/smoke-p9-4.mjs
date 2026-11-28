/**
 * Plan 9, Phase 4 demo smoke (P9-4.12): the service desk, one line per step (PASS, or FAIL with the step and the text that
 * was missing, then exit 1 at once). Every step checks the page text AND the screen API (or action output) and requires the
 * two to agree.
 *
 *   1  finance opens the Modeler (tool fleet) market tables, edits FR labour to 48 EUR (v2, from 1 Oct 2026) and submits;
 *      Finance's Approve button says why not; the Approver approves (v2 in force, the API reads 48).
 *   2  Registers the connectors the tickets need (fleet, recall) and `rephist` (shared, so its history is every org's), then
 *      `sdesk` bound to org unit tool-fleet-a; the service-desk cases open (CS0010042, CS0010050) and Returned assets lists them.
 *   3  CS0010042 (ACC-US-0042): Ticket, Estimate ("186 similar repairs", priced without a technician), Options (three, cites
 *      "US labour rates v1"), the Credit lever flips the recommendation; an Engineer posts a fault on a draft line and its
 *      options appear (skipped when no draft line exists).
 *   4  The Models panel shows "Repair estimate accuracy" with one row per family (the page rows equal the API rows).
 *   5  The batch CS0010050 reads "Upgrade 9 · Fix 11 · Covered swap 2" on its Batch tab and in the API.
 *   6  The Approver approves a held upgrade (owner label "Sales"); the Options tab shows the market terms; the take-back is
 *      acknowledged (source-sim clock) and opens a Returns case.
 *   7  Admin fits a take-up model with the button; the candidate row shows its log loss against the pack prior.
 *
 * State it needs: the main stack up with the worker running, source-sim with the ServiceNow (service desk and offers),
 * Oracle Depot Repair (repair history) and fleet mocks, on a freshly reset database. Nothing else is set up by hand. The
 * UI has no one-click setup, so the script calls the app's own actions as the signed-in person (as smoke-p9-3 does) and reads
 * the result in the pages. Planner.a and the Engineer open the case pages when their tenant may see them, else the Admin
 * does (the step's detail says so). Needs Chrome (`channel: 'chrome'`).
 *
 * Changes state, and resets nothing itself. The lead runs (holding the api test lock):
 *   bash scripts/dev/reset.sh && bash scripts/dev/wait-idle.sh
 *   node frontend/scripts/smoke-p9-4.mjs http://localhost:5173
 *   bash scripts/dev/reset.sh
 * Screenshots of a failing step go to SMOKE_OUT (default: <OS temp>/smoke-p9-4). SIM_URL / SIM_PORT name source-sim.
 * The last line is "smoke-p9-4: all <N> steps passed", N being the number of steps that ran.
 */
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const SIM = process.env.SIM_URL || `http://localhost:${process.env.SIM_PORT || 8100}`;
const out = process.env.SMOKE_OUT || path.join(tmpdir(), 'smoke-p9-4');
const ORG = 'tool-fleet-a';
const MODELER = `${base}/#/modeler?template=tool_fleet&org=${encodeURIComponent(ORG)}&tab=tables`; // the market tables are on the Tables page tab
const UI = Number(process.env.SMOKE_UI_MS) || 30000; // SMOKE_UI_MS: a longer wait on a slow or shared machine
const FIRST = Math.max(20000, Number(process.env.SMOKE_UI_MS) || 0); // a first page load after sign-in
const SYNC = Number(process.env.SMOKE_SYNC_MS) || 180000; // SMOKE_SYNC_MS: a longer wait for a sync or a re-evaluation on a loaded machine
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
  // the post-sign-in redirect to Home lands first, or a goto right after it races it and the page ends on Home (writer 102)
  await p.locator('#view').first().waitFor({ timeout: Math.max(FIRST, UI) });
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
const flat = (s) => String(s).replace(/\s+/g, ' ');
const view = async (p) => flat(await p.locator('#view').innerText());
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
const NAME = { fix: 'Fix and return', swap: 'Covered swap', upgrade: 'Upgrade' };
const pct = (v) => Math.round(v * 100);

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

// ---------------------------------------------------------------- helpers shared by the steps
async function openPage(p, url, ready = '#view') {
  await p.goto(url);
  await p.reload();
  await p.locator(ready).first().waitFor({ timeout: FIRST });
}

/** The case id of a ticket (the asset key of its case is the ticket number). */
async function caseOf(p, ticket, ms = SYNC) {
  return until(
    async () => {
      const r = await must(p, 'cases.list', { q: ticket, limit: 10 });
      return (r.rows || []).find((x) => x.id)?.id || null;
    },
    `no case for ${ticket}`,
    ms,
    p,
  );
}
/** The case record and its service-desk block, from the screen API. */
async function screenOf(p, id) {
  const s = await getJson(p, '/api/screens/case/' + encodeURIComponent(id));
  if (!s || !s.case) throw new Error(`${id}: the screen API gave no case (${JSON.stringify(s).slice(0, 120)})`);
  return s.case;
}
/** `prefer`'s page when its tenant sees the case, else the Admin's; `by` names who it is. */
async function viewerFor(prefer, id) {
  const p = await as(prefer);
  try {
    const c = await screenOf(p, id);
    if (c.serviceDesk) return { p, by: prefer };
  } catch {
    // not visible to that account: the Admin looks instead
  }
  return { p: await as('admin'), by: `admin (${prefer} cannot see ${ORG})` };
}
const tabUrl = (id, tab, stage = 6) => `${base}/#/product/${id}/stage/${stage}?tab=${tab}`;
async function openTab(p, id, tab) {
  await p.goto(tabUrl(id, tab));
  await p.locator('#view').waitFor();
  await p.waitForTimeout(500);
}

/** Wait until the page text matches every pattern; the error names the first that does not. */
async function pageHas(p, pats, what, ms = UI) {
  return until(
    async () => {
      const t = await view(p);
      return pats.every((x) => (x instanceof RegExp ? x.test(t) : t.includes(x))) ? t : null;
    },
    `${what}: the page does not read ${pats.map(String).join(' and ')}`,
    ms,
    p,
  );
}

/** A source's detail from the sources screen (null until it exists). */
const sourceOf = async (p, sid) => {
  const s = await getJson(p, '/api/screens/integration/sources/' + encodeURIComponent(sid));
  return deep(s, (o) => o.id === sid && 'method' in o);
};
const synced = (p, sid) =>
  until(
    async () => {
      const s = await sourceOf(p, sid);
      return s && s.lastSync != null && !s.syncing ? s : null;
    },
    `${sid} did not finish its first sync`,
    SYNC,
    p,
  );

// ---------------------------------------------------------------- 1
await step('1 Market tables: finance edits FR labour to 48 EUR, the Approver approves v2', async () => {
  // the org unit exists after smoke-p9-3 only; on a fresh stack the Modeler page says "No org unit tool-fleet-a"
  await callAction(await as('admin'), 'org.create', { id: ORG, parent_id: 'workspace', kind: 'company', name: 'Tool fleet A' });
  const fin = await as('finance');
  await openPage(fin, MODELER, '#mt-market');
  await fin.locator('#mt-market').selectOption('FR');
  await fin.getByRole('button', { name: /^FR labour rates v1$/i }).click();
  const ed = fin.locator('[data-table-editor]').first();
  await ed.waitFor();
  await ed.getByLabel('per_hour', { exact: true }).fill('48');
  await ed.locator('#mt-from').fill('2026-10-01');
  await ed.getByRole('button', { name: 'Save as new version' }).click();
  const v2 = fin.getByRole('button', { name: /^FR labour rates v2$/i });
  await v2.waitFor({ timeout: UI }).catch(() => {
    throw new Error('no "FR labour rates v2" draft after saving (reset the stack first?): ' + flat(fin.url()));
  });
  await v2.click();
  const ed2 = fin.locator('[data-table-editor]').first();
  await ed2.getByRole('button', { name: 'Submit', exact: true }).click();
  await until(async () => (await fin.locator('[data-table-status="submitted"]').count()) > 0, 'v2 did not read Submitted', UI, fin);
  // Finance may draft and submit but not approve: the button is off and the page says why
  const approveBtn = fin.locator('[data-table-editor]').first().getByRole('button', { name: 'Approve', exact: true });
  if (!(await approveBtn.isDisabled())) throw new Error("Finance's Approve button is enabled");
  const why = flat(await fin.locator('[data-table-why]').first().innerText());
  if (!/cannot approve|Maker-checker/.test(why)) throw new Error(`Finance's Approve button gives no reason: "${why}"`);

  const ap = await as('approver');
  await openPage(ap, MODELER, '#mt-market');
  await ap.locator('#mt-market').selectOption('FR');
  await ap.getByRole('button', { name: /^FR labour rates v2$/i }).click();
  await ap.locator('[data-table-editor]').first().getByRole('button', { name: 'Approve', exact: true }).click();
  const listed = () => must(ap, 'marketTable.list', { pack: 'tool_fleet', flow: 'service_desk', market: 'FR', name: 'labour' });
  await until(async () => ((await listed()).tables || []).find((t) => t.version === 2 && t.status === 'approved'), 'v2 did not read approved', UI, ap);
  await ap.getByRole('button', { name: /^FR labour rates v2$/i }).waitFor();
  const row = ((await listed()).tables || []).find((t) => t.version === 2);
  const rate = row && (row.body?.values?.per_hour ?? row.body?.values?.FR?.per_hour);
  if (!row || row.status !== 'approved' || Number(rate) !== 48) throw new Error('the API reads v2 as ' + JSON.stringify(row && { status: row.status, body: row.body }));
  return `"${why}" · v2 approved at ${rate} ${row.currency || 'EUR'}`;
});

// ---------------------------------------------------------------- 2
await step('2 Sources: sdesk and rephist synced, the service-desk cases open', async () => {
  const admin = await as('admin');
  const dev = await as('developer');
  await callAction(admin, 'org.create', { id: ORG, parent_id: 'workspace', kind: 'company', name: 'Tool fleet A' }); // exists after smoke-p9-3
  // contracts and recalls first: the lines' gates read them (best effort: the options do not need a contract)
  for (const sid of ['fleet', 'recall']) await callAction(dev, 'source.reconnect', { source_id: sid });
  // the repair history and the refurbished stock are shared (no org unit) so every org's estimates read them
  await must(dev, 'source.reconnect', { source_id: 'rephist' });
  await synced(dev, 'rephist');
  // the tickets belong to an org unit (a ticket of a source bound to none stays pending): register, bind, read
  await must(dev, 'source.reconnect', { source_id: 'sdesk' });
  const src = await until(() => sourceOf(dev, 'sdesk'), 'sdesk is not registered', UI, dev);
  const d = {
    type: src.type, name: src.name, vendor: src.vendor, ver: src.ver, env: src.env, url: src.url, method: src.method,
    cfg: { ...(src.cfg || {}) }, interval: src.interval, auth: src.auth, owner: src.owner,
  };
  const maps = (src.mappings || []).filter(Array.isArray);
  await must(admin, 'source.update', { mode: 'edit', id: 'sdesk', d, maps, ops: { read: src.read || [], write: src.write || [] }, note: '', org_unit_id: ORG });
  await synced(dev, 'sdesk');
  let id = await caseOf(admin, 'CS0010042', Math.max(20000, UI)).catch(() => null);
  if (!id) {
    // the first sync read the tickets before the bind: read everything again through the source's ingest workflow
    const wf = await must(dev, 'workflow.create', { type: 'ingest', src: 'sdesk' });
    const detail = await getJson(dev, '/api/screens/workflows/' + encodeURIComponent(wf.id));
    const w = detail.workflow;
    if (!w?.graph) throw new Error(`workflow ${wf.id} has no graph: ${JSON.stringify(detail).slice(0, 200)}`);
    const g0 = JSON.parse(JSON.stringify(w.graph));
    const conn = g0.nodes.find((n) => n.k === 'conn');
    conn.cfg = { ...(conn.cfg || {}), mode: 'full' };
    // the connector alone (the default graph's gateway and map fail the publish checks); the source's own hook opens the cases
    const g = { ...g0, nodes: [conn], edges: [] };
    await must(dev, 'workflow.save', { id: wf.id, name: w.name, owner: w.owner, trig: w.trig, graph: g });
    await must(dev, 'workflow.publish', { id: wf.id });
    await must(dev, 'source.sync', { source_id: 'sdesk' });
    id = await caseOf(admin, 'CS0010042').catch(() => {
      throw new Error('no case for CS0010042 after binding sdesk to ' + ORG + ' and a full read (is the tool-fleet flow published for the org?)');
    });
  }
  await caseOf(admin, 'CS0010050');
  const ret = JSON.stringify(await getJson(admin, '/api/screens/product/returned'));
  if (!/CS0010042/.test(ret)) throw new Error('the Returned assets API does not list CS0010042');
  await openPage(admin, `${base}/#/product/received`);
  await pageHas(admin, [/CS00100\d\d/], 'Returned assets');
  return `CS0010042 is ${id}`;
});

// ---------------------------------------------------------------- 3
await step('3 Ticket CS0010042: estimate, three options, credit lever, a fault posted on a draft line', async () => {
  const admin = await as('admin');
  const id = await caseOf(admin, 'CS0010042');
  const { p, by } = await viewerFor('planner.a', id);
  // the case opens with its estimate and options; a late contract or recall check only re-evaluates it
  const c = await until(
    async () => {
      const x = await screenOf(p, id);
      const ln = x.serviceDesk?.lines?.[0];
      return ln && ln.estimate && ln.options && ln.options.length === 3 ? x : null;
    },
    `${id} has no estimate and three options`,
    SYNC,
    p,
  );
  const sd = c.serviceDesk;
  const ln = sd.lines[0];
  const e = ln.estimate;

  // Ticket
  await openTab(p, id, 'ticket');
  await pageHas(p, [`Ticket ${sd.ticket} · 1 tool`, sd.account, ln.serial], 'Ticket tab');
  if (sd.ticket !== 'CS0010042' || sd.account !== 'ACC-US-0042') throw new Error(`the API reads ticket ${sd.ticket}, account ${sd.account}`);

  // Estimate
  await openTab(p, id, 'estimate');
  await pageHas(p, [`${e.n} similar repairs`, e.auto ? 'Priced without a technician' : 'Draft: a technician checks'], 'Estimate tab');
  if (e.n !== 186) throw new Error(`the estimate rests on ${e.n} similar repairs, not 186`);
  if (!e.auto) throw new Error(`the estimate is a draft: it should be priced without a technician (reason: ${e.reason})`);

  // Options
  await openTab(p, id, 'options');
  const names = ln.options.map((o) => NAME[o.k]);
  if (names.some((n) => !n) || new Set(names).size !== 3) throw new Error('the API options are ' + ln.options.map((o) => o.k).join(', '));
  const t = await pageHas(p, [...names, 'US labour rates v1'], 'Options tab');
  const recommended = NAME[ln.best];
  if (!ln.best || !t.includes(`${recommended} (recommended)`)) throw new Error(`the page does not mark "${recommended}" as recommended`);
  if (sd.approval && !t.includes(`Approval: ${sd.approval.owner}`)) throw new Error(`the page does not read "Approval: ${sd.approval.owner}"`);

  // Credit lever: find where the recommendation flips (the API), then move the sliders there and read it on the page
  const whatIf = (lv) => must(p, 'serviceDesk.whatIf', { case_id: id, line: ln.n, ...lv });
  let flipAt = null;
  for (const cr of [0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4]) {
    const r = (await whatIf({ credit_pct: cr })).lines[0];
    if (r.flips) { flipAt = { credit: cr, takeUp: null, r }; break; }
  }
  for (const tu of flipAt ? [] : [0, 0.25, 0.5, 0.75, 1]) {
    const r = (await whatIf({ credit_pct: 0.2, take_up: tu })).lines[0];
    if (r.flips) { flipAt = { credit: 0.2, takeUp: tu, r }; break; }
  }
  if (!flipAt) throw new Error('no credit from 0 to 40% (or take-up) flips the recommendation of ' + ln.serial);
  await openTab(p, id, 'credit');
  const lever = p.locator('[aria-label="Credit lever"]');
  await lever.waitFor();
  if (flipAt.takeUp !== null) {
    await lever.getByLabel('Use the take-up curve').uncheck();
    await lever.locator('input[aria-label="Take-up"]').fill(String(pct(flipAt.takeUp)));
  }
  await lever.locator('input[aria-label="Credit"]').fill(String(pct(flipAt.credit)));
  await pageHas(p, ['This differs from the recommendation the case holds.'], 'Credit lever at ' + pct(flipAt.credit) + '%');
  const x = flipAt.r.crossing;
  if (x) await pageHas(p, [`${NAME[x.to]} beats ${NAME[x.from]} with credit above ${pct(x.credit_pct)}% credit`], 'Credit lever flip line');
  const flipText = `${NAME[flipAt.r.from]} to ${NAME[flipAt.r.to]} at ${pct(flipAt.credit)}% credit`;

  // Post a fault on a draft line (any open ticket case with one; skipped when the data has none)
  let posted = '(no draft line: fault step skipped)';
  const list = await must(admin, 'cases.list', { q: 'CS00', limit: 100 });
  for (const row of (list.rows || []).filter((r) => r.id && r.id !== id)) {
    const cc = await screenOf(admin, row.id).catch(() => null);
    const draft = cc?.serviceDesk?.lines?.find((l) => l.estimate && !l.estimate.auto);
    if (!draft) continue;
    const code = draft.fault_code === 'MOT' ? 'GBX' : 'MOT';
    const eng = await viewerFor('engineer', row.id);
    await openTab(eng.p, row.id, 'estimate');
    const form = eng.p.locator(`[aria-label="Post the fault for ${draft.serial}"]`);
    await form.waitFor();
    await form.locator('select').selectOption(code);
    await form.getByRole('button', { name: 'Post the fault' }).click();
    const after = await until(
      async () => {
        const l = (await screenOf(eng.p, row.id)).serviceDesk.lines.find((q) => q.n === draft.n);
        return l.fault_code === code && l.options && l.options.length > 0 ? l : null;
      },
      `${row.id} line ${draft.n} has no options after the fault ${code}`,
      UI,
      eng.p,
    );
    await openTab(eng.p, row.id, 'options');
    await pageHas(eng.p, [`Options for ${draft.serial}`, ...after.options.map((o) => NAME[o.k])], 'Options after the fault');
    posted = `${eng.by} posted ${code} on ${draft.serial} of ${row.id}: ${after.options.length} options`;
    break;
  }
  return `${by}: ${e.n} similar repairs, ${names.join(' / ')} (best ${recommended}); flips ${flipText}; ${posted}`;
});

// ---------------------------------------------------------------- 4
await step('4 Models: Repair estimate accuracy has one row per family', async () => {
  const admin = await as('admin');
  await openPage(admin, `${base}/#/agents`, '#agRepairAccuracy');
  const btn = admin.locator('#ag-acc-compute');
  if (await btn.count()) await btn.click();
  else await must(admin, 'serviceDesk.computeAccuracy', {});
  const rows = await until(
    async () => {
      const m = await getJson(admin, '/api/screens/agents/models');
      return m.repairAccuracy && m.repairAccuracy.rows.length ? m.repairAccuracy.rows : null;
    },
    'no repair estimate accuracy rows after computing it',
    UI,
    admin,
  );
  const panel = admin.locator('#agRepairAccuracy');
  if (!/Repair estimate accuracy/.test(await panel.innerText())) throw new Error('the panel is not headed "Repair estimate accuracy"');
  await until(async () => (await panel.locator('tr[data-family]').count()) === rows.length, `the page shows ${await panel.locator('tr[data-family]').count()} family rows, the API ${rows.length}`, UI, admin);
  const keys = rows.map((r) => `${r.org_unit_id ?? 'shared'}/${r.model_class}`);
  if (new Set(keys).size !== keys.length) throw new Error('a family has two rows: ' + keys.join(', '));
  const shown = await panel.locator('tr[data-family]').evaluateAll((trs) => trs.map((t) => t.getAttribute('data-family')));
  if (shown.slice().sort().join() !== rows.map((r) => r.model_class).sort().join()) throw new Error(`the page families ${shown} differ from the API's`);
  return `${rows.length} rows: ${shown.join(', ')}`;
});

// ---------------------------------------------------------------- 5
await step('5 Batch CS0010050 splits Upgrade 9 · Fix 11 · Covered swap 2', async () => {
  const admin = await as('admin');
  const id = await caseOf(admin, 'CS0010050');
  const c = await until(
    async () => {
      const x = await screenOf(admin, id);
      return x.serviceDesk?.split ? x : null;
    },
    `${id} has no batch split`,
    SYNC,
    admin,
  );
  const sd = c.serviceDesk;
  const k = sd.split.counts;
  const expect = [['Upgrade', k.upgrade], ['Fix', k.fix], ['Covered swap', k.swap]].filter(([, n]) => n > 0).map(([l, n]) => `${l} ${n}`).join(' · ');
  await openTab(admin, id, 'batch');
  await pageHas(admin, [expect], 'Batch tab');
  if (expect !== 'Upgrade 9 · Fix 11 · Covered swap 2') throw new Error(`the batch splits as "${expect}", not "Upgrade 9 · Fix 11 · Covered swap 2"`);
  if (sd.lines.length !== 22) throw new Error(`the batch has ${sd.lines.length} lines, not 22`);
  await openTab(admin, id, 'ticket');
  await pageHas(admin, [`Ticket CS0010050 · batch ${sd.batchId} · 22 tools`], 'Ticket tab of the batch');
  return expect;
});

// ---------------------------------------------------------------- 6
await step('6 Held upgrade: the Approver approves it, the market terms show, the take-back opens a Returns case', async () => {
  const admin = await as('admin');
  const list = await must(admin, 'cases.list', { q: 'CS00', limit: 100 });
  let found = null;
  for (const row of (list.rows || []).filter((r) => r.id)) {
    const c = await screenOf(admin, row.id).catch(() => null);
    const sd = c?.serviceDesk;
    if (!sd || sd.batch || !sd.approval || sd.approval.owner !== 'Sales' || c.exec || c.chosen) continue;
    const up = sd.lines.find((l) => l.best === 'upgrade');
    if (up && c.recommendation?.id === 'upgrade') { found = { id: row.id, c, up }; break; }
  }
  if (!found) throw new Error('no open single-tool ticket case holds an upgrade for Sales (Approval owner "Sales"); reset the stack first?');
  const { id, c, up } = found;
  const sd = c.serviceDesk;
  await openTab(admin, id, 'options');
  await pageHas(admin, ['Approval: Sales'], 'Options tab of ' + id);

  const approver = await as('approver');
  await callAction(admin, 'decision.submit', { case_id: id }); // as the maker-checker pair the pipeline asks for; already submitted is fine
  const route = c.routes.find((r) => r.id === 'upgrade');
  if (!route) throw new Error(`${id} has no upgrade route`);
  await must(approver, 'decision.approve', { case_id: id, reviewed: true, rationale: 'Service desk smoke: upgrade for the site.', route: route.plan });
  const done = await until(
    async () => {
      const x = await screenOf(approver, id);
      return x.exec?.terms ? x : null;
    },
    `${id} carries no market terms after the approval`,
    UI,
    approver,
  );
  const terms = done.exec.terms;
  await openTab(approver, id, 'options');
  await pageHas(approver, [`Market terms: ${terms.refs.join(', ')}`, 'valid until'], 'Options tab of ' + id);
  if (terms.market !== sd.market) throw new Error(`the terms are for ${terms.market}, the ticket for ${sd.market}`);

  // only time moves: the sale and the transport are acknowledged, then the take-back, which opens the old tool's Returns case
  const returns = await until(
    async () => {
      const r = await must(admin, 'cases.list', { q: up.serial, limit: 10 });
      const row = (r.rows || []).find((x) => x.id && x.id !== id);
      if (row) return row.id;
      const adv = await fetch(SIM + '/_sim/clock/advance', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ hours: 3 }) });
      if (!adv.ok) throw new Error('clock advance failed: ' + adv.status);
      return null;
    },
    `no Returns case for ${up.serial} after the take-back (is the worker running, instructions on?)`,
    SYNC,
    admin,
  );
  await openPage(admin, `${base}/#/product/${returns}/overview`);
  await pageHas(admin, [up.serial], 'Overview of ' + returns);
  return `${id} approved for ${sd.approval.owner}, terms "${terms.refs.join(', ')}", ${returns} opened for ${up.serial}`;
});

// ---------------------------------------------------------------- 7
await step('7 Take-up model: Admin fits it, the candidate shows its log loss against the prior', async () => {
  const admin = await as('admin');
  const before = new Set(((await getJson(admin, '/api/screens/agents/models')).models || []).map((m) => m.id));
  await openPage(admin, `${base}/#/agents`, '#ag-mdl-template');
  await admin.locator('#ag-mdl-template').selectOption('tool_fleet');
  await admin.locator('#ag-mdl-fit-takeup').click();
  const m = await until(
    async () => ((await getJson(admin, '/api/screens/agents/models')).models || []).find((x) => x.kind === 'take_up' && !before.has(x.id)) || null,
    'no new take-up candidate after "Fit take-up model"',
    UI,
    admin,
  );
  if (m.status !== 'candidate' || typeof m.metrics.log_loss !== 'number') throw new Error('the candidate reads ' + JSON.stringify({ status: m.status, metrics: m.metrics }).slice(0, 160));
  const row = admin.locator(`tr[data-model="${m.id}"]`);
  await row.waitFor();
  const t = flat(await row.innerText());
  if (!/candidate/.test(t) || !t.includes('log loss') || !t.includes(m.metrics.log_loss.toFixed(3))) throw new Error(`the row of ${m.id} reads: ${t.slice(0, 200)}`);
  const prior = m.metrics.baseline_log_loss;
  return `${m.id}: log loss ${m.metrics.log_loss.toFixed(3)}${typeof prior === 'number' ? ` (prior ${prior.toFixed(3)})` : ''}`;
});

await browser.close();
if (errors.length) {
  say('FAIL page errors:', errors.slice(0, 5).join(' | '));
  process.exit(1);
}
say(`smoke-p9-4: all ${stepsRun} steps passed`);
