/**
 * Plan 9, Phase 5 demo smoke (P9-5): contract renewals, one line per step (PASS, or FAIL with the step and the text that
 * was missing, then exit 1 at once). This file holds the steps built so far; the later P9-5 tasks add theirs.
 *
 *   1  Admin creates org unit `tool-fleet-a` if it is missing; Developer connects and syncs `fleet` (the contracts),
 *      `parts` (the refurbished stock) and `repairlog` (the measured lives) and waits until each sync has finished. Admin
 *      then runs the daily scan from the worker's job (no UI: the smoke posts the job `refresh.scan` for 2026-10-07 to the
 *      tasks API, /api/v1/tasks, as Admin's Tasks screen does). The Returned assets list shows the refresh cases ("Case
 *      opened from contract_refresh") and FC-30117's panel shows 14 lines.
 *   2  The same panel lists each tool with its action and reason and the split "keep N, swap M, upgrade K" (the three add
 *      up to FC-30117's 14 lines).
 *   3  Each swap line is matched to a refurbished unit RU-7... of the parts system's stock (whichever families the lives
 *      make a swap).
 *   6  (runs before 5: the levers hide once a person approves) Admin moves the swap threshold to 40 on FC-30117's panel and reads
 *      the split before and after, the tools that change action and the fee and renewal impact (refresh.whatIf: nothing stored
 *      or sent).
 *   5  Admin sets the fleet and parts sources to Read / write (source.update, as smoke-p9-3 does; a reset leaves them
 *      read-only, and nothing is sent to a read-only system); planner.a (after a tenant access request to `tool-fleet-a` that
 *      the Admin approves) submits FC-30117, the Approver (Sales or Fleet desk) approves the proposal route; only time moves (the source-sim
 *      clock) and the panel shows "Proposal sent PR-…", "Contract lines drafted DL-…" and "Units reserved RU-…".
 *
 * Needs the worker (the sync and the job run on it) and source-sim with the fleet mock. Changes state, and resets nothing
 * itself. The lead runs:
 *   bash scripts/dev/reset.sh && bash scripts/dev/wait-idle.sh
 *   node frontend/scripts/smoke-p9-5.mjs http://localhost:5173
 *   bash scripts/dev/reset.sh
 * (hold the api test lock meanwhile). Screenshots of a failing step go to SMOKE_OUT (default: <OS temp>/smoke-p9-5).
 * The last line is "smoke-p9-5: all <N> steps passed", N being the number of steps that ran.
 */
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
// Guard: this smoke moves source-sim's clock. Against a stack other than the main one (web :5173), say which
// source-sim belongs to it; the default :8100 is the main stack's, and a run without it moved that clock.
if (new URL(base).port !== '5173' && !process.env.SIM_PORT && !process.env.SIM_URL) {
  console.error(`smoke-p9-5: ${base} is not the main stack (:5173). Set SIM_PORT or SIM_URL to its source-sim; ` +
    'the default localhost:8100 belongs to the main stack.');
  process.exit(2);
}
const out = process.env.SMOKE_OUT || path.join(tmpdir(), 'smoke-p9-5');
const ORG = 'tool-fleet-a';
const SID = 'fleet';
const TODAY = '2026-10-07'; // FC-30117 ends 2027-01-05: its window opens on this day
const UI = Number(process.env.SMOKE_UI_MS) || 30000; // SMOKE_UI_MS: a slower machine
const SYNC = Number(process.env.SMOKE_SYNC_MS) || 180000; // SMOKE_SYNC_MS: a longer wait for a sync on a loaded machine
const LONG = Number(process.env.SMOKE_LONG_MS) || 720000; // SMOKE_LONG_MS: a longer wait for the worker on a loaded machine
// the sources the refresh panel reads: the contracts and their lines (fleet), the refurbished stock a swap is matched to (parts)
// and the measured lives that decide keep or swap (repairlog). Every smoke runs from a reset, so this one connects them itself.
const SOURCES = [SID, 'parts', 'repairlog'];
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
const postJson = (p, url, body) =>
  p.evaluate(
    async ([url, body]) => {
      const r = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + sessionStorage.getItem('circ-api-token') },
        body: JSON.stringify(body),
      });
      return r.json();
    },
    [url, body],
  );
/** The first object in `o` (depth first) that `ok` accepts, or null. */
const deepFind = (o, ok) => {
  if (o && typeof o === 'object') {
    if (ok(o)) return o;
    for (const v of Object.values(o)) {
      const r = deepFind(v, ok);
      if (r) return r;
    }
  }
  return null;
};
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
await step('1 Refresh: the scan opens FC-30117 with 14 lines', async () => {
  const admin = await as('admin');
  await callAction(admin, 'org.create', { id: ORG, parent_id: 'workspace', kind: 'company', name: 'Tool fleet A' }); // exists after smoke-p9-3
  const dev = await as('developer');
  // each source's sync is queued by its reconnect (a second sync asked meanwhile is dropped as a duplicate); the worker runs
  // one job at a time, so the scan is posted only once every sync has FINISHED (the repair log's first full sync takes minutes)
  const lastRun = async (sid) => (await getJson(dev, '/api/screens/integration/sources/' + sid))?.sync_history?.[0] || null;
  const before = {};
  for (const sid of SOURCES) {
    before[sid] = JSON.stringify(await lastRun(sid));
    await must(dev, 'source.reconnect', { source_id: sid });
    await must(dev, 'source.sync', { source_id: sid });
  }
  const synced = [];
  for (const sid of SOURCES) {
    const h = await until(
      async () => {
        const r = await lastRun(sid);
        return r && JSON.stringify(r) !== before[sid] && r.dur !== '—' ? r : null; // a new run that has finished
      },
      `the ${sid} sync did not finish`,
      SYNC,
      dev,
    );
    if (!h.ok) throw new Error(`the ${sid} sync did not succeed: ${JSON.stringify(h)}`);
    synced.push(`${sid} ${h.rows} rows`);
  }
  // no UI for the schedule: the job the worker runs daily is posted to the tasks API (a shared fleet source names no org unit);
  // the dedupe key keeps one such job queued while the worker is still busy with what the syncs queued
  const caseOf = async () => {
    const r = await must(admin, 'cases.list', { q: 'FC-30117', limit: 5 });
    return (r.rows || []).find((x) => x.id)?.id || null;
  };
  const scan = { kind: 'refresh.scan', payload: { today: TODAY, org_unit_id: ORG }, dedupe_key: `refresh.scan:smoke:${ORG}:${TODAY}` };
  const id = await until(
    async () => {
      await postJson(admin, '/api/v1/tasks', scan);
      await admin.waitForTimeout(5000);
      return caseOf();
    },
    'the scan did not open a refresh case for FC-30117 in ' + ORG + ' (synced: ' + synced.join(', ') + ')',
    LONG,
    admin,
  );
  // "Case opened from contract_refresh" is the stage log row, which no page prints: the reason is read from the case's own
  // intake record (the case screen's `intake.reason`); the panel below is what a person sees of it
  const reason = (await getJson(admin, '/api/screens/case/' + id)).case?.intake?.reason;
  if (reason !== 'contract_refresh') throw new Error(`the case ${id} was opened from "${reason}", not contract_refresh`);
  await admin.goto(`${base}/#/product/${id}/overview`);
  await admin.locator('#view').waitFor();
  const t = await until(
    async () => {
      const x = await admin.locator('[data-testid="rf-lines-count"]').first().innerText();
      return /^14 lines/.test(x) ? x : null;
    },
    `${id}'s refresh panel does not show 14 lines`,
    UI,
    admin,
  );
  return `${id}: ${t} (synced: ${synced.join(', ')})`;
});
// ---------------------------------------------------------------- 2
await step('2 Refresh: FC-30117 shows its keep, swap and upgrade split', async () => {
  const admin = await as('admin');
  const text = await until(
    async () => {
      const x = await admin.locator('[data-testid="rf-tools-totals"]').first().innerText();
      return /^keep \d+, swap \d+, upgrade \d+$/.test(x) ? x : null;
    },
    'the refresh panel does not show "keep N, swap M, upgrade K"',
    UI,
    admin,
  );
  const n = (text.match(/\d+/g) || []).reduce((a, b) => a + Number(b), 0);
  if (n !== 14) throw new Error(`the split "${text}" does not add up to 14 tools`);
  const rows = await admin.locator('[data-testid="rf-tools"] tbody tr').count();
  if (rows !== 14) throw new Error(`the tools list has ${rows} rows, not 14`);
  return text;
});
// ---------------------------------------------------------------- 3
await step('3 Refresh: each swap is matched to refurbished stock RU-7... from the parts system', async () => {
  // whichever families the measured lives make a swap: each swap line names a unit of the parts system's refurbished stock
  const admin = await as('admin');
  const swaps = Number(((await admin.locator('[data-testid="rf-tools-totals"]').first().innerText()).match(/swap (\d+)/) || [])[1]);
  if (!swaps) throw new Error('FC-30117 has no swap to match (step 2 split)');
  let last = 'no match table';
  const rows = await until(
    async () => {
      const r = await admin
        .locator('[data-testid="rf-match"] tbody tr')
        .evaluateAll((trs) => trs.map((t) => ({ serial: t.dataset.serial, cls: t.dataset.cls, unit: t.dataset.unit, text: t.innerText })));
      last = r.map((x) => `${x.serial} ${x.unit || x.text.replace(/\s+/g, ' ')}`).join('; ') || 'no match rows';
      const ok = r.length === swaps && r.every((x) => /^RU-7/.test(x.unit) && /refurbished stock/.test(x.text));
      return ok ? r : null;
    },
    `the refresh panel does not match each of the ${swaps} swaps to refurbished stock RU-7...`,
    UI,
    admin,
  ).catch((e) => {
    throw new Error(`${e.message}; last seen: ${last}`);
  });
  return rows.map((x) => `${x.serial} (${x.cls}) → ${x.unit}`).join(', ');
});
// ---------------------------------------------------------------- 4
await step('4 Refresh: the proposal is priced and waits for a person', async () => {
  const admin = await as('admin');
  const pricing = await until(
    async () => {
      const x = await admin.locator('[data-testid="rf-likelihood"]').first().innerText();
      return /^Renewal likelihood \d+% with a proposal \(\d+% without\)$/.test(x) ? x : null;
    },
    'the refresh panel does not show "Renewal likelihood N% with a proposal (M% without)"',
    UI,
    admin,
  );
  const basis = await admin.locator('[data-testid="rf-basis"]').first().innerText();
  if (!/modelled, observational/.test(basis)) throw new Error('the renewal basis does not say it is modelled: ' + basis);
  const who = await admin.locator('[data-testid="rf-approval-text"]').first().innerText();
  if (!/^Waits for (Sales: credits .* are over \$300|the Fleet desk)$/.test(who)) throw new Error('the approval line says: ' + who);
  return `${pricing}; ${who}`;
});
// ---------------------------------------------------------------- 6 (runs before 5: the levers hide once a person approves)
await step('6 Refresh: moving the swap threshold to 40 shows the tools that change action and the impact', async () => {
  const admin = await as('admin');
  const id = (await must(admin, 'cases.list', { q: 'FC-30117', limit: 5 })).rows.find((x) => x.id)?.id;
  if (!id) throw new Error('no refresh case for FC-30117 (run steps 1 to 4 first)');
  await admin.goto(`${base}/#/product/${id}/overview`);
  await admin.locator('#view').waitFor();
  await admin.locator('[data-testid="rf-lever-threshold"]').first().fill('40');
  const split = await until(
    async () => {
      const x = await admin.locator('[data-testid="rf-lever-split"]').first().innerText();
      return /^keep \d+, swap \d+, upgrade \d+ → keep \d+, swap \d+, upgrade \d+$/.test(x) ? x : null;
    },
    'the levers do not show the split before and after',
    UI,
    admin,
  );
  const changed = await admin.locator('[data-testid="rf-lever-changed"]').first().innerText({ timeout: 2000 }).catch(() => 'no tool changes action');
  const impact = await admin.locator('[data-testid="rf-lever-impact"]').first().innerText();
  if (!/Fee a month .*renewal likelihood/.test(impact)) throw new Error('the impact line says: ' + impact);
  return `${split}; ${changed.replace(/\n/g, '; ')}`;
});
// ---------------------------------------------------------------- 5
await step('5 Refresh: planner.a submits, the Approver approves, the panel shows proposal sent, lines drafted, units reserved', async () => {
  const SIM = process.env.SIM_URL || `http://localhost:${process.env.SIM_PORT || 8100}`;
  const admin = await as('admin');
  // planner.a belongs to Customer A and cannot see the new org unit's cases from a reset: the real flow is a tenant access
  // request the Admin approves (access.requestTenant, access.decideRequest, as smoke-p9-3 does); then it signs in afresh
  const asked = await callAction(await as('planner.a'), 'access.requestTenant', { tenant: ORG, reason: 'Smoke: submit the refresh case of ' + ORG });
  if (asked.ok) await must(admin, 'access.decideRequest', { id: asked.output.id, decision: 'approve' });
  else if (!/already|access/i.test(JSON.stringify(asked.error || asked))) throw new Error('access.requestTenant: ' + JSON.stringify(asked.error || asked).slice(0, 200));
  await pages['planner.a'].context().close();
  delete pages['planner.a'];
  const planner = await as('planner.a');
  const approver = await as('approver');
  // the fleet contract system (proposal, draft lines) and the parts system (reserve units) are connected read-only from a reset:
  // the steps are only sent once their access is Read / write (source.update with a write operation sets it, as smoke-p9-3 does)
  for (const [sid, write] of [[SID, ['proposal send', 'draft lines']], ['parts', ['reserve units']]]) {
    const src = deepFind(await getJson(admin, '/api/screens/integration/sources/' + sid), (o) => o.id === sid && 'method' in o);
    if (!src) throw new Error(`no ${sid} source on the Integration screen`);
    if (src.rw && !/^(Read|Read \(import\)|—)$/.test(src.rw)) continue; // Read / write already
    const d = { type: src.type, name: src.name, vendor: src.vendor, ver: src.ver, env: src.env, url: src.url, method: src.method, cfg: { ...(src.cfg || {}) }, interval: src.interval, auth: src.auth, owner: src.owner };
    const ops = { read: src.read?.length ? src.read : ['records'], write: [...new Set([...(src.write || []), ...write])] };
    const up = await callAction(admin, 'source.update', { mode: 'edit', id: sid, d, maps: (src.mappings || []).filter(Array.isArray), ops, note: 'Smoke: send the refresh proposal' });
    if (!up.ok && !/No changes to save/.test(JSON.stringify(up.error || up))) throw new Error(`source.update ${sid}: ${JSON.stringify(up.error || up).slice(0, 200)}`);
  }
  const r = await must(admin, 'cases.list', { q: 'FC-30117', limit: 5 });
  const id = (r.rows || []).find((x) => x.id)?.id;
  if (!id) throw new Error('no refresh case for FC-30117 (run steps 1 to 4 first)');
  await must(planner, 'decision.submit', { case_id: id });
  const view = () =>
    approver.evaluate(
      async (u) => (await fetch(u, { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('circ-api-token') } })).json(),
      `/api/screens/refresh/${id}`,
    );
  const v0 = await view();
  if (v0.execution) throw new Error('the panel shows an execution before the approval');
  const proposal = v0.pricing.routes.find((x) => x.id === 'proposal');
  const body = { case_id: id, reviewed: true, rationale: 'Refresh proposal reviewed for the customer.', route: proposal.name };
  await must(approver, v0.pricing.best === 'proposal' ? 'decision.approve' : 'decision.override', body);
  await admin.goto(`${base}/#/product/${id}/overview`);
  await admin.locator('#view').waitFor();
  // only time moves: the worker sends each step, and the systems' events (or the simulated clock) acknowledge it
  const text = await until(
    async () => {
      const t = await admin.locator('[data-testid="rf-execution"]').first().innerText().catch(() => '');
      if (/Proposal sent PR-\d+/.test(t) && /Contract lines drafted DL-\d+/.test(t) && /Units reserved RU-\d+/.test(t)) return t;
      await fetch(SIM + '/_sim/clock/advance', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ hours: 3 }) });
      await admin.reload();
      await admin.locator('#view').waitFor();
      return null;
    },
    'the panel does not show "Proposal sent PR-...", "Contract lines drafted DL-..." and "Units reserved RU-..." (worker running, instructions on?)',
    SYNC,
    admin,
  );
  return text.split('\n').filter((l) => /Proposal sent|Contract lines drafted|Units reserved/.test(l)).join('; ');
});
// ---------------------------------------------------------------- 7
await step('7 Analytics: the Contract renewals section shows both rates, the segments and the caveat', async () => {
  const exec = await as('exec');
  await exec.goto(`${base}/#/analytics`);
  await exec.locator('#view').waitFor();
  // the Analytics view picker is a tab list (components/kit/Segmented: role tab)
  await exec.getByRole('tab', { name: 'Packs', exact: true }).or(exec.getByRole('radio', { name: 'Packs' })).first().click();
  // the Packs view opens on the first pack the account sees: the renewals belong to the tool fleet pack's view
  await exec.getByLabel('Pack', { exact: true }).selectOption('tool_fleet');
  const sec = exec.locator('[data-testid="renewals"]');
  await sec.waitFor({ timeout: UI });
  const text = await sec.innerText();
  if (!/With a proposal: .*\d/.test(text) || !/Without a proposal: /.test(text)) throw new Error('the section shows no rates: ' + text.slice(0, 200));
  if (!/This comparison is observational; a 20% region publish is the proof\./.test(text)) throw new Error('the caveat is missing');
  return text.split('\n').find((l) => /With a proposal/.test(l)) || '';
});
await browser.close();
if (errors.length) {
  say('FAIL page errors:', errors.slice(0, 5).join(' | '));
  process.exit(1);
}
say(`smoke-p9-5: all ${stepsRun} steps passed`);
