/**
 * Plan 9, Phase 8 demo smoke (P9-8.22, story X-10): Compose and the identity steps, one line per step (PASS, or FAIL with the
 * step and what was missing, then exit 1 at once). Chrome through Playwright, every step through the UI unless the line says
 * "(action: ...)": those are a mock system's admin route, a read, or the owner's click where My work has no button yet.
 *
 *   1  planner-a: Modeler (tool fleet, Customer A) > Compose > sample prompt 1 > Draft the changes: the reading log, the matched
 *      pack and exactly one question show; planner-a answers it and marks Describe done.
 *   2  Adapter mapping: "Legacy depot repair log" reads "Needs an adapter". developer (Integration > Connect > From the adapter
 *      registry > From an API spec) pastes the Depot Repair mock's OpenAPI document (source-sim /openapi.json, filtered to the
 *      mock's list paths and completed with its paging, record ids and Basic scheme), saves the draft, creates a test connection
 *      with `engineer` as system owner and asks the owner to approve; the approval is in engineer's My work, engineer approves
 *      (action: connection.ownerApprove), the drawer reads "Approved by engineer".
 *   3  developer reads a sample (Source drawer). Suggest mappings and the five choices (Accept, Choose another field, Accept with
 *      a conversion, Not needed, Ask the owner) once each, as admin in the same composition: a Planner lacks manageIntegrations,
 *      which mapping.decide needs. The question is in engineer's My work; engineer answers it (action: mapping.answerOwner);
 *      Save mapping; planner-a marks the mapping step done.
 *   4  Test run card: planner-a imports the tool-fleet history (Replay) and runs the test; reached and stopped by stage show.
 *   5  Agents: Condition on Recommend only, threshold 80 %; planner-a saves, marks done and submits.
 *   6  approver sends the Agents step back with a pinned note; planner-a sees it, sets Condition to Act within limits, resubmits;
 *      planner-a's Approve is off with the maker-checker text; approver approves.
 *   7  The flow is approved into shadow and replayed (planner-a forks, submits and replays; approver approves: the publish needs
 *      both), then approver publishes to Customer A at 20 %; the rollout reads "Canary ... Customer A at 20 %".
 *   8  admin: Access > Identity > Test a user for joiner.one@example.com finds nobody (action: access.testUser, and the user is
 *      not in the list); the joiner is added through the directory mock's _admin route (action: a mock system); admin presses
 *      "Sync from directory"; Test a user shows "Planner", "Customer B" and "Role from group circ-planners-customer-b".
 *   9  The joiner signs in with "Sign in with your organisation" (the mock's login_hint) and lands signed in, off #/signin.
 *  10  developer: Workflow Studio > Build with AI "every 15 minutes pull returns from rl and drop records without a serial": the
 *      draft opens, the canvas shows the graph laid out, a test run puts sample records in a node's Input and Output tabs.
 *  11  planner-a: Modeler > History > Export DMN and Export BPMN save non-empty files that parse as XML.
 *  12  planner-a opens the service-desk decision table node, edits a cell and "Test this decision" shows an output; "(skipped:
 *      no table)" counts as a pass when the flow has no table node.
 *
 * Needs the worker (replay, sync) and source-sim (the repair log mock and the directory mock). No vendor product is claimed
 * connected: the Depot Repair system is source-sim's synthetic mock.
 *
 * Changes state. The lead runs, holding the api test lock meanwhile (as smoke-mvp.mjs documents):
 *   bash scripts/dev/reset.sh && bash scripts/dev/wait-idle.sh
 *   node frontend/scripts/smoke-p9-8.mjs http://localhost:5173
 *   bash scripts/dev/reset.sh
 * Screenshots of a failing step go to SMOKE_SHOTS (default: <OS temp>/smoke-p9-8). Keep it under 10 minutes.
 * The last line is "smoke-p9-8: all 12 steps passed".
 */
import { execFileSync } from 'node:child_process';
import { chromium } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const SIM = process.env.SIM_URL || `http://localhost:${process.env.SIM_PORT || 8100}`;
const shots = process.env.SMOKE_SHOTS || path.join(tmpdir(), 'smoke-p9-8');
const HISTORY = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../fixtures/replay/tool_fleet_returns.csv');
const ORG = 'Customer A';
const MODELER = `${base}/#/modeler?template=tool_fleet&org=${encodeURIComponent(ORG)}`;
const JOINER = 'joiner.one@example.com';
const JOINER_GROUP = 'circ-planners-customer-b';
const UI = 180000; // the dev stack answers slowly while the worker syncs (compose.systems alone takes seconds)
const FIRST = 180000; // a first page load after sign-in
const LOG = /repair log/i;
mkdirSync(shots, { recursive: true });

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const errors = [];
const pages = {};
const say = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

async function as(acct) {
  if (pages[acct]) return pages[acct];
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 }, acceptDownloads: true });
  const p = await ctx.newPage();
  p.on('crash', () => say('CRASH', acct, p.url()));
  p.setDefaultTimeout(UI);
  p.on('pageerror', (e) => errors.push(`${acct} @ ${p.url().replace(/^.*#/, '#')}: ${e.message}`));
  await p.goto(base + '/#/signin', { waitUntil: 'domcontentloaded', timeout: 180000 });
  await p.fill('#si-id', acct);
  await p.fill('#si-pw', 'demo');
  await p.click('button[type=submit]');
  await p.waitForURL((u) => !/signin/.test(u.hash), { timeout: FIRST });
  await p.locator('#view').first().waitFor({ timeout: FIRST });
  await p.waitForTimeout(2500); // the shell's own redirect to Home lands a moment after sign-in and would undo a goto made now
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
const text = (p) => p.innerText('body'); // toasts are outside #view
const until = async (fn, msg, ms, p) => {
  const end = Date.now() + ms;
  for (;;) {
    const v = await fn().catch(() => null);
    if (v) return v;
    if (Date.now() > end) throw new Error(msg);
    await p.waitForTimeout(500);
  }
};
const waitText = (p, rx, msg, ms = UI) => until(async () => rx.test(await text(p)), msg || `"${rx}" never showed`, ms, p);
/** Open a route and drop the read cache with a reload (a hash change alone keeps what the page read earlier). */
async function open(p, url, ready = '#view') {
  const want = url.replace(/^.*#/, '#');
  for (let i = 0; i < 4; i++) {
    await p.goto(url, { waitUntil: 'domcontentloaded', timeout: 180000 });
    await p.waitForTimeout(800);
    if (p.url().includes(want)) break; // else the shell sent us Home: try again
  }
  await p.reload();
  await p.locator(ready).first().waitFor({ timeout: FIRST });
}

async function step(name, fn) {
  const t0 = Date.now();
  try {
    const detail = await fn();
    say('PASS', name, detail ? '· ' + detail : '', `(${Math.round((Date.now() - t0) / 1000)} s)`);
  } catch (e) {
    say('FAIL', name, '·', String(e?.message || e).split('\n').slice(0, 3).join(' | '), (e?.stack || '').match(/smoke-p9-8\.mjs:\d+/)?.[0] ?? '');
    for (const [a, p] of Object.entries(pages)) await p.screenshot({ path: path.join(shots, `fail-${a}.png`), fullPage: true }).catch(() => {});
    await Promise.race([browser.close().catch(() => {}), new Promise((r) => setTimeout(r, 5000))]);
    process.exit(1);
  }
}

// ---------------------------------------------------------------- Compose helpers
const panel = (p) => p.locator('section[aria-label="Compose"]');
const stepTab = (p, name) => panel(p).getByRole('tab', { name, exact: true });
async function openCompose(p, id) {
  await open(p, `${MODELER}${id ? `&compose=${id}` : ''}`, '.mdl-bar');
  if (!id) await p.getByRole('button', { name: 'Compose', exact: true }).click();
  await panel(p).waitFor();
}
let COMP = 0; // the composition id
async function composeTab(p, name) {
  await openCompose(p, COMP);
  await stepTab(p, name).click();
}
const systemRow = (p) => panel(p).locator('table[aria-label="Systems"] tbody tr', { hasText: LOG });
const markDone = async (p) => {
  const b = panel(p).getByRole('button', { name: 'Mark done', exact: true });
  await b.waitFor();
  await until(async () => (await b.isEnabled()) || null, 'Mark done stayed off', UI, p);
  await b.click();
  await panel(p).getByRole('button', { name: 'Done', exact: true }).waitFor();
};
const stateLine = (p) => panel(p).locator('.cmp-state').innerText();

/** A well-formed check without a DOM: tags nest and close, and there is one root. */
function wellFormed(xml) {
  const body = xml.replace(/<\?[\s\S]*?\?>/g, '').replace(/<!--[\s\S]*?-->/g, '').replace(/<!\[CDATA\[[\s\S]*?\]\]>/g, '');
  const stack = [];
  let roots = 0;
  for (const m of body.matchAll(/<(\/?)([A-Za-z_][\w:.-]*)((?:[^>"']|"[^"]*"|'[^']*')*?)(\/?)>/g)) {
    const [, close, name, , self] = m;
    if (close) {
      if (stack.pop() !== name) return false;
    } else if (!self) {
      if (!stack.length) roots += 1;
      stack.push(name);
    } else if (!stack.length) roots += 1;
  }
  return stack.length === 0 && roots === 1;
}

/** The mock's OpenAPI document: its list paths from source-sim's /openapi.json, with what FastAPI leaves open filled in. */
async function repairLogDocument() {
  const sim = await (await fetch(`${SIM}/openapi.json`)).json();
  const ids = { 'repair-orders': 'roId', teardowns: 'tdId' };
  const listed = Object.keys(sim.paths || {}).filter((k) => k.startsWith('/repairlog/api/') && !k.includes('{'));
  const paths = {};
  const schemas = {};
  for (const k of listed) {
    const leaf = k.split('/').pop();
    if (!ids[leaf]) continue;
    const name = leaf.replace(/-/g, '_');
    schemas[name] = {
      type: 'object',
      required: ['items'],
      properties: {
        items: { type: 'array', items: { type: 'object', required: [ids[leaf]], properties: { [ids[leaf]]: { type: 'string' }, serial: { type: 'string' } } } },
        next: { type: 'integer' },
        total: { type: 'integer' },
      },
    };
    paths[k] = {
      get: {
        operationId: `repairlog_${name}_list`,
        parameters: [
          { name: 'page', in: 'query', required: false, schema: { type: 'integer' } },
          { name: 'page_size', in: 'query', required: false, schema: { type: 'integer' } },
        ],
        responses: { 200: { description: 'A page', content: { 'application/json': { schema: { $ref: `#/components/schemas/${name}` } } } } },
      },
    };
  }
  if (Object.keys(paths).length < 2) throw new Error(`${SIM}/openapi.json lists no /repairlog/api/repair-orders and /teardowns (is source-sim up to date?)`);
  return JSON.stringify({
    openapi: '3.1.0',
    info: { title: 'Legacy depot repair log (synthetic)', version: '1.0.0' },
    paths,
    components: { schemas, securitySchemes: { basic: { type: 'http', scheme: 'basic' } } },
    security: [{ basic: [] }],
  });
}

// ---------------------------------------------------------------- 1
await step('1 Compose: sample prompt 1, the reading, the pack and one question', async () => {
  const p = await as('planner-a');
  await openCompose(p, null);
  const prompt = panel(p).locator('.cmp-prompts button').first();
  await prompt.waitFor();
  await prompt.click();
  if (!(await panel(p).getByLabel('Describe your business').inputValue()).trim()) throw new Error('the sample prompt did not fill the box');
  await panel(p).getByRole('button', { name: 'Draft the changes' }).click();
  await panel(p).getByRole('heading', { name: /What the agent read/ }).waitFor({ timeout: UI });
  const t = await panel(p).innerText();
  if (!/Matched pack|Nearest pack/.test(t) || !/tool_fleet/.test(t)) throw new Error('no matched pack line naming tool_fleet');
  const q = panel(p).locator('.cmp-question');
  if ((await q.count()) !== 1) throw new Error(`expected exactly one question, found ${await q.count()}`);
  COMP = Number((await stateLine(p)).match(/composition (\d+) is/)?.[1]);
  if (!COMP) throw new Error('no composition id in the state line');
  await q.locator('button').first().click(); // the first option (Skip is the last)
  await until(async () => (await panel(p).locator('.cmp-question').count()) === 0, 'the question stayed after the answer', UI, p);
  await markDone(p);
  return `composition ${COMP}`;
});

// ---------------------------------------------------------------- 2
let SID = '';
await step('2 Adapter mapping: Needs an adapter, spec import, test connection, owner approves', async () => {
  const p = await as('planner-a');
  await composeTab(p, 'Adapter mapping');
  await systemRow(p).waitFor();
  if (!/Needs an adapter/.test(await systemRow(p).innerText())) throw new Error("the legacy depot repair log does not read Needs an adapter: " + (await systemRow(p).innerText()).replace(/s+/g," "));

  const dev = await as('developer');
  const doc = await repairLogDocument();
  await open(dev, base + '/#/integration/overview', 'tr[data-int]');
  await dev.locator('tr[data-int]').getByRole('button', { name: 'Connect', exact: true }).first().click(); // a catalogue row's Connect opens the dialog
  const dlg = dev.locator('[role=dialog]').last();
  await dlg.getByRole('tab', { name: 'From the adapter registry' }).click();
  const kind = (name) => dlg.getByRole('tablist', { name: 'Connector kind' }).getByRole('tab', { name });
  await kind('From an API spec').click();
  await dlg.locator('#spDoc').fill(doc);
  await dlg.locator('#spName').fill('Depot repair log test');
  await dlg.locator('#spFamily').fill('Depot');
  await dlg.locator('#spType').fill('repairlog'); // the type the composition looks for (RegistryPicker hook, P9-8.22)
  await dlg.locator('#spBase').fill('http://source-sim:8100/repairlog/api');
  const before = await dlg.locator('label.frpk', { hasText: 'Depot' }).count(); // drafts of an earlier run stay: wait for one more
  await dlg.getByRole('button', { name: 'Save draft' }).click();
  await waitText(dev, /resource\(s\) found/, 'the import did not list the resources it found');
  const entry = dlg.locator('label.frpk', { hasText: 'Depot' }).last();
  await until(
    async () => {
      if ((await dlg.locator('label.frpk', { hasText: 'Depot' }).count()) > before) return true;
      await kind('Catalogue').click(); // refresh the entry list
      await kind('From an API spec').click();
      return null;
    },
    'the saved draft is not offered as a registry entry',
    UI,
    dev,
  );
  await entry.locator('input').check();
  await dlg.locator('#rgName').fill('Depot repair log test');
  await dlg.locator('#rgOwner').fill('engineer');
  const unit = await dlg.locator('#rgOrg option').evaluateAll((os, name) => os.find((o) => o.textContent.trim() === name)?.value ?? '', ORG);
  if (!unit) throw new Error(`no org unit named ${ORG} in the picker`);
  await dlg.locator('#rgOrg').selectOption(unit);
  await dlg.locator('#rgUrl').fill('http://source-sim:8100/repairlog/api');
  await dlg.locator('#rgSecret').fill('repairlog-demo'); // the mock's Basic password (demo user di-connector)
  await dlg.getByRole('button', { name: 'Create test connection' }).click();
  await waitText(dev, /created in the test environment, read only/, 'no "created in the test environment" confirmation');

  const admin = await as('admin');
  const sys = (await must(admin, 'compose.systems', { id: COMP })).systems.find((x) => LOG.test(x.name));
  SID = sys?.source_id;
  if (!SID) throw new Error('compose.systems still has no source for the repair log (the entry system type did not match?)');

  await open(dev, base + '/#/integration/overview', `tr[data-int="${SID}"]`);
  await dev.locator(`tr[data-int="${SID}"] button.frintn`).click();
  const drawer = dev.locator('aside.drawer.on');
  await drawer.getByRole('tab', { name: 'Overview' }).click();
  await drawer.getByRole('button', { name: 'Ask the owner to approve' }).click();
  await until(async () => /Waiting for engineer to approve/.test(await drawer.innerText()), 'the drawer does not read "Waiting for engineer to approve"', UI, dev);

  const eng = await as('engineer');
  await open(eng, base + '/#/mywork');
  await waitText(eng, /Approve production access \(read\) for Depot repair log test/, "the approval is not in engineer's My work");
  const st = await must(dev, 'connection.approvals', { source_id: SID });
  const pending = st.approvals.find((a) => a.status === 'pending');
  if (!pending) throw new Error('no pending approval on ' + SID);
  await must(eng, 'connection.ownerApprove', { id: pending.id }); // action: My work has Resolve and Assign only
  await dev.reload();
  await dev.locator(`tr[data-int="${SID}"] button.frintn`).click();
  await dev.locator('aside.drawer.on').getByRole('tab', { name: 'Overview' }).click();
  await until(async () => /Approved by engineer/.test(await dev.locator('aside.drawer.on').innerText()), 'the drawer does not read "Approved by engineer"', UI, dev);
  return SID;
});

// ---------------------------------------------------------------- 3
await step('3 Sample, suggestions with the five choices, the owner answers, mapping saved', async () => {
  const dev = await as('developer');
  await open(dev, base + '/#/integration/overview', `tr[data-int="${SID}"]`);
  await dev.locator(`tr[data-int="${SID}"] button.frintn`).click();
  const drawer = dev.locator('aside.drawer.on');
  await drawer.getByRole('tab', { name: 'Overview' }).click();
  await drawer.getByRole('button', { name: /Read a sample/ }).click();
  await until(async () => /: \d+/.test(await drawer.locator('[aria-label="Sample from the test connection"] [role=status]').innerText()), 'no record counts after "Read a sample"', 60000, dev);

  const admin = await as('admin');
  await composeTab(admin, 'Adapter mapping');
  await systemRow(admin).getByRole('button', { name: 'Review mappings' }).click();
  await panel(admin).getByRole('button', { name: 'Suggest mappings' }).click();
  const table = panel(admin).locator('table[aria-label="Suggested field mappings"]');
  await table.waitFor({ timeout: 60000 });
  const rows = table.locator('tbody tr');
  const n = await rows.count();
  if (n < 5) throw new Error(`only ${n} suggested rows: five choices need five fields`);
  const enabled = [];
  for (let i = 0; i < n; i++) enabled.push(await rows.nth(i).getByRole('button', { name: 'Accept', exact: true }).isEnabled());
  const acc = enabled.indexOf(true);
  if (acc < 0) throw new Error('no row has a proposal to accept');
  const rest = [...Array(n).keys()].filter((i) => i !== acc);
  const [rOther, rRule, rNot, rAsk] = rest;
  const saw = (i, rx, what) => until(async () => rx.test(await rows.nth(i).innerText()), `row ${i + 1} does not read ${what}`, UI, admin);

  await rows.nth(acc).getByRole('button', { name: 'Accept', exact: true }).click();
  await saw(acc, /Accepted /, '"Accepted ..."');
  await rows.nth(rOther).getByRole('button', { name: 'Choose another field' }).click();
  await rows.nth(rOther).getByLabel('Choose another field', { exact: true }).selectOption({ index: 1 });
  await rows.nth(rOther).getByRole('button', { name: 'Use this field' }).click();
  await saw(rOther, /Replaced with /, '"Replaced with ..."');
  await rows.nth(rRule).getByRole('button', { name: 'Accept with a conversion' }).click();
  await rows.nth(rRule).getByLabel('Field to convert into').selectOption({ index: 1 });
  await rows.nth(rRule).getByLabel('Conversion', { exact: true }).selectOption('upper');
  await rows.nth(rRule).getByRole('button', { name: 'Convert and show values' }).click();
  await saw(rRule, /with upper/, '"Accepted ... with upper"');
  await rows.nth(rNot).getByRole('button', { name: 'Not needed' }).click();
  await until(async () => (await rows.nth(rNot).getByRole('button', { name: 'Not needed' }).count()) === 0, `row ${rNot + 1} does not read "Not needed"`, UI, admin);
  await rows.nth(rAsk).getByRole('button', { name: 'Ask the owner' }).click();
  await rows.nth(rAsk).getByLabel('Question for the owner').fill('Which canonical field is this?');
  await rows.nth(rAsk).getByRole('button', { name: 'Send question' }).click();
  await saw(rAsk, /Asked engineer/, '"Asked engineer"');
  await waitText(admin, /Waiting for the system owner on 1 field/, 'no "Waiting for the system owner on 1 field"');

  const eng = await as('engineer');
  await open(eng, base + '/#/mywork');
  await waitText(eng, /Which field is .+ on Depot repair log test\?/, "the mapping question is not in engineer's My work");
  const sug = await must(admin, 'mapping.suggest', { source_id: SID });
  const asked = sug.rows.find((r) => r.decision?.decision === 'asked_owner');
  if (!asked) throw new Error('the server holds no open question for the field asked about');
  await must(eng, 'mapping.answerOwner', { decision_id: asked.decision.id, decision: 'accepted', target: sug.fields[0] }); // action: My work has no Answer button

  await composeTab(admin, 'Adapter mapping');
  await systemRow(admin).getByRole('button', { name: 'Review mappings' }).click();
  await panel(admin).getByRole('button', { name: 'Suggest mappings' }).click();
  await panel(admin).locator('table[aria-label="Suggested field mappings"]').waitFor({ timeout: 60000 });
  const save = panel(admin).getByRole('button', { name: 'Save mapping' });
  await until(async () => (await save.isEnabled()) || null, 'Save mapping stayed off after the owner answered', UI, admin);
  await save.click();
  await waitText(admin, /Saved as mapping version \d+/, 'no "Saved as mapping version"');

  const planner = await as('planner-a');
  await composeTab(planner, 'Adapter mapping');
  await markDone(planner);
  return 'five choices used once each (as admin)';
});

// ---------------------------------------------------------------- 4
await step('4 Test run: reached and stopped counts by stage', async () => {
  const p = await as('planner-a');
  await open(p, MODELER, '.mdl-bar');
  await p.locator('#mdl-rp-file').setInputFiles(HISTORY);
  await p.locator('[data-replay-batch]').first().waitFor({ timeout: UI });
  await composeTab(p, 'Adapter mapping');
  const card = panel(p).locator('[aria-label="Test run"]');
  await card.getByRole('button', { name: 'Run test' }).click();
  await until(async () => (await card.locator('[role=status]').count()) > 0, 'the test run answered nothing', 120000, p);
  const table = card.locator('table[aria-label="Where cases stopped"]');
  if (await table.count()) {
    const head = await table.locator('thead').innerText();
    if (!/Reached/.test(head) || !/Stopped/.test(head)) throw new Error('the table has no Reached and Stopped columns');
    return `${await table.locator('tbody tr').count()} stage(s) with stops`;
  }
  if (!/Every item reached a decision/.test(await card.innerText())) throw new Error('neither the stage table nor "Every item reached a decision" showed');
  return 'no stage stopped any case (no table)';
});

// ---------------------------------------------------------------- 5
await step('5 Agents: Condition on Recommend only at 80 %, submitted', async () => {
  const p = await as('planner-a');
  await composeTab(p, 'Agents');
  await panel(p).locator('select[aria-label="Autonomy of Condition"]').selectOption({ label: 'Recommend only' });
  await panel(p).getByLabel('Confidence threshold').evaluate((el) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, '80'); // a range input: set it as a person drags it
    el.dispatchEvent(new Event('input', { bubbles: true }));
  });
  if (!/80 %/.test(await panel(p).innerText())) throw new Error('the threshold does not read 80 %');
  await panel(p).getByRole('button', { name: 'Save settings' }).click();
  await waitText(p, /Saved the agent settings/, 'the settings were not saved');
  await markDone(p);
  await stepTab(p, 'Approve').click();
  await panel(p).getByRole('button', { name: 'Submit for approval' }).click();
  await waitText(p, /Submitted for approval/, 'the composition was not submitted');
  return 'submitted';
});

// ---------------------------------------------------------------- 6
const NOTE = 'Condition must act within limits, not only recommend.';
await step('6 Send back with a pinned note, resubmit, maker-checker, approve', async () => {
  const ap = await as('approver');
  await composeTab(ap, 'Approve');
  await panel(ap).getByLabel('Step to send back').selectOption('agents');
  await panel(ap).getByLabel('Node', { exact: true }).fill('condition');
  await panel(ap).getByLabel('Reason to send back').fill(NOTE);
  await panel(ap).getByRole('button', { name: 'Send back', exact: true }).click();
  await waitText(ap, /Sent back to its maker/, 'no "Sent back to its maker"');

  const p = await as('planner-a');
  await composeTab(p, 'Approve');
  await until(async () => (await panel(p).locator('[role=note]').filter({ hasText: NOTE }).count()) > 0, 'planner-a does not see the pinned note', UI, p);
  await stepTab(p, 'Agents').click();
  if (!/About: condition/.test(await panel(p).innerText())) throw new Error('the note is not pinned to the condition node');
  await panel(p).locator('select[aria-label="Autonomy of Condition"]').selectOption({ label: 'Act within limits' });
  await panel(p).getByRole('button', { name: 'Save settings' }).click();
  await waitText(p, /Saved the agent settings/, 'the changed settings were not saved');
  await markDone(p);
  await stepTab(p, 'Approve').click();
  await panel(p).getByRole('button', { name: 'Submit for approval' }).click();
  await waitText(p, /Submitted for approval/, 'planner-a could not resubmit');
  await until(async () => (await panel(p).getByRole('button', { name: 'Approve', exact: true }).count()) > 0, 'no Approve button for the maker to see off', UI, p);
  const mine = panel(p).getByRole('button', { name: 'Approve', exact: true });
  if (await mine.isEnabled()) throw new Error("planner-a's Approve button is enabled");
  if (!/Maker-checker: you composed this, so you cannot approve it\./.test(await panel(p).innerText())) throw new Error('the maker-checker text is missing');

  await composeTab(ap, 'Approve');
  await panel(ap).getByRole('button', { name: 'Approve', exact: true }).click();
  await waitText(ap, /Approved: the changes, mapping and settings apply together/, 'the approver could not approve');
  return 'approved by approver';
});

// ---------------------------------------------------------------- 7
await step('7 Shadow and replay, then publish to Customer A at 20 %', async () => {
  const p = await as('planner-a');
  await open(p, MODELER, '.mdl-bar');
  const fork = p.getByRole('button', { name: /Give Customer A its own flow/ });
  if (await fork.count()) {
    await fork.click();
    await waitText(p, /Tool fleet returns · Customer A|· Customer A/, 'Customer A did not get its own flow');
  }
  if (!(await p.getByRole('button', { name: 'Submit for approval' }).count())) {
    // a fork is published v1, not a draft: one rule makes the draft to submit (as smoke-modeler.mjs does)
    await p.getByRole('button', { name: 'Add rule' }).click();
    const paths = await p.getByLabel('Path', { exact: true }).locator('option').evaluateAll((os) => os.map((o) => o.value).filter(Boolean));
    await p.getByLabel('Path', { exact: true }).selectOption(paths[paths.length - 1]);
    await p.getByLabel('Action', { exact: true }).selectOption('exclude');
    await p.locator('.mdl-inspector fieldset input[type=checkbox], fieldset input[type=checkbox]').first().check();
    await p.waitForTimeout(3000); // the 2 s autosave
    await p.getByRole('button', { name: 'Submit for approval' }).first().waitFor({ timeout: UI });
  }
  await p.getByRole('button', { name: 'Submit for approval' }).first().click();
  await waitText(p, /In review · v\d+/, 'the flow was not submitted');
  const ap = await as('approver');
  await open(ap, MODELER, '.mdl-bar');
  await ap.getByRole('button', { name: 'Approve', exact: true }).first().click();
  await waitText(ap, /Shadow · v\d+/, 'the flow did not go to shadow');
  await open(p, MODELER, '.mdl-bar');
  await p.locator('[data-replay-run] button').first().click(); // "Replay the draft"
  await p.locator('[data-replay-report]').first().waitFor({ timeout: 180000 });

  await composeTab(ap, 'Publish');
  const btn = panel(ap).getByRole('button', { name: `Publish to ${ORG} at 20 %` });
  await until(async () => (await btn.isEnabled()) || null, 'Publish stayed off: ' + (await panel(ap).locator('.note').allInnerTexts()).slice(-3).join(' | '), UI, ap);
  await btn.click();
  const canary = /Canary (of|:) Customer A at 20 %/;
  const shown = await until(async () => canary.test(await panel(ap).innerText()), '', 10000, ap).then(() => true, () => false);
  if (!shown) {
    await composeTab(ap, 'Publish'); // the history is a cached read: a reload shows the rollout
    await until(async () => canary.test(await panel(ap).innerText()), 'the rollout does not read "Canary ... Customer A at 20 %"', UI, ap);
  }
  return 'Canary · Customer A · 20 %';
});

// ---------------------------------------------------------------- 8
await step('8 Identity: not found, the joiner added in the directory, synced, Planner · Customer B', async () => {
  const admin = await as('admin');
  await open(admin, base + '/#/access/identity', '#axRoles');
  const before = await must(admin, 'access.testUser', { email: JOINER }); // action: the picker lists only known users
  if (before.source !== 'none' || before.role) throw new Error(`${JOINER} is already known: ${JSON.stringify(before).slice(0, 160)}`);
  if ((await admin.locator(`#tu-user option[value="${JOINER}"]`).count()) > 0) throw new Error('the joiner is already in the list');
  const r = await fetch(`${SIM}/directory/_admin/users`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: JOINER, groups: [JOINER_GROUP] }),
  }); // action: the directory mock's admin route
  if (!r.ok) throw new Error(`the directory mock refused the joiner: ${r.status}`);
  // KNOWN GAP: nothing in the demo or the UI connects the directory as source `idp` (the pull sync needs it; without it
  // "Sync from directory" only stamps the time). Connect it here, as tests/scim_helpers.py does, straight in the database.
  execFileSync('docker', ['compose', 'exec', '-T', 'postgres', 'psql', '-U', 'circ', '-d', 'di', '-c',
    "INSERT INTO source_connection (source_id, base_url, protocol, auth_kind, environment) VALUES ('idp', 'http://source-sim:8100/directory', 'rest', 'none', 'test') ON CONFLICT DO NOTHING"], { stdio: 'pipe' });
  await admin.getByRole('button', { name: 'Sync from directory' }).click();
  await waitText(admin, /Directory synced/, 'no "Directory synced"');
  await open(admin, base + '/#/access/identity', '#axRoles');
  await admin.locator('#tu-user').selectOption(JOINER);
  const card = admin.locator('#testUserCard');
  await card.waitFor();
  const t = await card.innerText();
  for (const want of [/Planner/, /Customer B/, new RegExp(`Role from group ${JOINER_GROUP}`)]) if (!want.test(t)) throw new Error(`the test card lacks ${want}: ${t.slice(0, 200)}`);
  return 'Planner · Customer B';
});

// ---------------------------------------------------------------- 9
await step('9 The joiner signs in with the organisation', async () => {
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } });
  const p = await ctx.newPage();
  p.on('crash', () => say('CRASH', 'joiner', p.url()));
  p.setDefaultTimeout(UI);
  p.on('pageerror', (e) => errors.push(`joiner @ ${p.url().replace(/^.*#/, '#')}: ${e.message}`));
  pages.joiner = p;
  await p.goto(base + '/#/signin', { waitUntil: 'domcontentloaded', timeout: 180000 });
  await p.getByRole('button', { name: 'Sign in with your organisation' }).click();
  await p.waitForURL(/\/directory\/authorize/, { timeout: FIRST });
  await p.getByRole('button', { name: JOINER }).click(); // the mock's own link: authorize with login_hint
  await p.waitForURL((u) => u.origin === new URL(base).origin && !/signin/.test(u.hash) && u.hash !== '', { timeout: FIRST });
  await p.locator('#view').waitFor({ timeout: FIRST });
  if (!(await p.evaluate(() => sessionStorage.getItem('circ-api-token')))) throw new Error('no session token after the organisation sign-in');
  return p.url().replace(/^.*#/, '#');
});

// ---------------------------------------------------------------- 10
await step('10 Studio: Build with AI, the drafted graph, node samples', async () => {
  const dev = await as('developer');
  await open(dev, base + '/#/integration/studio');
  await dev.getByRole('button', { name: 'Build with AI' }).click();
  await dev.locator('#wbPrompt').fill('every 15 minutes pull returns from rl and drop records without a serial');
  await dev.getByRole('button', { name: 'Plan it' }).click();
  const draft = dev.getByRole('button', { name: 'Draft with the assistant' });
  await until(
    async () => {
      if (await draft.count()) return true;
      const defaults = dev.getByRole('button', { name: 'Use defaults for the rest' });
      if ((await defaults.count()) && (await defaults.isEnabled())) await defaults.click();
      return null;
    },
    'the planner never reached a plan',
    90000,
    dev,
  );
  await draft.click();
  await dev.locator('[data-testid="wbAuthored"]').waitFor({ timeout: 120000 });
  if (!/saved as a draft/.test(await dev.locator('[data-testid="wbAuthored"]').innerText())) throw new Error('the assistant saved no draft: ' + (await dev.locator('[data-testid="wbAuthored"]').innerText()).slice(0, 200));
  await dev.getByRole('button', { name: 'Open the draft' }).click();
  const nodes = dev.locator('.react-flow__node');
  await nodes.first().waitFor({ timeout: FIRST });
  const n = await nodes.count();
  if (n < 3) throw new Error(`the canvas shows ${n} nodes`);
  const xs = new Set();
  for (let i = 0; i < n; i++) xs.add(Math.round(((await nodes.nth(i).boundingBox())?.x ?? 0) / 10));
  if (xs.size < 2) throw new Error('the nodes are stacked on one column: not laid out');
  await dev.getByRole('button', { name: 'Test run' }).click();
  await waitText(dev, /Test run (finished|failed)|Test run \(dry\)/, 'the test run did not finish', 120000);
  let rowsSeen = 0;
  for (let i = 0; i < n && !rowsSeen; i++) {
    await nodes.nth(i).click();
    const samp = dev.locator('.nsamp');
    if (!(await samp.count())) continue;
    for (const tab of ['Input', 'Output']) {
      await samp.getByRole('tab', { name: tab }).click();
      rowsSeen += await samp.locator('table tbody tr').count();
    }
  }
  if (!rowsSeen) throw new Error("no node shows sample records in its Input or Output tab");
  return `${n} nodes, ${rowsSeen} sample rows`;
});

// ---------------------------------------------------------------- 11
await step('11 Modeler History: Export DMN and Export BPMN', async () => {
  const p = await as('planner-a');
  await open(p, MODELER, '.mdl-bar');
  const got = [];
  for (const name of ['Export DMN', 'Export BPMN']) {
    const [dl] = await Promise.all([p.waitForEvent('download', { timeout: UI }), p.getByRole('button', { name, exact: true }).click()]);
    const file = await dl.path();
    const xml = readFileSync(file, 'utf8');
    if (!xml.trim()) throw new Error(`${name} saved an empty file`);
    if (!wellFormed(xml)) throw new Error(`${name} (${dl.suggestedFilename()}) is not well-formed XML`);
    got.push(`${dl.suggestedFilename()} ${xml.length} B`);
  }
  return got.join(', ');
});

// ---------------------------------------------------------------- 12
await step('12 Service-desk decision table: edit a cell, Test this decision', async () => {
  const p = await as('planner-a');
  await open(p, MODELER, '.mdl-bar');
  const node = p.locator('.mdl-node.t-table').first();
  if (!(await node.count())) return '(skipped: no table)';
  await node.click();
  const ed = p.locator('.mdl-table-editor').first();
  await ed.waitFor({ timeout: UI });
  const cell = ed.locator('tbody input').first();
  const was = await cell.inputValue();
  if (await cell.isEditable()) {
    await cell.fill(was + ' ');
    await cell.fill(was); // an edit and back: the cell is changed through the editor
  }
  await ed.getByRole('button', { name: 'Test this decision' }).click();
  await until(async () => /matched row|\{.*\}/.test(await ed.innerText()), '"Test this decision" shows no output', UI, p);
  return 'output shown';
});

if (errors.length) {
  say('FAIL page errors:', JSON.stringify(errors));
  await browser.close();
  process.exit(1);
}
await browser.close();
console.log('\nsmoke-p9-8: all 12 steps passed');
