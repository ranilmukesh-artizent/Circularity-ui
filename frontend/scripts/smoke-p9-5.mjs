/**
 * Plan 9, Phase 5 demo smoke (P9-5): contract renewals, one line per step (PASS, or FAIL with the step and the text that
 * was missing, then exit 1 at once). This file holds the steps built so far; the later P9-5 tasks add theirs.
 *
 *   1  Admin creates org unit `tool-fleet-a` if it is missing; Developer connects and syncs `fleet`. Admin runs the daily
 *      scan from the worker's job (no UI: the smoke posts the job `refresh.scan` for 2026-10-07 to the tasks API,
 *      /api/v1/tasks, as Admin's Tasks screen does). The Returned assets list shows the refresh cases ("Case opened from
 *      contract_refresh") and FC-30117's panel shows 14 lines.
 *   2  The same panel lists each tool with its action and reason and the split "keep N, swap M, upgrade K" (the three add
 *      up to FC-30117's 14 lines).
 *
 * Needs the worker (the sync and the job run on it) and source-sim with the fleet mock. Changes state, and resets nothing
 * itself. The lead runs:
 *   bash scripts/dev/reset.sh && bash scripts/dev/wait-idle.sh
 *   node frontend/scripts/smoke-p9-5.mjs http://localhost:5173
 *   bash scripts/dev/reset.sh
 * (hold the api test lock meanwhile). Screenshots of a failing step go to SMOKE_OUT (default: <OS temp>/smoke-p9-5).
 * The last line is "smoke-p9-5: all 2 steps passed".
 */
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const out = process.env.SMOKE_OUT || path.join(tmpdir(), 'smoke-p9-5');
const ORG = 'tool-fleet-a';
const SID = 'fleet';
const TODAY = '2026-10-07'; // FC-30117 ends 2027-01-05: its window opens on this day
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
await step('1 Refresh: the scan opens FC-30117 with 14 lines', async () => {
  const admin = await as('admin');
  await callAction(admin, 'org.create', { id: ORG, parent_id: 'workspace', kind: 'company', name: 'Tool fleet A' }); // exists after smoke-p9-3
  const dev = await as('developer');
  await must(dev, 'source.reconnect', { source_id: SID });
  await must(dev, 'source.sync', { source_id: SID });
  // no UI for the schedule: the job the worker runs daily is posted to the tasks API (a shared fleet source names no org unit)
  const caseOf = async () => {
    const r = await must(admin, 'cases.list', { q: 'FC-30117', limit: 5 });
    return (r.rows || []).find((x) => x.id)?.id || null;
  };
  const id = await until(
    async () => {
      await postJson(admin, '/api/v1/tasks', { kind: 'refresh.scan', payload: { today: TODAY, org_unit_id: ORG } });
      await admin.waitForTimeout(3000);
      return caseOf();
    },
    'the scan did not open a refresh case for FC-30117 in ' + ORG,
    SYNC,
    admin,
  );
  await admin.goto(`${base}/#/product/received`);
  await admin.locator('#view').waitFor();
  await until(
    async () => /Case opened from contract_refresh/.test(await admin.locator('#view').innerText()),
    'Returned assets does not show "Case opened from contract_refresh"',
    UI,
    admin,
  );
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
  return `${id}: ${t}`;
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
await browser.close();
if (errors.length) {
  say('FAIL page errors:', errors.slice(0, 5).join(' | '));
  process.exit(1);
}
say('smoke-p9-5: all 2 steps passed');
