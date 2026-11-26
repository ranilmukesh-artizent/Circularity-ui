/**
 * Plan 9, Phase 1 demo smoke (P9-1.14): the tool-fleet and device packs end to end in the browser, one line per step
 * (PASS, or FAIL with the step and the text that was missing, then exit 1 at once). Exit code 0 only when all seven steps
 * pass and no page threw an error.
 *
 *   1  planner.a imports tool_fleet 3.2.1 in Modeler > tool_fleet > Packs (Customer A), submits it; approver approves.
 *      The panel shows "3.2.0" (the pack file), "Published" and "13 of 13 parts".
 *   2  Customer layer of the device pack for Customer A: a shortcut from Return and receive to Execute is refused with
 *      "Blocked: this skips the compliance guardrail"; GR-D2's floor 0.60 saves; 0.50 shows "can only be tightened".
 *   3  case.open x2: tool-fleet cases for Customer A, class CMH, lease order L-SMOKE-1 in their facts. One case's Decide
 *      tab (stage 6, Why this outcome) shows "Holds lease renewal L-SMOKE-1", the other "goes to".
 *   4  case.open for asset key TF-SMOKE-NOPE: My work lists "Not in the system of record" with its action.
 *   5  A tool-fleet case's Why this outcome tab (outcome table) shows "CO₂e avoided", "avoided, not inventory" and "cfs-2026.2".
 *   6  Analytics > Packs > tool_fleet shows the tile "Redeploy rate" and its two question cards.
 *   7  planner.a submits the device overlay; the Approve button is not offered to them; approver approves and the
 *      panel shows "Published".
 *
 * Where the UI has no control (opening a case from data) the script calls the app's own action as the signed-in person.
 * The pack file is read from backend/di/services/modeler/packs/tool_fleet.json (override: PACK_FILE), so run it from a
 * checkout of the same commit as the stack. Needs the worker (the queue re-plan runs on it).
 *
 * Changes state, and resets nothing itself. The lead runs:
 *   bash scripts/dev/reset.sh && bash scripts/dev/wait-idle.sh
 *   node frontend/scripts/smoke-p9-1.mjs http://localhost:5173
 *   bash scripts/dev/reset.sh
 * (hold the api test lock meanwhile; a second run without a reset fails at step 1 or 3). Screenshots of a failing
 * step go to SMOKE_OUT (default: <OS temp>/smoke-p9-1). About 2 minutes; the last line is "smoke-p9-1: all 7 steps passed".
 *
 * Playwright APIs used (https://playwright.dev/docs/api/class-locator): locator.setInputFiles with a
 * {name, mimeType, buffer} payload, locator.selectOption, getByRole with name and exact.
 */
import { chromium } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const out = process.env.SMOKE_OUT || path.join(tmpdir(), 'smoke-p9-1');
const here = path.dirname(fileURLToPath(import.meta.url));
const packFile = process.env.PACK_FILE || path.join(here, '../../backend/di/services/modeler/packs/tool_fleet.json');
const ORG = 'Customer A';
const ORG_Q = encodeURIComponent(ORG);
const ORDER = 'L-SMOKE-1';
const UI = 30000;
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const errors = [];
const pages = {};
const say = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

/** One signed-in session per account; page errors are collected. The page stays in front (Chrome throttles background tabs). */
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

// The page keeps its template and organisation in its own state (the query is not read): pick them in its selects.
const modeler = async (p, template) => {
  await go(p, `modeler?template=${template}&org=${ORG_Q}`);
  const tpl = p.locator('#mdl-tpl');
  await tpl.waitFor();
  if ((await tpl.inputValue()) !== template) {
    await tpl.selectOption(template);
    await p.waitForFunction((t) => document.querySelector('#mdl-tpl')?.value === t, template);
    // the pick changes at once; the flow follows (writer 23): wait until the new template's screen is shown
    await p.locator('.mdl-picks[aria-busy="false"]').waitFor({ timeout: 60000 });
  }
};
const caseOpen = async (p, asset, facts) => {
  const r = await callAction(p, 'case.open', { org_unit_id: ORG, template_key: 'tool_fleet', asset_key: asset, reason: 'manual', facts });
  if (!r.ok) throw new Error(`case.open ${asset}: ${JSON.stringify(r.error || r).slice(0, 200)} (reset the stack first?)`);
  return r.output.case_id;
};

// ---------------------------------------------------------------- 1
await step('1 Packs: tool_fleet 3.2.0, Published, 13 of 13 parts', async () => {
  const doc = JSON.parse(readFileSync(packFile, 'utf-8'));
  const [maj, min, pat] = doc.version.split('.').map(Number);
  doc.version = `${maj}.${min}.${pat + 1}`; // an import must be newer than the pack file's version
  const pl = await as('planner.a');
  await modeler(pl, 'tool_fleet');
  const panel = pl.locator('[data-pack-key="tool_fleet"]');
  await panel.waitFor();
  await pl.locator('#mdl-pk-file').setInputFiles({ name: 'tool_fleet.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(doc)) });
  await expectText(pl, /Draft/, '[data-pack-key="tool_fleet"]');
  await panel.locator('[data-pack-version]').first().getByRole('button', { name: 'Submit for approval' }).click();
  await expectText(pl, /In review/, '[data-pack-key="tool_fleet"]');
  const ap = await as('approver');
  await modeler(ap, 'tool_fleet');
  await ap.locator('[data-pack-key="tool_fleet"] [data-pack-version]').first().getByRole('button', { name: 'Approve', exact: true }).click();
  await pl.reload();
  for (const w of ['3.2.0', 'Published', '13 of 13 parts']) await expectText(pl, w, '[data-pack-key="tool_fleet"]');
  return `file 3.2.0, imported ${doc.version} approved`;
});

// ---------------------------------------------------------------- 2
await step('2 Customer layer: skip refused, GR-D2 0.60 saves, 0.50 refused', async () => {
  const pl = await as('planner.a');
  await modeler(pl, 'device');
  const box = pl.locator('.mdl-overlay');
  await box.waitFor();
  const dv = box.locator('[data-overlay-diversion]');
  await dv.locator('#mdl-ov-stage').selectOption('receive');
  await dv.locator('#mdl-ov-kind').selectOption('shortcut');
  await dv.locator('#mdl-ov-to').selectOption('execute');
  await dv.getByRole('button', { name: 'Save', exact: true }).click();
  await expectText(pl, 'Blocked: this skips the compliance guardrail', '.mdl-overlay [data-overlay-refusal]');
  const tg = box.locator('[data-overlay-tighten]');
  await tg.locator('#mdl-ov-g').selectOption('GR-D2');
  await tg.locator('#mdl-ov-v').fill('0.6');
  await tg.getByRole('button', { name: 'Save', exact: true }).click();
  await expectText(pl, /Tighten GR-D2: floor 0\.55 → 0\.6/, '.mdl-overlay [data-overlay-ops]');
  await tg.locator('#mdl-ov-v').fill('0.5');
  await expectText(pl, 'can only be tightened', '.mdl-overlay [data-overlay-tighten]');
  await tg.locator('#mdl-ov-v').fill('');
});

// ---------------------------------------------------------------- 3
const ORDER_FACT = { kind: 'lease', id: ORDER, renew: true, who: 'Acme Rentals', site: 'Houston', need: 9, rate: 900, term: 24, what: `Fleet contract ${ORDER} renews`, when: 'renewal confirmed' };
const facts = (grade) => ({ cls: 'CMH', grade, ft: 'Repair center', site: 'Houston', rul: 62, dem: { lease: [ORDER_FACT] } });
const st = {};
await step('3 Queue plan: one case holds the lease order, the other loses it', async () => {
  const pl = await as('planner.a');
  st.a = await caseOpen(pl, 'TF-SMOKE-1', facts('B'));
  st.b = await caseOpen(pl, 'TF-SMOKE-2', facts('A'));
  const why = (id) => go(pl, `product/${id}/stage/6?tab=why`);
  const seen = await until(
    async () => {
      const t = {};
      for (const id of [st.a, st.b]) {
        await why(id);
        await pl.reload(); // the order is re-planned by the worker after the second case opens
        await pl.locator('#view').waitFor();
        // the case page opens on its overview (the case waits at stage 7); its "Queue plan:" line shows once the screen is read
        t[id] = await expectText(pl, /Queue plan:/, '#view', 15000).catch(() => '');
      }
      const hold = [st.a, st.b].find((id) => t[id].includes(`Holds lease renewal ${ORDER}`));
      const lose = [st.a, st.b].find((id) => new RegExp(`goes to RT-\\d+`).test(t[id]));
      return hold && lose && hold !== lose ? { hold, lose } : null;
    },
    `no case shows "Holds lease renewal ${ORDER}" and the other "goes to" (is the worker running?)`,
    90000,
    2000,
    pl,
  );
  st.holder = seen.hold;
  return `${seen.hold} holds ${ORDER}, ${seen.lose} loses it`;
});

// ---------------------------------------------------------------- 4
await step('4 My work: Not in the system of record, with its action', async () => {
  const pl = await as('planner.a');
  st.nope = await caseOpen(pl, 'TF-SMOKE-NOPE', facts('B'));
  await go(pl, 'mywork');
  const t = await expectText(pl, 'Not in the system of record', '#mywork', 60000);
  const row = t.split('\n').join(' ');
  if (!/Next: Check the serial in .*or correct the asset key/.test(row)) throw new Error('missing text "Next: Check the serial in …, or correct the asset key" (the recommended action)');
  return st.nope;
});

// ---------------------------------------------------------------- 5
await step('5 Case page: CO₂e avoided (not inventory), cfs-2026.2', async () => {
  const pl = await as('planner.a');
  await go(pl, `product/${st.holder}/stage/6?tab=why`); // the CO₂e column and its note are in the "Why this outcome" tab (outcome table)
  for (const w of ['CO₂e avoided', 'avoided, not inventory', 'cfs-2026.2']) await expectText(pl, w, '#view');
});

// ---------------------------------------------------------------- 6
await step('6 Analytics > Packs > tool_fleet: Redeploy rate, two questions', async () => {
  const ad = await as('admin');
  await go(ad, 'analytics');
  await ad.getByRole('tab', { name: 'Packs' }).click();
  await ad.getByLabel('Pack', { exact: true }).selectOption('tool_fleet');
  await expectText(ad, 'Redeploy rate', '[data-pack="tool_fleet"]');
  for (const q of ['Where do returns go?', 'Which tool classes recover the most per tool?']) await expectText(ad, q, '[data-pack="tool_fleet"]');
});

// ---------------------------------------------------------------- 7
await step('7 Overlay: approver approves, planner.a is not offered Approve', async () => {
  const pl = await as('planner.a');
  await modeler(pl, 'device');
  const box = pl.locator('.mdl-overlay');
  await box.getByRole('button', { name: 'Submit for approval' }).click();
  await expectText(pl, 'In review', '.mdl-overlay');
  if (await box.getByRole('button', { name: 'Approve', exact: true }).count()) throw new Error('planner.a is offered Approve on their own draft');
  const ap = await as('approver');
  await modeler(ap, 'device');
  await ap.locator('.mdl-overlay').getByRole('button', { name: 'Approve', exact: true }).click();
  await expectText(ap, 'Published', '.mdl-overlay');
});

if (errors.length) {
  say('FAIL page errors:', JSON.stringify(errors).slice(0, 600));
  await browser.close();
  process.exit(1);
}
// leave nothing on a page that writes
for (const p of Object.values(pages)) await p.goto('about:blank').catch(() => {});
await browser.close();
console.log('smoke-p9-1: all 7 steps passed');
