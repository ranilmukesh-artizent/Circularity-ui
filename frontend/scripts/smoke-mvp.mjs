/**
 * The MVP end to end in the browser (plan 8, MVP-12.4), against the running stack: a new company is set up, its returns
 * open cases, its Planner gets access and changes its decision flow, an agent prepares a decision, people approve it,
 * the instructions go out, Finance confirms the outcome and Admin fits a model on it. Ten steps, one line each (PASS or
 * FAIL with the reason); exit code 0 only when every step passed and no page threw an error.
 *
 *   1  Admin creates the org unit company-x under workspace (Access › Organisation).
 *   2  Developer connects PostgreSQL from the catalogue, bound to company-x, and publishes an ingest workflow on
 *      Reverse logistics (rl) with an Open case step (template industrial, org company-x, only early returns).
 *   3  A sync of rl opens company-x cases.
 *   4  planner-a asks for access to company-x, the Approver grants it; planner-a gives company-x its own flow, asks the
 *      assistant "Never recycle grade A", applies it, simulates and submits.
 *   5  The Approver approves (shadow) and publishes the flow.
 *   6  A company-x case goes back for re-evaluation (the Approver declines it) and planner-a re-evaluates it: the case
 *      page shows the rule.
 *   7  Admin sets the Handoff Coordinator to "Propose for a person" and starts the case autopilot on that case from the
 *      Agents page; the run stops at a held decision.submit; planner-a accepts the proposal.
 *   8  The Approver approves the decision (the approval card); the run finishes.
 *   9  Only source-sim's clock moves until the case waits for Finance; Finance confirms the outcome.
 *  10  Admin fits a model (model.fit) and the case's run board (Reconcile and learn) shows the candidate.
 *
 * Where the UI offers no control yet, the smoke uses the app's own call and says so in its line ("(no UI: …)"):
 * binding a source to an org unit (the Connect dialog has no org field: the dialog's own source.update gets
 * org_unit_id added), asking for tenant access (the account menu item is disabled in the demo), accepting a proposal
 * as a Planner (the Agents page is Admin and Developer only) and model.fit (no button). planner-a reloads after the
 * grant: the browser reads the account's tenants when it loads.
 *
 * Changes state: run scripts/dev/reset.sh and scripts/dev/wait-idle.sh before and reset.sh after; the worker must run
 * (syncs, workflow runs, agent runs, instructions). Hold the api test lock meanwhile (docs/agents/testing.md).
 *   node scripts/smoke-mvp.mjs http://localhost:5173
 */
import { chromium } from '@playwright/test';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const SIM = process.env.SIM_URL || `http://localhost:${process.env.SIM_PORT || 8100}`;
const shots = process.env.SMOKE_SHOTS || ''; // a folder: a screenshot of the page is saved there when a step fails
const ORG = 'company-x';
const CAT = 'postgres';
const CAT_SECRET = `${CAT}-demo-key`; // the sandbox key of source-sim's synthetic mock (di/connectors/catalog.py)
const SRC = 'rl'; // Reverse logistics (the Optoro mock): receipts carry the asset key (sku) and the return reason
const ONLY_IF = 'return_reason=early return';
const RULE = 'Never recycle grade A';
const AGENT = 'coordinator'; // Handoff Coordinator, a seeded agent
const WF_NAME = 'MVP smoke intake ' + Date.now().toString(36);
// SMOKE_TIME_SCALE=3 stretches every wait on a loaded machine (several stacks side by side); the default is 1
const K = Number(process.env.SMOKE_TIME_SCALE) || 1;
const T = { ui: 45000 * K, sync: 240000 * K, run: 180000 * K };

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const errors = [];
const pages = {};
const say = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);
const results = [];
const st = {}; // what the steps pass on

/** One signed-in browser session per account, with every toast it shows recorded (they disappear). */
async function as(acct) {
  if (pages[acct]) return pages[acct];
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
  await ctx.addInitScript(() => {
    window.__toasts = [];
    new MutationObserver((ms) => {
      for (const m of ms)
        for (const n of m.addedNodes) {
          if (n.nodeType !== 1) continue;
          for (const t of n.classList.contains('toast') ? [n] : n.querySelectorAll('.toast')) window.__toasts.push(t.textContent || '');
        }
    }).observe(document, { childList: true, subtree: true });
  });
  const p = await ctx.newPage();
  p.setDefaultTimeout(T.ui);
  p.on('pageerror', (e) => errors.push(`${acct} @ ${p.url().replace(/^.*#/, '#')}: ${e.message} ${(e.stack || '').split('\n').slice(1, 3).join(' | ').replace(/\s+/g, ' ')}`));
  await p.goto(base + '/#/signin');
  await p.fill('#si-id', acct);
  await p.fill('#si-pw', 'demo');
  await p.click('button[type=submit]');
  await p.waitForURL((u) => !/signin/.test(u.hash), { timeout: T.ui });
  pages[acct] = p;
  return p;
}

async function step(name, fn) {
  const t0 = Date.now();
  try {
    const detail = await fn();
    results.push({ name, ok: true });
    say('PASS', name, detail ? '· ' + detail : '', `(${Math.round((Date.now() - t0) / 1000)} s)`);
  } catch (e) {
    results.push({ name, ok: false });
    say('FAIL', name, '·', String(e?.message || e).split('\n')[0], `(${Math.round((Date.now() - t0) / 1000)} s)`);
    if (shots) for (const [a, p] of Object.entries(pages)) await p.screenshot({ path: `${shots}/fail-${results.length}-${a}.png`, fullPage: true }).catch(() => {});
  }
}
const check = (c, msg) => { if (!c) throw new Error(msg); };
const need = (...keys) => check(keys.every((k) => st[k]), 'an earlier step failed (no ' + keys.filter((k) => !st[k]).join(', ') + ')');

// ---- helpers on a page
const toastMark = (p) => p.evaluate(() => window.__toasts.length);
async function waitToast(p, re, mark, timeout = T.ui) {
  const end = Date.now() + timeout;
  for (;;) {
    const all = await p.evaluate(() => window.__toasts);
    const hit = all.slice(mark).find((t) => re.test(t));
    if (hit) return hit;
    if (Date.now() > end) throw new Error(`no toast ${re} (saw: ${JSON.stringify(all.slice(mark)).slice(0, 300)})`);
    await p.waitForTimeout(250);
  }
}
async function clickToast(p, loc, re, timeout) {
  const m = await toastMark(p);
  await loc.click();
  return waitToast(p, re, m, timeout);
}
async function until(p, fn, msg, timeout = T.ui, every = 1000) {
  const end = Date.now() + timeout;
  for (;;) {
    const v = await fn().catch(() => null);
    if (v) return v;
    if (Date.now() > end) throw new Error(msg);
    await p.waitForTimeout(every);
  }
}
const text = (p) => p.innerText('body');
async function waitText(p, rx, msg, timeout = T.ui) {
  return until(p, async () => (await text(p)).match(rx), msg || `no text ${rx}`, timeout, 250);
}
/** plan 10: the Modeler rail's Inspector, Checks, Impact and History are tabs that open on demand (closed below 1600 px) */
async function railTab(p, name) {
  const tab = p.locator('.mdl-strip').getByRole('tab', { name }).first();
  if ((await tab.getAttribute('aria-selected')) !== 'true') await tab.click();
}
async function go(p, route) {
  await p.goto(`${base}/#/${route}`);
  await p.locator('#view').waitFor();
}
const dlg = (p) => p.locator('[role=dialog]').last();
async function closeDialogs(p) {
  for (let i = 0; i < 4 && (await p.locator('[role=dialog]').count()); i++) {
    await p.keyboard.press('Escape');
    await p.waitForTimeout(300);
  }
}
/** The app's own action call, as the signed-in person (for the steps the UI has no control for yet). */
const callAction = (p, id, body) =>
  p.evaluate(async ([id, body]) => {
    const r = await fetch('/api/actions/' + id, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + sessionStorage.getItem('circ-api-token') },
      body: JSON.stringify(body),
    });
    return r.json();
  }, [id, body]);
const caseStage = async (p) => {
  const t = await p.innerText('#view');
  if (/Every stage is done/.test(t)) return '10 · Every stage is done';
  return t.match(/Case at Stage (\d+) of 10 · ([^\n]+)/)?.slice(1).join(' · ') ?? '(none)';
};

// ---------------------------------------------------------------- 1
await step('1 Admin creates company-x under workspace (Access › Organisation)', async () => {
  const p = await as('admin');
  await go(p, 'access/orgs');
  await p.locator('#axOrgs').waitFor();
  check(!(await p.locator('#axOrgs tr', { hasText: ORG }).count()), `${ORG} already exists: reset the stack first`);
  await p.locator('#org-parent').selectOption('workspace');
  await p.locator('#org-kind').selectOption('company');
  await p.locator('#org-name').fill(ORG);
  const t = await clickToast(p, p.getByRole('button', { name: 'Add unit' }), new RegExp(`${ORG} added under workspace`));
  await until(p, async () => (await p.locator('#axOrgs tr', { hasText: ORG }).count()) > 0, `${ORG} is not in the tree`);
  st.org = true;
  return `"${t}"; the tree lists ${ORG}`;
});

// ---------------------------------------------------------------- 2
const dev = await as('developer');
const drawer = () => dev.locator('aside.drawer.on');
async function openSource(id, tab) {
  await closeDialogs(dev);
  await go(dev, 'integration/overview');
  await dev.locator(`tr[data-int="${id}"] summary[aria-label^="Actions for"]`).waitFor();
  await dev.locator(`tr[data-int="${id}"] button.frintn`).click();
  await drawer().getByRole('tab').first().waitFor();
  if (tab) await drawer().getByRole('tab', { name: tab }).click();
}

await step('2a Developer connects PostgreSQL from the catalogue, bound to company-x', async () => {
  need('org');
  await go(dev, 'integration/overview');
  await dev.locator(`tr[data-int="${CAT}"], tr[data-int="cat:${CAT}"]`).first().waitFor();
  check(!(await dev.locator(`tr[data-int="${CAT}"]`).count()), 'PostgreSQL is already connected: reset the stack first');
  // (no UI: the Connect dialog has no org unit field) the dialog's own source.update call gets org_unit_id added
  await dev.route('**/api/actions/source.update', async (route) => {
    const body = JSON.parse(route.request().postData() || '{}');
    if (body.mode === 'catalog') body.org_unit_id = ORG;
    await route.continue({ postData: JSON.stringify(body) });
  });
  await dev.getByRole('button', { name: 'New integration' }).click();
  await dlg(dev).getByText('PostgreSQL', { exact: true }).click();
  await dlg(dev).getByRole('heading', { name: 'Connect PostgreSQL' }).waitFor();
  await dlg(dev).locator('input[name=frAuth][value=key]').check();
  await until(dev, async () => (await dlg(dev).locator('#frKey').inputValue()) === CAT_SECRET, 'the API key is not prefilled with the sandbox key');
  await dlg(dev).getByRole('button', { name: 'Continue' }).click();
  await dlg(dev).getByText('Grant only what Circularity needs').waitFor();
  await dlg(dev).getByRole('button', { name: 'Continue' }).click();
  await dlg(dev).getByRole('button', { name: 'Test connection' }).click();
  await until(dev, async () => /Connection test passed/.test(await dlg(dev).innerText()), 'Test connection did not pass', 60000 * K);
  await dlg(dev).getByRole('button', { name: 'Continue' }).click();
  await dlg(dev).getByRole('button', { name: 'Suggest mappings' }).click();
  await until(dev, async () => (await dlg(dev).locator('tbody tr').count()) > 0, 'Suggest mappings returned no rows', 60000 * K, 500);
  await dlg(dev).getByRole('button', { name: 'Accept all high' }).click();
  const acc = await dlg(dev).getByText(/\d+ of \d+ accepted/).innerText();
  await dlg(dev).getByRole('button', { name: 'Continue' }).click();
  await until(dev, async () => /Connected · first sync queued/.test(await dlg(dev).innerText()), 'the connection was not made', T.sync, 500);
  await dlg(dev).getByRole('button', { name: 'Done' }).click();
  await dev.unroute('**/api/actions/source.update');
  // the binding, as the Fabric's source list serves it
  const org = await dev.evaluate(async (id) => {
    const r = await fetch('/api/screens/integration/sources', { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('circ-api-token') } });
    return ((await r.json()).sources || []).find((s) => s.id === id)?.org_unit_id ?? null;
  }, CAT);
  check(org === ORG, `the source is bound to ${org}, not ${ORG}`);
  st.cat = true;
  return `${acc}; "Connected · first sync queued"; source ${CAT} org_unit_id ${org} (no UI for the org: added to the dialog's source.update)`;
});

const node = (label) => dev.locator('.wfn', { has: dev.locator('.lb', { hasText: new RegExp('^' + label.replace(/[.*+?^${}()|[\]\\&]/g, '\\$&') + '$') }) });
const insp = () => dev.locator('#wfInsp');
async function select(label) {
  await node(label).click();
  await insp().locator('h3', { hasText: label }).waitFor();
}
async function addBlock(label) {
  await dev.locator('#frPalQ').fill(label);
  const m = await toastMark(dev);
  await dev.locator(`#wfPal button[aria-label="Add ${label}"]`).first().focus();
  await dev.keyboard.press('Enter');
  await waitToast(dev, new RegExp(label + ' added'), m);
  await dev.locator('#frPalQ').fill('');
}
const sendsTo = () => insp().evaluate((el) => [...el.querySelectorAll('div')].filter((d) => d.firstElementChild?.textContent === 'Sends to').flatMap((d) => [...d.querySelectorAll('li b')].map((b) => b.textContent)));
async function link(from, to) {
  await select(from);
  const add = insp().getByRole('button', { name: '+ Add another connection' });
  if (await add.count()) await add.click();
  await insp().locator('#wfTo').selectOption({ label: to });
  await select(from);
  await until(dev, async () => (await sendsTo()).includes(to), `${from} does not send to ${to}`, 10000 * K, 300);
}
async function moreActions(item) {
  await dev.locator('summary', { hasText: 'More actions' }).click();
  await dev.getByRole('menuitem', { name: item, exact: true }).click();
}
/** Commit a text setting of the selected block (they commit on Enter). */
async function setText(key, v) {
  const f = insp().locator(`input[id$="-${key}"]`);
  await f.fill(v);
  await f.press('Enter');
}

await step('2b Developer publishes an ingest workflow on rl with Open case (industrial, company-x)', async () => {
  need('org');
  await closeDialogs(dev);
  await go(dev, 'integration/studio');
  await dev.getByRole('button', { name: /New workflow/ }).first().click();
  await dlg(dev).locator('#nwType').selectOption('ingest');
  await dlg(dev).locator('#nwSrc').selectOption(SRC);
  await dlg(dev).locator('#nwName').fill(WF_NAME);
  await clickToast(dev, dlg(dev).getByRole('button', { name: 'Create workflow' }), /created as a draft/);
  await dev.waitForURL(/#\/integration\/studio\/WF-/);
  st.wfId = dev.url().match(/WF-[\w-]+/)[0];
  await dev.locator('#wfPal').waitFor();
  // the connector: every record, receipts only (they carry the sku and the return reason)
  const conn = dev.locator('.wfn').first();
  await conn.click();
  const connName = (await insp().locator('h3').first().innerText()).trim();
  const mode = insp().locator('select[id$="-mode"]');
  if (await mode.count()) await mode.selectOption('full');
  const res = insp().locator('[role=group][aria-label="Resources"] input[type=checkbox]');
  for (let i = 0; i < (await res.count()); i++) {
    const name = (await res.nth(i).locator('xpath=..').innerText()).trim();
    if ((name === 'receipts') !== (await res.nth(i).isChecked())) await res.nth(i).click();
  }
  await addBlock('Open case');
  await select('Open case');
  await insp().locator('select[id$="-template"]').selectOption('industrial');
  await insp().locator('select[id$="-reason"]').selectOption('rma');
  await setText('asset_field', 'sku');
  await setText('org_unit_id', ORG);
  await setText('only_if', ONLY_IF);
  await link('Validation & enrichment', 'Open case');
  await select('Open case');
  check((await insp().locator('input[id$="-org_unit_id"]').inputValue()) === ORG, 'Open case lost its org unit');
  await dev.getByRole('button', { name: 'Auto layout' }).click();
  const v = await clickToast(dev, dev.getByRole('button', { name: 'Validate', exact: true }), /error|No errors/);
  check(/^No errors/.test(v), v);
  const m1 = await toastMark(dev);
  await moreActions('Save');
  await waitToast(dev, /saved as v[\d.]+/, m1);
  const m2 = await toastMark(dev);
  await moreActions('Publish');
  const pub = await waitToast(dev, /published as v[\d.]+|Cannot publish/, m2);
  check(/published/.test(pub), pub);
  st.wf = true;
  return `${st.wfId} on ${connName} (receipts) → Validation & enrichment → Open case (industrial, rma, sku, ${ORG}, only ${ONLY_IF}); "${v}"; "${pub}"`;
});

// ---------------------------------------------------------------- 3
await step('3 A sync of rl opens company-x cases', async () => {
  need('wf');
  await openSource(SRC, 'Sync & History');
  const t = await clickToast(dev, drawer().getByRole('button', { name: 'Sync now' }).first(), /synced: [\d,]+ records|sync failed/, T.sync);
  check(/synced:/.test(t), t);
  await closeDialogs(dev);
  // the cases it opened, as Admin's case list has them
  const admin = await as('admin');
  const rows = await until(admin, async () => {
    const r = await callAction(admin, 'cases.list', { owner: ORG, limit: 500 });
    const mine = (r.output?.rows || []).filter((c) => c.owner === ORG);
    return mine.length ? mine : null;
  }, `no ${ORG} case opened`, 60000 * K, 2000);
  // the case the journey follows: grade A (the rule's grade), waiting for approval, not submitted
  const pick = rows.find((c) => c.grade === 'A' && c.stage === 'awaiting_approval' && !c.submitted);
  check(pick, `no grade A ${ORG} case awaiting approval among ${rows.map((c) => `${c.id} ${c.grade} ${c.stage}`).join(', ')}`);
  st.case = pick.id;
  return `"${t}"; ${rows.length} ${ORG} cases opened (${rows.slice(0, 4).map((c) => c.id).join(', ')}…); following ${pick.id} (${pick.product}, grade A, ${pick.recommendation?.plan})`;
});

// ---------------------------------------------------------------- 4
await step('4a planner-a asks for access to company-x; the Approver grants it', async () => {
  need('org');
  const pl = await as('planner-a');
  // (no UI: the account menu's "Request tenant access" is disabled in the demo) the existing tenant access action
  const r = await callAction(pl, 'access.requestTenant', { tenant: ORG, reason: 'MVP smoke: I plan company-x returns.' });
  check(r.ok, 'access.requestTenant: ' + JSON.stringify(r.error));
  const id = r.output.id;
  const ap = await as('approver');
  await go(ap, 'command/approvals'); // the Approver's approvals inbox
  const row = ap.locator(`[data-req="${id}"]`);
  await row.waitFor();
  await row.getByRole('button', { name: 'Approve access' }).click();
  const t = await clickToast(ap, dlg(ap).getByRole('button', { name: 'Approve', exact: true }), new RegExp(`${id} approved`));
  st.access = true;
  return `${id} (no UI to ask: access.requestTenant called as planner-a); the Approver: "${t}"`;
});

await step('4b planner-a gives company-x its own flow, applies "Never recycle grade A", simulates and submits', async () => {
  need('access');
  const pl = await as('planner-a');
  // the grant reaches the server at once; this browser reads the account's tenants at load (no push yet): reload
  await pl.reload();
  await pl.locator('#view').waitFor();
  await go(pl, 'modeler?org=' + encodeURIComponent(ORG));
  await waitText(pl, /Industrial returns · /, 'the Modeler did not open');
  check((await pl.locator('#mdl-org').inputValue()) === ORG, `the Modeler is not on ${ORG}: ${await pl.locator('#mdl-org').inputValue()}`);
  const fork = pl.getByRole('button', { name: `Give ${ORG} its own flow` });
  if (await fork.count()) {
    await fork.click();
    await waitText(pl, new RegExp(`Industrial returns · ${ORG}`), `${ORG} did not get its own flow`);
  }
  const ask = pl.locator('.mdl-agent textarea'); // plan 10: the pinned agent column replaced the Assistant panel
  await ask.fill(RULE);
  await ask.press('Enter');
  await waitText(pl, /Proposed: /, 'the assistant proposed nothing', 30000 * K);
  const prop = (await pl.locator('.mdl-agent .as-card-title').first().innerText()).replace(/^Proposed:\s*/, '').trim();
  check(/recycle|material/i.test(prop) && /\bA\b/.test(prop), `the proposal does not read as the rule: "${prop}"`);
  await pl.getByRole('button', { name: 'Apply to draft' }).click();
  await waitText(pl, /Saved .* to draft/, 'the proposal was not applied');
  st.rule = prop.match(/^[A-Z]+-\d+/)?.[0] ?? null;
  await railTab(pl, 'Impact');
  await pl.getByRole('button', { name: 'Simulate on open queue' }).click();
  const sim = (await waitText(pl, /\d+ of \d+ open decisions change[^\n]*/, 'no simulation result'))[0];
  await pl.getByRole('button', { name: 'Submit for approval' }).click();
  const ver = (await waitText(pl, /In review · v(\d+)/, 'the flow is not in review'))[1];
  st.flowVer = ver;
  return `proposal "${prop}"; ${sim}; In review · v${ver}`;
});

// ---------------------------------------------------------------- 5
await step('5 The Approver approves (shadow) and publishes the flow', async () => {
  need('flowVer');
  const ap = await as('approver');
  await go(ap, 'modeler?org=' + encodeURIComponent(ORG));
  await waitText(ap, new RegExp(`In review · v${st.flowVer}`), 'the Approver does not see the flow in review');
  await ap.getByRole('button', { name: 'Approve', exact: true }).click();
  await waitText(ap, new RegExp(`Shadow · v${st.flowVer}`), 'not in shadow after Approve');
  await ap.getByRole('button', { name: 'Publish' }).click();
  await waitText(ap, new RegExp(`Published · v${st.flowVer}`), 'not published');
  st.published = true;
  return `Shadow · v${st.flowVer} → Published · v${st.flowVer}`;
});

// ---------------------------------------------------------------- 6
await step('6 planner-a re-evaluates a company-x case: the rule shows', async () => {
  need('published', 'case');
  const id = st.case;
  // back for re-evaluation: the Approver declines it in stage 7
  const ap = await as('approver');
  await go(ap, `product/${id}/stage/7`);
  await ap.getByRole('button', { name: 'Decline', exact: true }).first().click();
  await dlg(ap).locator('#dc-why').fill('Re-check with the new company-x business rule.');
  const d = await clickToast(ap, dlg(ap).getByRole('button', { name: 'Decline', exact: true }), /declined and sent back/);
  const pl = await as('planner-a');
  await go(pl, `product/${id}/stage/7`);
  const re = pl.getByRole('button', { name: new RegExp(`Re-evaluate ${id}|Run re-evaluation`) }).first();
  await re.waitFor();
  const t = await clickToast(pl, re, /Re-evaluat/); // "Re-evaluated. …" or the agent's step "Re-evaluate case · RT-x."
  const want = /Excluded by business rule [A-Z]+-\d+/;
  let found = null;
  await go(pl, `product/asset/${id}`);
  found = await waitText(pl, want, '', 6000 * K).catch(() => null);
  for (const n of found ? [] : [6, 7]) {
    await go(pl, `product/${id}/stage/${n}`);
    for (const tab of ['Compare outcomes', 'Why this outcome', 'Checks']) {
      const tb = pl.getByRole('tab', { name: tab });
      if (await tb.count()) await tb.first().click();
      found = await waitText(pl, want, '', 1500 * K).catch(() => null);
      if (found) break;
    }
    if (found) break;
  }
  check(found, `the case page does not show "Excluded by business rule" after the re-evaluation`);
  check(!st.rule || found[0].endsWith(st.rule), `the case shows ${found[0]}, not the new rule ${st.rule}`);
  st.reevaluated = true;
  return `${id}: "${d}"; "${t}"; the case page: "${found[0]}"`;
});

// ---------------------------------------------------------------- 7
await step('7 Admin starts the case autopilot from the Agents page; it stops at a held submit; planner-a accepts', async () => {
  need('reevaluated');
  const id = st.case;
  const admin = await as('admin');
  await go(admin, 'agents');
  const au = admin.locator(`#ag-au-${AGENT}`);
  if ((await au.inputValue()) !== 'propose') {
    const m = await toastMark(admin);
    await au.selectOption('propose');
    await waitToast(admin, /autonomy changed/, m);
  }
  await admin.locator('#ag-run-agent').selectOption(AGENT);
  await admin.locator('#ag-run-playbook').selectOption('case_autopilot'); // plan 9 added the playbook choice
  await admin.locator('#ag-run-case').fill(id);
  const t = await clickToast(admin, admin.getByRole('button', { name: 'Start run' }), /Run AR-\w+ started/);
  const run = t.match(/AR-\w+/)[0];
  // the worker runs it to the hold: the run waits for a proposal, the proposal is the decision.submit
  const row = await until(admin, async () => {
    await admin.reload();
    const r = admin.locator('#agRuns tr', { hasText: run });
    await r.waitFor({ timeout: 15000 * K });
    const x = await r.innerText();
    return /waiting/.test(x) && /Proposal \d+/.test(x) ? x : null;
  }, `run ${run} did not stop at a held proposal`, 90000 * K, 3000);
  const pid = +row.match(/Proposal (\d+)/)[1];
  const prow = await admin.locator(`#agp-${pid}`).innerText();
  check(/Submit for review/.test(prow) && prow.includes(id), `proposal ${pid} is not the submit of ${id}: ${prow.replace(/\s+/g, ' ')}`);
  // (no UI for a Planner: the Agents page is Admin and Developer only) planner-a accepts with the page's own action
  const pl = await as('planner-a');
  const acc = await callAction(pl, 'proposal.accept', { id: pid });
  check(acc.ok, 'proposal.accept: ' + JSON.stringify(acc.error));
  await go(pl, `product/${id}/stage/7`);
  await waitText(pl, /Submitted|submitted/, `${id} does not show as submitted`);
  const after = await until(admin, async () => {
    await admin.reload();
    const x = await admin.locator('#agRuns tr', { hasText: run }).innerText();
    return /Approval of/.test(x) ? x : null;
  }, `run ${run} does not wait for the approval after the accept`, 60000 * K, 3000);
  st.run = run;
  return `"${t}"; ${run} waiting · Proposal ${pid} (decision.submit ${id}); planner-a accepted it (no UI: proposal.accept); the run now waits: ${after.replace(/\s+/g, ' ').trim()}`;
});

// ---------------------------------------------------------------- 8
await step('8 The Approver approves the decision; the run finishes', async () => {
  need('run');
  const id = st.case;
  const ap = await as('approver');
  await go(ap, `product/${id}/stage/7`);
  await ap.locator('button', { hasText: /^\s*Approve (?!and send)/ }).first().click();
  await ap.getByLabel(/I reviewed evidence snapshot/).check();
  const t = await clickToast(ap, ap.getByText('Approve and send instruction'), /APR-\S+ created/); // "APR-… created. Instruction handed to WMS."
  const admin = await as('admin');
  await go(admin, 'agents');
  const row = await until(admin, async () => {
    await admin.reload();
    const x = await admin.locator('#agRuns tr', { hasText: st.run }).innerText();
    return /\bdone\b/.test(x) ? x : null;
  }, `run ${st.run} did not finish after the approval`, 90000 * K, 3000);
  st.approved = true;
  return `"${t}"; ${row.replace(/\s+/g, ' ').trim()}`;
});

// ---------------------------------------------------------------- 9
await step('9 The instructions are acknowledged (sim clock); Finance confirms the outcome', async () => {
  need('approved');
  const id = st.case;
  const w = await as('approver');
  await go(w, `product/${id}/stage/8`);
  let s = '';
  // keep the clock moving until the case waits for Finance: stage 9 first reads "Waiting on <ERP>" while the outcome
  // is still being reported, and only "Waiting on Finance" (the case closed) offers Confirm (as smoke-rt1048 waits)
  for (let i = 0; i < 40; i++) {
    s = await caseStage(w);
    if (/^9 .*Finance|^10 /.test(s)) break;
    const r = await fetch(SIM + '/_sim/clock/advance', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ hours: 3 }) });
    check(r.ok, 'clock advance failed: ' + r.status);
    await w.waitForTimeout(3000);
  }
  check(/^9 .*Finance/.test(s), `${id} did not reach stage 9 waiting on Finance: ${s}`);
  const fin = await as('finance');
  await go(fin, `product/${id}/stage/9`);
  const confirm = fin.locator('button', { hasText: 'Confirm the outcome' });
  await confirm.first().waitFor();
  const t = await clickToast(fin, confirm.first(), /onfirm|outcome/i);
  await go(fin, `product/${id}/stage/10`);
  const done = await until(fin, async () => /^10 · Every stage is done/.test(await caseStage(fin)), `${id} did not close after the confirmation`, 20000 * K, 500);
  st.confirmed = done;
  return `watcher saw "${s}"; Finance: "${t}"; ${id} at stage 10 · Every stage is done`;
});

// ---------------------------------------------------------------- 10
await step('10 Admin fits a model and sees the candidate', async () => {
  need('confirmed');
  const admin = await as('admin');
  // (no UI: no button runs model.fit yet) the action, as Admin
  const r = await callAction(admin, 'model.fit', { template: 'industrial' });
  check(r.ok, 'model.fit: ' + JSON.stringify(r.error));
  const mid = r.output.id;
  // the case's run board (Process Orchestration), stage 10: the Reconciler's learning records name the candidate
  await go(admin, `orchestration/run?case=${st.case}`);
  await admin.getByText('Reconcile and learn', { exact: true }).first().click();
  const seen = await waitText(admin, new RegExp(`candidate model ${mid} awaiting promotion[^\\n]*`), `the run board of ${st.case} does not show the candidate ${mid}`, 15000 * K);
  return `model.fit → ${mid} (${r.output.status}, ${r.output.metrics.n} outcome rows); the run board, Reconcile and learn: "${seen[0]}"`;
});

const failed = results.filter((r) => !r.ok);
say('page errors:', errors.length ? errors.slice(0, 8) : 'none');
say(failed.length || errors.length ? `FAILED: ${failed.length} of ${results.length} steps, ${errors.length} page errors` : `smoke-mvp: all ${results.length} steps passed`);
await browser.close();
process.exit(failed.length || errors.length ? 1 : 0);
