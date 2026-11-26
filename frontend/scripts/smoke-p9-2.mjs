/**
 * Plan 9, Phase 2 demo smoke (P9-2.16): the agent layer end to end in the browser, one line per step (PASS, or FAIL with
 * the step and the text that was missing, then exit 1 at once). Exit code 0 only when all eight steps pass and no page
 * outside the case pages threw an error.
 *
 *   1  admin, Agents: Language models shows the seeded model; the tool catalogue search "request missing evidence" lists
 *      `evidence_request` first.
 *   2  admin, Modeler > industrial > workspace > Standing policies: drafts a policy (max $500, confidence 0.75, owner admin)
 *      and submits it; admin's own Approve shows the maker-checker reason; approver approves, the policy is "In force".
 *   3  admin starts a Stage chain run (agent Recover chain) on RT-1048 from the Agents page; the run view shows the ten-stage
 *      journey, the stage records with confidence "x of 0.75", and the Disposition stage held with its reasons.
 *   4  planner.a accepts the held proposal from Home ("Held because: ..."); the run resumes and waits for an approval (the
 *      value is above the policy's limit); approver approves RT-1048 in the approval card.
 *   5  admin starts a Stage chain run on a low-value case the script finds with `cases.list` (awaiting approval, not
 *      submitted, net under $500; up to 5 are tried, as a case with an open conflict or exception is held instead); the case
 *      page reads "Approved by policy SP-..." and its History tab lists "Approve by standing policy".
 *   6  a device case (Customer A) is held for fraud review with a blacklist signal: its page shows "Held for fraud review"
 *      with the signal and its source; approver releases it with a reason.
 *   7  planner.a: Modeler > tool_fleet > Customer A > Set up (plan 10: Ask Circularity's Set up mode replaced the "Describe
 *      your business" dialog, so no `config.draft` proposal any more): the first sample prompt of the pack, the one question
 *      answered, "Drafted N changes" as plain sentences, "Open in Set up" shows the composition.
 *   8  GET /.well-known/oauth-protected-resource (page.request) returns JSON with `resource`.
 *
 * Where this script calls the app's own action as the signed-in person instead of using a control, the UI has none:
 *   - `case.open` (steps 5-7 cases opened from data), as smoke-p9-1 does;
 *   - `fraud.hold` (step 6): the intake stage calls it when the pack's fraud rules fire, but the shipped device pack has no
 *     fraud part and a blacklist record can only come from a source, so the script makes the same call the stage makes,
 *     with a blacklist signal, score 0.8, threshold 0.6, rule set v1;
 *   - `cases.list` (step 5), a read.
 * The sample prompt of step 7 is read from backend/di/services/modeler/packs/tool_fleet.json (override: PACK_FILE; the dialog
 * is opened without sample buttons), so run the script from a checkout of the same commit as the stack.
 * Step 8 asks the web origin first (the Vite proxy only forwards /api and /mcp), then the API at API_URL (default
 * http://localhost:$API_PORT or 8000).
 *
 * Needs: the worker (runs, wake-ups and the policy hook run on it) and a synced stack, with no standing policy and no
 * agent runs (a fresh reset). Changes state, and resets nothing itself. The lead runs:
 *   bash scripts/dev/reset.sh && bash scripts/dev/wait-idle.sh
 *   node frontend/scripts/smoke-p9-2.mjs http://localhost:5173
 *   bash scripts/dev/reset.sh
 * (hold the api test lock meanwhile; a second run without a reset fails at step 2 or 3). Screenshots of a failing step go to
 * SMOKE_OUT (default: <OS temp>/smoke-p9-2). About 3-5 minutes; the last line is "smoke-p9-2: all 8 steps passed".
 *
 * Playwright APIs used (https://playwright.dev/docs/api/class-locator): getByRole with name, locator.filter({ has }),
 * locator.selectOption, page.request.get.
 */
import { chromium } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describeInAssistant, openInSetup, openSetupTab } from './a10-setup.mjs';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const apiBase = process.env.API_URL || `http://localhost:${process.env.API_PORT || 8000}`;
const out = process.env.SMOKE_OUT || path.join(tmpdir(), 'smoke-p9-2');
const here = path.dirname(fileURLToPath(import.meta.url));
const packFile = process.env.PACK_FILE || path.join(here, '../../backend/di/services/modeler/packs/tool_fleet.json');
const HERO = 'RT-1048';
const UI = 30000;
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const errors = [];
const caseErrors = [];
const pages = {};
const say = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

/** One signed-in session per account; page errors are collected (case pages' apart: they are not what this smoke checks). */
async function as(acct) {
  if (pages[acct]) return pages[acct];
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } });
  const p = await ctx.newPage();
  p.setDefaultTimeout(UI);
  p.on('pageerror', (e) => {
    const line = `${acct} @ ${p.url().replace(/^.*#/, '#')}: ${e.message}`;
    (p.url().includes('#/product') ? caseErrors : errors).push(line);
  });
  await p.goto(base + '/#/signin');
  await p.fill('#si-id', acct);
  await p.fill('#si-pw', 'demo');
  await p.click('button[type=submit]');
  await p.waitForURL((u) => !/signin/.test(u.hash), { timeout: UI });
  pages[acct] = p;
  return p;
}

const text = (p, sel = 'body') => p.locator(sel).first().innerText();
const rxOf = (t) => (t instanceof RegExp ? t : new RegExp(t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));

/** Wait until the text is on the page (inside sel); throw naming the text when it is not. */
async function expectText(p, want, sel = 'body', ms = UI) {
  const rx = rxOf(want);
  const end = Date.now() + ms;
  let last = '';
  for (;;) {
    last = await text(p, sel).catch(() => '');
    if (rx.test(last)) return last;
    if (Date.now() > end) throw new Error(`missing text ${want} (page shows: ${last.replace(/\s+/g, ' ').slice(0, 240)})`);
    await p.waitForTimeout(250);
  }
}
const until = async (fn, msg, ms = UI, every = 500, p) => {
  const end = Date.now() + ms;
  for (;;) {
    const v = await fn().catch(() => null);
    if (v) return v;
    if (Date.now() > end) throw new Error(msg);
    await (p ? p.waitForTimeout(every) : new Promise((r) => setTimeout(r, every)));
  }
};
const go = async (p, route) => {
  await p.goto(`${base}/#/${route}`);
  await p.locator('#view').waitFor();
};
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

// The Modeler's template and organisation are in its URL (plan 10 T8); the selects are checked too.
const modeler = async (p, template, org) => {
  await go(p, `modeler?template=${template}&org=${encodeURIComponent(org)}`);
  for (const [sel, want] of [['#mdl-tpl', template], ['#mdl-org', org]]) {
    const el = p.locator(sel);
    await el.waitFor();
    if ((await el.inputValue()) !== want) {
      await el.selectOption(want);
      await p.waitForFunction(([s, v]) => document.querySelector(s)?.value === v, [sel, want]);
    }
  }
};

/** Start a playbook run from the Agents page (Admin): the Start run form of the Runs section. */
const startChain = async (p, caseId) => {
  await go(p, 'agents');
  await p.locator('#ag-run-agent').selectOption('recover-chain');
  await p.locator('#ag-run-playbook').selectOption('stage_chain');
  await p.locator('#ag-run-case').fill(caseId);
  await p.locator('#agRuns').getByRole('button', { name: 'Start run' }).click();
  await expectText(p, new RegExp(`started: stage chain on ${caseId}`), 'body');
};
/** The Runs row of a case (the newest first, as the page lists them), after a reload that reads the run's state again. */
const runRow = async (p, caseId) => {
  await p.reload();
  await p.locator('#agRuns').waitFor();
  // the chain's own run: each stage's model reading is listed too, as a stage_reasoner run on the same case
  const row = p.locator('#agRuns tbody tr', { hasText: caseId }).filter({ hasText: 'stage_chain' }).first();
  return { row, t: await row.innerText({ timeout: 3000 }) };
};
const openRun = async (p, row) => {
  await row.getByRole('button', { name: 'View' }).click();
  const dlg = p.locator('[role=dialog]');
  await dlg.locator('.runview').waitFor();
  return dlg;
};
const closeDrawer = (p) => p.getByRole('button', { name: 'Close panel' }).click();

const st = {};

// ---------------------------------------------------------------- 1
await step('1 Agents: seeded language model, tool search lists evidence_request first', async () => {
  const ad = await as('admin');
  await go(ad, 'agents');
  await expectText(ad, 'openai/gpt-oss-120b', '#agLlm');
  await ad.getByRole('searchbox', { name: 'Find a tool' }).fill('request missing evidence');
  const first = await until(
    async () => {
      const t = (await ad.locator('#agTools tbody tr').first().locator('td').first().innerText()).trim();
      return t === 'evidence_request' ? t : null;
    },
    'the tool search "request missing evidence" does not list evidence_request first',
    UI,
    300,
    ad,
  );
  return first;
});

// ---------------------------------------------------------------- 2
await step('2 Standing policy: maker-checker refusal for admin, approver puts it in force', async () => {
  const ad = await as('admin');
  await modeler(ad, 'industrial', 'workspace');
  const draft = ad.locator('[data-standing-draft]');
  await draft.waitFor();
  await draft.locator('#sp-name').fill('Smoke standing policy');
  await draft.locator('#sp-max').fill('500');
  await draft.locator('#sp-conf').fill('0.75');
  await draft.locator('#sp-owner').fill('admin');
  await draft.getByRole('button', { name: 'Save draft' }).click();
  const list = ad.locator('[data-standing-policies]');
  await list.locator('[data-standing-status="draft"]').waitFor();
  await list.locator('li').first().getByRole('button', { name: 'Submit for approval' }).click();
  await list.locator('[data-standing-status="review"]').waitFor();
  await list.locator('li').first().getByRole('button', { name: 'Approve', exact: true }).click();
  await expectText(ad, 'Maker-checker: you drafted this policy, so another person approves it.', '[data-standing-refusal]');
  const ap = await as('approver');
  await modeler(ap, 'industrial', 'workspace');
  await ap.locator('[data-standing-policies] li').first().getByRole('button', { name: 'Approve', exact: true }).click();
  await ap.locator('[data-standing-policies] [data-standing-status="active"]').waitFor();
  await expectText(ap, /In force · v1/, '[data-standing-policies]');
  st.policy = (await ap.locator('[data-standing-policies] li b').first().innerText()).trim();
  return st.policy;
});

// ---------------------------------------------------------------- 3
await step('3 Stage chain on RT-1048: journey, stage records, Disposition held with reasons', async () => {
  const ad = await as('admin');
  await startChain(ad, HERO);
  await until(
    async () => {
      const r = await runRow(ad, HERO);
      return /waiting/.test(r.t) && /Proposal \d+/.test(r.t) ? r.t : null;
    },
    `the run on ${HERO} never waited on a proposal (the Disposition stage was not held; is the worker running?)`,
    120000,
    3000,
    ad,
  );
  const { row } = await runRow(ad, HERO);
  st.runId = (await row.locator('td').first().innerText()).trim();
  const dlg = await openRun(ad, row);
  const stages = await dlg.locator('ol[aria-label="Journey stages"] > li').count();
  if (stages !== 10) throw new Error(`the journey shows ${stages} stages, not 10`);
  // held before submit: the hold is on Decide (6); Approve (7) is not reached until the submit is accepted (journey.py)
  await expectText(ad, /6\. Decide\s*Warning/, '[role=dialog]');
  await expectText(ad, /7\. Approve\s*(Queued|Not reached)/, '[role=dialog]');
  const disp = dlg.locator('.runview tr').filter({ has: ad.locator('b', { hasText: /^Disposition$/ }) });
  const row7 = await disp.innerText();
  if (!/held/.test(row7)) throw new Error(`the Disposition stage is not held (row: ${row7.replace(/\s+/g, ' ')})`);
  if (!/(is above the \$[\d,.]+ limit|is below \d\.\d+|open exception|sources disagree|Guardrail|Recommend only|may only propose)/.test(row7)) {
    throw new Error(`the Disposition stage shows no reason for its hold (row: ${row7.replace(/\s+/g, ' ')})`);
  }
  await expectText(ad, /\d\.\d\d of 0\.75/, '[role=dialog] .runview'); // a stage record's confidence against the threshold
  await closeDrawer(ad);
  return `${st.runId || 'run'} held at Disposition`;
});

// ---------------------------------------------------------------- 4
await step('4 planner.a accepts from Home, the run resumes, approver approves RT-1048', async () => {
  const pl = await as('planner.a');
  await go(pl, 'home');
  const card = pl.locator('#frProps li').filter({ hasText: HERO });
  await card.waitFor();
  await expectText(pl, 'Held because:', `#frProps li:has-text("${HERO}")`);
  // plan 10 (2.6): Accept names what it does, then one confirming step runs it as the person
  await card.getByRole('button', { name: 'Accept, runs as you', exact: true }).click();
  await card.getByRole('button', { name: 'Run as me', exact: true }).click();
  await expectText(pl, 'ran as you', 'body');
  const ad = await as('admin');
  await until(
    async () => (await runRow(ad, HERO)).t.includes(`Approval of ${HERO}`),
    `the run on ${HERO} does not wait for the approval of the case after the proposal was accepted`,
    90000,
    3000,
    ad,
  );
  // the open run view reads once: reload and reopen until the stage record shows the submit (it may land just after the row)
  await until(
    async () => {
      const { row } = await runRow(ad, HERO);
      const dlg = await openRun(ad, row);
      return /7\. Approve\s*Waiting for approval/.test(await dlg.innerText()) ? true : null;
    },
    `the journey of ${HERO} does not show 7. Approve as Waiting for approval`,
    60000,
    3000,
    ad,
  );
  await closeDrawer(ad);
  const ap = await as('approver');
  await go(ap, `product/${HERO}/stage/7`);
  const approve = ap.locator('button', { hasText: /^\s*Approve (?!and send)/ }).first();
  await approve.waitFor();
  await approve.click();
  await ap.getByLabel(/I reviewed evidence snapshot/).check();
  await ap.getByText('Approve and send instruction').click();
  await expectText(ap, /Approved by /, '#view');
});

// ---------------------------------------------------------------- 5
await step('5 Low-value case: the policy approves it ("Approved by policy SP-"), History lists it', async () => {
  const ad = await as('admin');
  const list = await callAction(ad, 'cases.list', { stage: 'awaiting_approval', submitted: false, limit: 200 });
  if (!list.ok) throw new Error('cases.list: ' + JSON.stringify(list.error || list).slice(0, 200));
  const cands = list.output.rows
    .filter((r) => r.id !== HERO && !r.blocked && !r.missing?.length && r.recommendation && r.recommendation.net > 0 && r.recommendation.net < 500)
    .sort((a, b) => a.recommendation.net - b.recommendation.net)
    .slice(0, 15); // a case held by its stage confidence or a model concern is not policy-approved: try more
  if (!cands.length) throw new Error('no case awaiting approval with a recommended net under $500 (is the stack reset?)');
  for (const c of cands) {
    await startChain(ad, c.id);
    const done = await until(
      async () => {
        const r = await callAction(ad, 'cases.list', { q: c.id, limit: 5 });
        return r.output?.rows?.find((x) => x.id === c.id)?.stage === 'approved';
      },
      `${c.id} not approved`,
      45000,
      2000,
      ad,
    ).catch(() => null);
    if (done) {
      st.low = c.id;
      break;
    }
  }
  if (!st.low) throw new Error(`none of ${cands.map((c) => c.id).join(', ')} was approved by the policy (held by an exception or a conflict?)`);
  await go(ad, `product/${st.low}/stage/7`);
  await expectText(ad, new RegExp(`Approved by policy ${st.policy} v\\d+`), '#view');
  await ad.getByRole('tab', { name: 'History' }).click();
  await expectText(ad, 'Approve by standing policy', '#view');
  return st.low;
});

// ---------------------------------------------------------------- 6
await step('6 Device case: held for fraud review with its signal, approver releases it', async () => {
  const pl = await as('planner.a');
  const lot = { brand: 'Apple', model: 'iPhone 14', band: '25-48m', grade: 'B', ref: 315, qty: 40, doh: 12 };
  const o = await callAction(pl, 'case.open', { org_unit_id: 'Customer A', template_key: 'device', asset_key: 'DEV-SMOKE-1', reason: 'manual', facts: lot });
  if (!o.ok) throw new Error(`case.open DEV-SMOKE-1: ${JSON.stringify(o.error || o).slice(0, 200)} (reset the stack first?)`);
  const id = o.output.case_id;
  const signal = { id: 'F-BL', fired: true, value: true, source: 'Blacklist register', at: new Date().toISOString() };
  const h = await callAction(pl, 'fraud.hold', { case_id: id, score: 0.8, signals: [signal], rule_version: 'v1', threshold: 0.6 });
  if (!h.ok) throw new Error(`fraud.hold ${id}: ${JSON.stringify(h.error || h).slice(0, 200)}`);
  await go(pl, `product/${id}/overview`);
  await expectText(pl, /Held for fraud review: score 0\.8 ≥ 0\.6 · rule set v1/, '[data-testid=fraud-hold]');
  await expectText(pl, 'F-BL · Blacklist register', '[data-testid=fraud-hold]');
  const ap = await as('approver');
  await go(ap, `product/${id}/overview`);
  await expectText(ap, 'Held for fraud review', '[data-testid=fraud-hold]');
  await ap.locator('#fraud-reason').fill('Checked the register: a name clash, not this asset.');
  await ap.locator('[data-testid=fraud-hold]').getByRole('button', { name: 'Release', exact: true }).click();
  await ap.locator('[data-testid=fraud-hold]').waitFor({ state: 'detached' });
  await expectText(ap, 'released from fraud review', 'body');
  return id;
});

// ---------------------------------------------------------------- 7
await step('7 Describe your business in Ask Circularity (Set up): a draft composition, the question answered, plain sentences', async () => {
  const prompt = JSON.parse(readFileSync(packFile, 'utf-8')).prompts?.[0];
  if (!prompt) throw new Error(`${packFile} has no sample prompt`);
  const pl = await as('planner.a');
  await modeler(pl, 'tool_fleet', 'Customer A');
  // plan 10: no dialog; the Set up page tab shows the Compose panel, whose launcher opens the assistant in Set up
  await openSetupTab(pl);
  const id = await describeInAssistant(pl, { timeout: 120000 });
  await expectText(pl, /Matched pack: tool_fleet|Nearest pack: tool_fleet/, '.st-turn');
  // the one question: its options are the buttons beside Skip; pick the first
  const skip = pl.locator('.st-turn').last().getByRole('button', { name: 'Skip', exact: true });
  await skip.waitFor();
  await skip.locator('xpath=..').locator('button').first().click();
  await expectText(pl, /Drafted (\d+ changes?|no changes)/, '.st-turn');
  const turn = pl.locator('.st-turn').last();
  if (/[{}]/.test(await turn.innerText())) throw new Error('the Set up turn shows JSON braces instead of plain sentences');
  const assumed = await turn.locator('.chip', { hasText: 'assumed' }).count();
  await openInSetup(pl, 60000);
  return `composition ${id}, ${assumed} assumed badge(s)`;
});

// ---------------------------------------------------------------- 8
await step('8 /.well-known/oauth-protected-resource returns JSON with resource', async () => {
  const ad = await as('admin');
  const url = '/.well-known/oauth-protected-resource';
  let seen = '';
  for (const origin of [base, apiBase]) {
    const r = await ad.request.get(origin + url).catch((e) => ({ ok: () => false, status: () => 0, text: async () => String(e) }));
    const body = await r.text();
    try {
      const j = JSON.parse(body);
      if (r.ok() && typeof j.resource === 'string' && j.resource) return `${origin}: resource ${j.resource}`;
    } catch {
      /* not JSON (the Vite page): try the API */
    }
    seen += ` ${origin} -> ${r.status()} ${body.slice(0, 60).replace(/\s+/g, ' ')};`;
  }
  throw new Error('no JSON with "resource":' + seen);
});

if (errors.length) {
  say('FAIL page errors:', JSON.stringify(errors).slice(0, 600));
  await browser.close();
  process.exit(1);
}
if (caseErrors.length) say('info: case page errors (not checked):', JSON.stringify(caseErrors).slice(0, 400));
// leave nothing on a page that writes
for (const p of Object.values(pages)) await p.goto('about:blank').catch(() => {});
await browser.close();
console.log('smoke-p9-2: all 8 steps passed');
