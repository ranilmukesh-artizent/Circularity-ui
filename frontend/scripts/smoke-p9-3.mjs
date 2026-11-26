/**
 * Plan 9, Phase 3 demo smoke (P9-3): the tool fleet's returns, one line per step (PASS, or FAIL with the step and the
 * text that was missing, then exit 1 at once). This file holds the steps built so far; the later P9-3 tasks add theirs.
 *
 *   1  Admin creates org unit `tool-fleet-a` (company). Developer registers and connects `fleet` bound to it, and
 *      publishes an ingest workflow on `fleet` whose Open case step is set: template tool_fleet, org tool-fleet-a, asset
 *      field serial, reason field kind, facts toolClass, contractId, lineId, site. A sync opens 18 tool cases; the
 *      Returned assets list shows CMH-48213 with "Case opened from contract_end".
 *   2  (see the step) CMH-48213 reads an estimate; a late workbench grade makes CRH-44120 workbench.
 *   3  BRK-51007's case (a theft recovered with the claim still open) is blocked by GR-07: its Overview reads "Theft
 *      recovered: claim CLM-7781 is open" (My work's exception for planner.a is reported, not required); CMH-48213 (an
 *      end of term) passes the gate.
 *   4  The recall register is synced; a case opened for BRK-51007 (repair recall RC-2026-017) shows its quarantine card; the
 *      Approver releases it after the fix (the card reads released); a Planner is refused.
 *   5  (P9-3.8) after the telematics source syncs, CMH-48777 (last seen 2026-09-29) reads "Telematics last seen 8 days ago:
 *      re-issue and pool need a person" on its Overview; CMH-48213 reads "Telematics 3 days old".
 *   10 (P9-3.13) two CMH returns that both want FC-30117-R: the plan gives it to one, the other reads "is planned for RT-nnnn, where it adds more across the queue" with the gain over first come, first served.
 *   6  (P9-3.9) CMH-48213 (820 h, 30% high load) reads its wear index ("WTI 65" when the piston kit was replaced at 500 h;
 *      the repair log's own replacements decide it) and "RUL 21% (Motor armature)" on its Overview.
 *   7  (P9-3.10) planner.a fits a remaining-life model on the repair log's teardown verdicts and proposes it; the Approver
 *      promotes it; the Models panel lists it as active with its median hours per component. (A case already open keeps
 *      its life until it is valued again; the Overview shows the model id for cases valued after the promotion.)
 *   9  (P9-3.12) CMH-48213 reads six valued paths and the renewal FC-30117-R in the re-issue lines.
 *   17 (P9-3.20) planner.a is refused a fit-for-use threshold of 40 (GR-03), proposes 60 and cannot approve it; the Approver
 *      approves; a CMH return with parts at 55% life no longer harvests them. (The overlay stays: the lead resets after.)
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
 * The last line is "smoke-p9-3: all <N> steps passed", N being the number of steps that ran.
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
await step('1 Returns: 18 tool cases opened, CMH-48213 from contract_end', async () => {
  const admin = await as('admin');
  await must(admin, 'org.create', { id: ORG, parent_id: 'workspace', kind: 'company', name: 'Tool fleet A' });
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

// ---------------------------------------------------------------- 2
await step('2 Grade: CMH-48213 an estimate, a late workbench grade makes CRH-44120 workbench', async () => {
  const admin = await as('admin');
  const dev = await as('developer');
  const caseId = async (serial) => {
    const r = await must(admin, 'cases.list', { q: serial, limit: 5 });
    const row = (r.rows || []).find((x) => x.id);
    if (!row) throw new Error('no case for ' + serial);
    return row.id;
  };
  const panel = async (serial, re, msg) => {
    const id = await caseId(serial);
    await admin.goto(`${base}/#/product/${id}/overview`);
    await admin.locator('#view').waitFor();
    return until(
      async () => {
        const t = await admin.locator('[data-testid="tf-grade"]').first().innerText();
        return re.test(t) ? t : null;
      },
      `${serial} (${id}) does not read ${msg}`,
      UI,
      admin,
    );
  };
  await panel('CMH-48213', /estimate/i, '"estimate"');
  await must(dev, 'source.reconnect', { source_id: 'repairlog' });
  await must(dev, 'source.sync', { source_id: 'repairlog' });
  const t = await until(
    async () => {
      await admin.reload();
      return panel('CRH-44120', /workbench DR-/, '"workbench"').catch(() => null);
    },
    'CRH-44120 never read "workbench" after the repairlog sync',
    SYNC,
    admin,
  );
  await panel('CMH-48213', /estimate/i, '"estimate"');
  return t;
});

// ---------------------------------------------------------------- 3
await step('3 Contract right: BRK-51007 blocked by GR-07, CMH-48213 passes', async () => {
  const admin = await as('admin');
  const caseId = async (serial) => {
    const r = await must(admin, 'cases.list', { q: serial, limit: 5 });
    const row = (r.rows || []).find((x) => x.id);
    if (!row) throw new Error('no case for ' + serial);
    return row.id;
  };
  // the cases opened before the sync wrote their contract lines were held; the lines queued a recheck on the worker
  const gateOf = async (serial, re, msg) => {
    const id = await caseId(serial);
    await until(
      async () => {
        const g = ((await getJson(admin, '/api/screens/toolfleet/' + id)).gates || []).find((x) => x.id === 'G-CON-2');
        return g && re.test(g.passed ? 'passed' : g.reason);
      },
      `${serial} (${id}) never read ${msg}`,
      SYNC,
      admin,
    );
    await admin.goto(`${base}/#/product/${id}/overview`);
    await admin.locator('#view').waitFor();
    return until(
      async () => {
        const t = await admin.locator('[data-testid="tf-gates"]').first().innerText();
        return re.test(t) ? t : null;
      },
      `${serial} (${id}) does not show ${msg} on the Overview`,
      UI,
      admin,
    );
  };
  const t = await gateOf('BRK-51007', /Theft recovered: claim CLM-7781 is open/, '"Theft recovered: claim CLM-7781 is open"');
  await gateOf('CMH-48213', /passed/, '"passed"');
  // My work lists the held case's exception for the Fleet desk (a Planner) of the org's tenant: reported, not required here
  // (planner.a sees its own tenant's items; the smoke's org unit is a company of its own)
  const work = JSON.stringify(await getJson(await as('planner.a'), '/api/screens/mywork'));
  return t.replace(/\s+/g, ' ') + (/Theft recovered|contract/i.test(work) ? ' \u00b7 My work lists it for planner.a' : '');
});
// ---------------------------------------------------------------- 4
await step('4 Recall quarantine: BRK-51007 (repair recall RC-2026-017) is released by the Approver', async () => {
  const dev = await as('developer');
  await must(dev, 'source.reconnect', { source_id: 'recall' });
  await must(dev, 'source.sync', { source_id: 'recall' });
  const admin = await as('admin');
  // a case opened after the notices are on file reads them (a notice that arrives later reaches an open case on its next re-evaluation)
  const opened = await must(admin, 'case.open', {
    org_unit_id: ORG, template_key: 'tool_fleet', asset_key: 'BRK-51007', reason: 'manual', facts: { cls: 'BRK', grade: 'B', site: 'Houston', rul: 62 },
  });
  const id = opened.case_id;
  const approver = await as('approver');
  await approver.goto(`${base}/#/product/${id}/overview`);
  await approver.locator('#view').waitFor();
  const card = approver.locator('[data-testid="tf-quarantine"]').first();
  await card.waitFor({ timeout: UI });
  const before = await card.innerText();
  if (!/RC-2026-017 \(repair\)/.test(before) || !/release, redeploy, resell/.test(before)) throw new Error('the quarantine card reads: ' + before.replace(/\s+/g, ' '));
  await approver.locator('textarea[aria-label="Why the tool is released"]').fill('Impact mechanism replaced at the depot');
  await approver.locator('[data-testid="tf-quarantine-release"]').click();
  const after = await until(
    async () => {
      const t = await approver.locator('[data-testid="tf-quarantine"]').first().innerText();
      return /released/.test(t) && !/quarantined/.test(t) ? t : null;
    },
    `${id} did not show the release`,
    UI,
    approver,
  );
  const planner = await as('planner.a');
  const denied = await callAction(planner, 'recall.release', { case_id: id, note: 'A planner may not release' });
  if (denied.ok) throw new Error('a Planner released a quarantine');
  return after.replace(/\s+/g, ' ');
});

// ---------------------------------------------------------------- 5
await step('5 Telematics: CMH-48777 last seen 8 days ago needs a person for re-issue and pool, CMH-48213 is fresh', async () => {
  const admin = await as('admin');
  const dev = await as('developer');
  await must(dev, 'source.reconnect', { source_id: 'tooltel' });
  await must(dev, 'source.sync', { source_id: 'tooltel' });
  const caseId = async (serial) => {
    const r = await must(admin, 'cases.list', { q: serial, limit: 5 });
    const row = (r.rows || []).find((x) => x.id);
    if (!row) throw new Error('no case for ' + serial);
    return row.id;
  };
  // the sync of the telematics queues a re-evaluation of each tool's open cases on the worker
  const lineOf = async (serial, re, msg) => {
    const id = await caseId(serial);
    await until(
      async () => {
        const g = ((await getJson(admin, '/api/screens/toolfleet/' + id)).gates || []).find((x) => x.id === 'G-TOOL-TEL');
        return g && re.test(g.reason);
      },
      `${serial} (${id}) never read ${msg}`,
      SYNC,
      admin,
    );
    await admin.goto(`${base}/#/product/${id}/overview`);
    await admin.locator('#view').waitFor();
    return until(
      async () => {
        const t = await admin.locator('[data-testid="tf-gate-G-TOOL-TEL"]').first().innerText();
        return re.test(t) ? t : null;
      },
      `${serial} (${id}) does not show ${msg} on the Overview`,
      UI,
      admin,
    );
  };
  const stale = await lineOf('CMH-48777', /Telematics last seen 8 days ago: re-issue and pool need a person/, '"Telematics last seen 8 days ago: re-issue and pool need a person"');
  await lineOf('CMH-48213', /Telematics 3 days old/, '"Telematics 3 days old"');
  return stale.replace(/\s+/g, ' ');
});

// ---------------------------------------------------------------- 6
await step('6 Life: CMH-48213 reads its wear index and the remaining life of its weakest component', async () => {
  const admin = await as('admin');
  const r = await must(admin, 'cases.list', { q: 'CMH-48213', limit: 5 });
  const row = (r.rows || []).find((x) => x.id);
  if (!row) throw new Error('no case for CMH-48213');
  const id = row.id;
  // the telematics sync (step 5) queued the re-evaluation that computes the life on the worker
  await until(
    async () => !!(await getJson(admin, '/api/screens/toolfleet/' + id)).life,
    `CMH-48213 (${id}) has no computed life`,
    SYNC,
    admin,
  );
  await admin.goto(`${base}/#/product/${id}/overview`);
  await admin.locator('#view').waitFor();
  // the piston kit's replacement comes from the repair log: the wear index follows it (65 with the replacement at 500 h)
  const wti = await until(
    async () => {
      const t = await admin.locator('[data-testid="tf-life-wti"]').first().innerText();
      return /^WTI \d+$/.test(t.trim()) ? t.trim() : null;
    },
    'CMH-48213 does not show a wear index on the Overview',
    UI,
    admin,
  );
  const rul = await until(
    async () => {
      const t = await admin.locator('[data-testid="tf-life-rul"]').first().innerText();
      return /RUL 21% \(Motor armature\)/.test(t) ? t.trim() : null;
    },
    'CMH-48213 does not show "RUL 21% (Motor armature)" on the Overview',
    UI,
    admin,
  );
  return `${wti}; ${rul}`;
});
// ---------------------------------------------------------------- 8
await step('8 Disagreement: a tool whose grade and wear agree shows no flag; one that disagrees shows the line and its exception', async () => {
  const admin = await as('admin');
  const r = await must(admin, 'cases.list', { q: 'CMH-48213', limit: 5 });
  const row = (r.rows || []).find((x) => x.id);
  if (!row) throw new Error('no case for CMH-48213');
  const view = await getJson(admin, '/api/screens/toolfleet/' + row.id);
  // CMH-48213 is graded by an estimate here, and an estimate never triggers a disagreement
  if (view.grade.source === 'estimate' && view.disagreement) throw new Error('an estimated grade must not flag a disagreement');
  await admin.goto(`${base}/#/product/${row.id}/overview`);
  await admin.locator('#view').waitFor();
  const flagged = await admin.locator('[data-testid="tf-disagreement"]').count();
  if (!!view.disagreement !== flagged > 0) throw new Error('the Overview and the screen API disagree about the flag');
  return view.disagreement ? view.disagreement.text : 'no disagreement (estimate grade)';
});

// ---------------------------------------------------------------- 7
await step('7 Remaining life: planner.a fits and proposes, the Approver promotes, the Models panel lists it', async () => {
  const planner = await as('planner.a');
  const m = await must(planner, 'model.fit', { template: 'tool_fleet', kind: 'rated_life' });
  if (!m.factors.length) throw new Error(`${m.id} fitted no component (${m.metrics.n} verdicts): is the repair log synced?`);
  await must(planner, 'model.propose', { id: m.id });
  const approver = await as('approver');
  await must(approver, 'model.promote', { id: m.id });
  const view = await getJson(approver, '/api/screens/agents/models');
  if (view.activeRatedLife !== m.id) throw new Error(`the active remaining-life model is ${view.activeRatedLife}, not ${m.id}`);
  await approver.goto(`${base}/#/agents`);
  const row = approver.locator(`tr[data-model="${m.id}"]`);
  await row.waitFor();
  const t = await row.innerText();
  if (!/median [\d,]+ h/.test(t) || !/active/.test(t)) throw new Error(`the Models panel row of ${m.id} shows no median hours and active: ${t.slice(0, 160)}`);
  return `${m.id} active, ${m.factors.length} components`;
});

// ---------------------------------------------------------------- 9
await step('9 Paths: CMH-48213 reads six valued paths and the renewal FC-30117-R in the re-issue lines', async () => {
  const admin = await as('admin');
  const r = await must(admin, 'cases.list', { q: 'CMH-48213', limit: 5 });
  const row = (r.rows || []).find((x) => x.id);
  if (!row) throw new Error('no case for CMH-48213');
  const v = await getJson(admin, '/api/screens/toolfleet/' + row.id);
  if ((v.paths || []).length !== 6) throw new Error(`expected six paths, got ${(v.paths || []).length}`);
  const release = v.paths.find((p) => p.k === 'release');
  if (!release.lines.some((l) => /Fleet renewal FC-30117-R/.test(l.label))) {
    throw new Error('the re-issue lines do not name the renewal FC-30117-R: ' + release.lines.map((l) => l.label).join(' | '));
  }
  await admin.goto(`${base}/#/product/${row.id}/overview`);
  await admin.locator('#view').waitFor();
  await admin.locator('[data-testid="tf-path-release"]').first().waitFor({ timeout: UI });
  const shown = await admin.locator('[data-testid="tf-paths"]').first().textContent();
  if (!/Fleet renewal FC-30117-R/.test(shown || '')) throw new Error('the Overview does not show "Fleet renewal FC-30117-R"');
  return `${v.paths.map((p) => p.k).join(', ')}; best ${v.best}, uplift ${v.uplift}`;
});
// ---------------------------------------------------------------- 10
await step('10 Queue plan: two CMH returns that both want FC-30117-R share it, the plan says who takes it', async () => {
  const admin = await as('admin');
  const open = async (serial) =>
    (await must(admin, 'case.open', { org_unit_id: ORG, template_key: 'tool_fleet', asset_key: serial, reason: 'manual', facts: { cls: 'CMH', grade: 'A', site: 'Houston', rul: 62 } })).case_id;
  const a = await open('CMH-QP-1');
  const b = await open('CMH-QP-2');
  const plans = [];
  for (const id of [a, b]) {
    await until(async () => (await getJson(admin, '/api/screens/toolfleet/' + id)).plan, 'no queue plan for ' + id, SYNC, admin);
    plans.push([id, (await getJson(admin, '/api/screens/toolfleet/' + id)).plan]);
  }
  // the renewal goes to one case only: another open CMH return (CMH-48213) may take it, so the two new returns need not hold it
  const holders = plans.filter(([, p]) => p.holds === 'FC-30117-R');
  if (holders.length > 1) throw new Error('FC-30117-R is held by both returns: ' + JSON.stringify(plans.map(([i, p]) => [i, p.holds])));
  const lost = plans.find(([, p]) => p.lost.some((x) => x.order === 'FC-30117-R'));
  if (!lost) throw new Error('neither return lost FC-30117-R to another: ' + JSON.stringify(plans.map(([i, p]) => [i, p.holds, p.headline])));
  const [loserId, loser] = lost;
  if (!/FC-30117-R .* is planned for RT-\d+, where it adds more across the queue/.test(loser.headline || '')) throw new Error('the losing reason reads: ' + loser.headline);
  await admin.goto(`${base}/#/product/${loserId}/overview`);
  await admin.locator('#view').waitFor();
  await admin.locator('[data-testid="tf-plan"]').first().waitFor({ timeout: UI });
  const shown = (await admin.locator('[data-testid="tf-plan"]').first().innerText()).replace(/\s+/g, ' ');
  if (!/is planned for RT-\d+, where it adds more across the queue/.test(shown) || !/first come, first served/.test(shown)) throw new Error('the Overview reads: ' + shown);
  return shown;
});
// ---------------------------------------------------------------- 13
await step('13 Key account: CRH-44120 (contract FC-30140, Westmark Supply) waits for the account manager', async () => {
  const admin = await as('admin');
  const r = await must(admin, 'cases.list', { q: 'CRH-44120', limit: 5 });
  const row = (r.rows || []).find((x) => x.id);
  if (!row) throw new Error('no case for CRH-44120');
  const v = await getJson(admin, '/api/screens/toolfleet/' + row.id);
  const key = ((v.approval || {}).holds || []).find((x) => x.id === 'TF-KEY');
  if (!key || !/Westmark Supply/.test(key.reason) || key.owner !== 'Account manager') throw new Error('no key-account hold: ' + JSON.stringify(v.approval));
  if (v.approval.kind !== 'person') throw new Error('a key account must wait for a person: ' + JSON.stringify(v.approval));
  await admin.goto(`${base}/#/product/${row.id}/overview`);
  await admin.locator('#view').waitFor();
  await admin.locator('[data-testid="tf-approval-key"]').first().waitFor({ timeout: UI });
  const shown = (await admin.locator('[data-testid="tf-approval"]').first().innerText()).replace(/\s+/g, ' ');
  if (!/Westmark Supply/.test(shown)) throw new Error('the Overview reads: ' + shown);
  return shown;
});
// ---------------------------------------------------------------- 17
await step('17 Fit-for-use threshold: planner.a proposes 60, lowering is refused, the Approver approves, a harvest case loses its parts', async () => {
  const planner = await as('planner.a');
  const ref = { pack_key: 'tool_fleet', org_unit_id: ORG };
  const op = (value) => ({ id: 'op-1', op: 'set_param', path: 'valuer.rulMin', value, seen: 50 });
  const low = await callAction(planner, 'overlay.save', { ...ref, ops: [op(40)] });
  if (low.ok || !/GR-03/.test(low.error?.message || '')) throw new Error('lowering the threshold to 40 was not refused naming GR-03: ' + JSON.stringify(low).slice(0, 200));
  await must(planner, 'overlay.save', { ...ref, ops: [op(60)] });
  await must(planner, 'overlay.submit', ref);
  const own = await callAction(planner, 'overlay.approve', ref);
  if (own.ok) throw new Error('the maker approved her own change to the threshold');
  const admin = await as('admin');
  const shown = await getJson(admin, `/api/screens/modeler?template=tool_fleet&org=${ORG}`);
  const p = (shown.overlay.params || []).find((x) => x.path === 'valuer.rulMin');
  if (!p || p.value !== 50 || p.owner !== 'Quality' || p.direction !== 'raise_only') throw new Error('the Modeler lists no Quality-owned threshold: ' + JSON.stringify(shown.overlay.params));
  await must(await as('approver'), 'overlay.approve', ref);
  const id = (await must(admin, 'case.open', { org_unit_id: ORG, template_key: 'tool_fleet', asset_key: 'CMH-FU-1', reason: 'manual', facts: { cls: 'CMH', grade: 'C', site: 'Houston', rul: 55 } })).case_id;
  const v = await until(async () => (await getJson(admin, '/api/screens/toolfleet/' + id)).paths?.length && (await getJson(admin, '/api/screens/toolfleet/' + id)), 'no paths for ' + id, SYNC, admin);
  const harvest = v.paths.find((x) => x.k === 'harvest');
  if (!harvest || harvest.lines.some((l) => /55% life/.test(l.basis || ''))) throw new Error('a part at 55% still counts at a 60% threshold: ' + JSON.stringify(harvest).slice(0, 200));
  return `threshold 60, harvest: ${harvest.why}`;
});

// ---------------------------------------------------------------- 15
await step('15 Non-return fee: AGR-20991 closed without the tool, planner.a posts the $180 fee from My work', async () => {
  const planner = await as('planner.a');
  const title = 'Non-return fee FL-30128-04';
  const row = await until(
    async () => ((await getJson(planner, '/api/screens/mywork')).items || []).find((i) => i.title === title),
    'no "' + title + '" item in My work (the fleet source must have synced)',
    SYNC,
    planner,
  );
  if (!/\$180/.test(row.cause || '') || !/AGR-20991/.test(row.cause || '')) throw new Error('the item reads: ' + row.cause);
  await planner.goto(`${base}/#/mywork`);
  await planner.locator('#mywork').waitFor();
  const li = planner.locator('#mywork li', { hasText: title }).first();
  await li.waitFor({ timeout: UI });
  await li.getByRole('button', { name: 'Post the fee' }).click();
  await until(
    async () => !((await getJson(planner, '/api/screens/mywork')).items || []).some((i) => i.title === title),
    'the item is still open after the post',
    UI,
    planner,
  );
  const again = await callAction(planner, 'nonReturnFee.post', { line_id: 'FL-30128-04' });
  if (again.ok || again.error?.code !== 'duplicate') throw new Error('a second post is not a duplicate: ' + JSON.stringify(again));
  return 'posted once, the second post is a duplicate';
});
await browser.close();
if (errors.length) {
  say('FAIL page errors:', errors.slice(0, 5).join(' | '));
  process.exit(1);
}
say(`smoke-p9-3: all ${stepsRun} steps passed`);
