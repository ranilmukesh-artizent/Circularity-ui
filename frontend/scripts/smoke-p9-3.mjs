/**
 * Plan 9, Phase 3 demo smoke (P9-3): the tool fleet's returns, one line per step (PASS, or FAIL with the step and the
 * text that was missing, then exit 1 at once). This file holds the steps built so far; the later P9-3 tasks add theirs.
 *
 *   1  Admin creates org unit `tool-fleet-a` (segment). Developer registers and connects `fleet` bound to it, and
 *      publishes an ingest workflow on `fleet` whose Open case step is set: template tool_fleet, org tool-fleet-a, asset
 *      field serial, reason field kind, facts toolClass, contractId, lineId, site. A sync opens 18 tool cases; the
 *      Returned assets list shows CMH-48213 with "Case opened from contract_end".
 *
 * The UI has no one-click setup for this, so the script calls the app's own actions as the signed-in person (the same
 * ones the Source Map and Workflow Studio call) and reads the result in the pages. Needs the worker (the sync runs on it)
 * and source-sim with the fleet mock.
 *
 * Changes state, and resets nothing itself. The lead runs:
 *   bash scripts/dev/reset.sh && bash scripts/dev/wait-idle.sh
 *   node frontend/scripts/smoke-p9-3.mjs http://localhost:5173
 *   bash scripts/dev/reset.sh
 * (hold the api test lock meanwhile). Screenshots of a failing step go to SMOKE_OUT (default: <OS temp>/smoke-p9-3).
 * The last line is "smoke-p9-3: all 1 steps passed".
 */
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const out = process.env.SMOKE_OUT || path.join(tmpdir(), 'smoke-p9-3');
const ORG = 'tool-fleet-a';
const SID = 'fleet';
const UI = 30000;
const SYNC = 180000;
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

async function step(name, fn) {
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
await step('1 Returns: 18 tool cases opened, CMH-48213 from contract_end', async () => {
  const admin = await as('admin');
  await must(admin, 'org.create', { id: ORG, parent_id: 'workspace', kind: 'segment', name: 'Tool fleet A' });
  const dev = await as('developer');
  await must(dev, 'source.reconnect', { source_id: SID });
  // the Open case step names the org unit itself (source.update's edit form needs the whole connection, so no bind here)
  const wf = await must(dev, 'workflow.create', { type: 'ingest', src: SID });
  const d = await getJson(dev, '/api/screens/workflows/' + encodeURIComponent(wf.id));
  const w = d.workflow || d;
  // the graph is the connector and the Open case step only (the default one has a gateway and a map the checks refuse)
  const conn = w.graph.nodes.find((n) => n.k === 'conn');
  conn.cfg = { ...(conn.cfg || {}), resources: ['returns'] };
  const caseNode = {
    id: 'case', k: 'xf', ref: 'x_case', x: conn.x + 120, y: conn.y,
    cfg: { template: 'tool_fleet', reason: 'contract_end', asset_field: 'serial', org_unit_id: ORG, reason_field: 'kind', facts: ['toolClass', 'contractId', 'lineId', 'site'] },
  };
  const g = { ...w.graph, nodes: [conn, caseNode], edges: [{ id: `${conn.id}>case`, a: conn.id, b: 'case', locked: false }] };
  await must(dev, 'workflow.save', { id: wf.id, name: w.name, owner: w.owner, trig: w.trig, graph: g });
  await must(dev, 'workflow.publish', { id: wf.id });
  await must(dev, 'source.sync', { source_id: SID });
  const n = await until(
    async () => {
      // the Returned assets read, counted by the tool serials in it (CMH-48213 ...): 18 once the sync has run
      const r = JSON.stringify(await getJson(dev, '/api/screens/product/returned'));
      const serials = new Set(r.match(/\b(?:CMH|BRK|DCD|CRH|AGR|LSR)-\d+\b/g) || []);
      return serials.size === 18 ? serials.size : 0;
    },
    'the sync did not open 18 tool cases in ' + ORG,
    SYNC,
    dev,
  );
  const p = await as('admin');
  await p.goto(`${base}/#/product/received`);
  await p.locator('#view').waitFor();
  await until(
    async () => /CMH-48213/.test(await p.locator('#view').innerText()) && /Case opened from contract_end/.test(await p.locator('#view').innerText()),
    'Returned assets does not show CMH-48213 with "Case opened from contract_end"',
    UI,
    p,
  );
  return `${n} cases`;
});

await browser.close();
if (errors.length) {
  say('FAIL page errors:', errors.slice(0, 5).join(' | '));
  process.exit(1);
}
say('smoke-p9-3: all 1 steps passed');
