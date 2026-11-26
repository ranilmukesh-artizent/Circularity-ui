/**
 * Plan 9, Phase 7 demo smoke (P9-7.8): replay, publish in steps, the back-test report and the FR market canary of the service-desk
 * tables, one line per step (PASS, or FAIL with the step and the text that was missing, then exit 1 at once). Everything goes
 * through the UI as the signed-in person; the only file the script writes is the second CSV (one route set to `scrap`), into
 * SMOKE_OUT.
 *
 *   1  planner.a opens Customer A's tool-fleet flow in the Modeler (giving the org its own flow when it has none) and asks Ask
 *      Circularity, the pinned column, for one rule ("Never recycle construction lasers"); Apply to draft puts it in the draft.
 *      (Plan 9's journey opens Replay first; the stepper that opens the Replay drawer only shows once the flow has a draft, so
 *      the draft comes first here. The old Describe dialog and Ask panel are gone since plan 10: the column is the assistant.)
 *   2  Replay, Import history (CSV) with fixtures/replay/tool_fleet_returns.csv: "120 rows · 0 held".
 *   3  The same file with one row's route set to `scrap`: "1 held" with "Route 'scrap' is not a route of tool_fleet".
 *   4  "Replay the draft" on the first batch: the four numbers show (route mix, straight-through %, approvals and exceptions a day,
 *      uplift with its 80 % band).
 *   5  planner.a submits the draft; approver approves it (Shadow · v2).
 *   6  planner.a's Start canary is off and says why (Maker-checker: you made these changes ...); the approver starts a canary at
 *      FR, 20 %: the panel reads "Canary: FR at 20 % of volume".
 *   7  exec opens Analytics, Back-test: the latest run's waterfall and method note show, and the print view as a PDF is over 10 kB.
 *   8  approver starts the FR tables canary at 20 % under "Decision tables · FR" (the flow's replay is done), and the report
 *      compares the arms "Canary" and "Standard quote".
 *
 * Needs the worker (the replay runs on it) and a freshly reset database. Changes state, and resets nothing itself. The lead runs
 * (holding the api test lock):
 *   bash scripts/dev/reset.sh && bash scripts/dev/wait-idle.sh
 *   node frontend/scripts/smoke-p9-7.mjs http://localhost:5173
 *   bash scripts/dev/reset.sh
 * Screenshots of a failing step go to SMOKE_OUT (default: <OS temp>/smoke-p9-7). The last line is "smoke-p9-7: all <N> steps passed".
 */
import { chromium } from '@playwright/test';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const out = process.env.SMOKE_OUT || path.join(tmpdir(), 'smoke-p9-7');
const HISTORY = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../fixtures/replay/tool_fleet_returns.csv');
const ORG = 'Customer A';
const MODELER = `${base}/#/modeler?template=tool_fleet&org=${encodeURIComponent(ORG)}`;
const UI = 60000;
const FIRST = 180000; // a first page load after sign-in: the dev stack answers slowly
const REPLAY = 240000; // the replay runs in the worker
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const errors = [];
const pages = {};
let stepsRun = 0;
const say = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

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
  pages[acct] = p;
  return p;
}

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

/** Wait until the page text matches `rx`; fail naming what was missing and the nearest page text. */
async function waitText(p, rx, what, ms = UI) {
  const t0 = Date.now();
  let txt = '';
  while (Date.now() - t0 < ms) {
    txt = await p.innerText('body').catch(() => '');
    if (rx.test(txt)) return txt;
    await p.waitForTimeout(400);
  }
  throw new Error(`${what}: ${rx} not on the page (${txt.replace(/\s+/g, ' ').slice(0, 160)}…)`);
}

async function openModeler(p) {
  await p.goto(MODELER);
  await p.reload();
  await waitText(p, /Tool fleet returns/, 'the Modeler did not open the tool-fleet flow', FIRST);
  const fork = p.getByRole('button', { name: /Give Customer A its own flow/ });
  if (await fork.count()) {
    await fork.click();
    await waitText(p, /Tool fleet returns · Customer A|· Customer A/, 'Customer A did not get its own flow');
  }
}

/** The stepper on the lifecycle bar (Replay, Shadow, Canary, Full) opens the drawer with that step's panel. */
const stepper = (p, name) => p.locator('.mdl-life').getByRole('button', { name, exact: true });

async function importCsv(p, name, text) {
  await p.setInputFiles('#mdl-rp-file', { name, mimeType: 'text/csv', buffer: Buffer.from(text, 'utf8') });
}

// ---------------------------------------------------------------- 1
await step('1 planner.a: one rule through the assistant, Apply to draft', async () => {
  const p = await as('planner-a');
  await openModeler(p);
  const box = p.locator('.mdl-agent textarea');
  await box.waitFor({ timeout: FIRST });
  await box.fill('Never recycle construction lasers');
  await box.press('Enter');
  await waitText(p, /Proposed: /, 'the assistant showed no proposal card', 90000);
  await waitText(p, /BR-03: construction lasers: never recycle/, 'the proposal does not read BR-03');
  await p.getByRole('button', { name: 'Apply to draft' }).first().click();
  await waitText(p, /Draft · v\d+/, 'the flow is not a draft after Apply to draft');
  return 'draft saved';
});

// ---------------------------------------------------------------- 2
await step('2 Replay: the sample history, 120 rows, 0 held', async () => {
  const p = await as('planner-a');
  await stepper(p, 'Replay').click();
  await p.locator('.mdl-replay').waitFor();
  await importCsv(p, 'tool_fleet_returns.csv', readFileSync(HISTORY, 'utf8'));
  await waitText(p, /120 rows · 0 held/, 'the import did not read "120 rows · 0 held"');
  return '120 rows · 0 held';
});

// ---------------------------------------------------------------- 3
await step('3 Replay: one row with route scrap is held with its reason', async () => {
  const p = await as('planner-a');
  const lines = readFileSync(HISTORY, 'utf8').split(/\r?\n/);
  const head = lines.findIndex((l) => l.startsWith('item_id,')); // the file opens with a comment line
  const cols = lines[head].split(',');
  const at = cols.indexOf('actual_route');
  const row = lines[head + 1].split(',');
  row[at] = 'scrap';
  lines[head + 1] = row.join(',');
  const file = path.join(out, 'tool_fleet_returns_scrap.csv');
  writeFileSync(file, lines.join('\n'), 'utf8');
  await importCsv(p, 'tool_fleet_returns_scrap.csv', readFileSync(file, 'utf8'));
  await waitText(p, /\d+ rows · 1 held/, 'the second import did not read "1 held"');
  await waitText(p, /Route 'scrap' is not a route of tool_fleet/, "the held row's reason is not shown");
  return "1 held, Route 'scrap' is not a route of tool_fleet";
});

// ---------------------------------------------------------------- 4
await step('4 Replay the draft: the four numbers', async () => {
  const p = await as('planner-a');
  await p.locator('li[data-replay-batch]').first().getByRole('button', { name: 'Replay the draft' }).click();
  await p.locator('[data-replay-report]').waitFor({ timeout: REPLAY });
  const t = await p.locator('[data-replay-report]').innerText();
  for (const [rx, what] of [
    [/Route\s+Actual\s+Flow/, 'the route mix'],
    [/Straight-through: [\d.]+ %/, 'straight-through'],
    [/Approvals a day: [\d.]+/, 'approvals a day'],
    [/Exceptions a day: [\d.]+/, 'exceptions a day'],
    [/Uplift: .*80 % band/, 'the uplift with its 80 % band'],
  ]) {
    if (!rx.test(t)) throw new Error(`the replay report lacks ${what}: ${t.replace(/\s+/g, ' ').slice(0, 200)}`);
  }
  return t.match(/Straight-through: [\d.]+ %/)[0];
});

// ---------------------------------------------------------------- 5
await step('5 planner.a submits; the approver approves into shadow', async () => {
  const p = await as('planner-a');
  if (await p.locator('.mdl-drawer-x').count()) await p.locator('.mdl-drawer-x').click();
  await p.getByRole('button', { name: 'Submit for approval' }).click();
  await waitText(p, /In review · v\d+/, 'the flow is not In review after Submit');
  const ap = await as('approver');
  await openModeler(ap);
  await waitText(ap, /In review · v\d+/, 'the approver does not see the flow in review');
  await ap.getByRole('button', { name: 'Approve', exact: true }).click();
  await waitText(ap, /Shadow · v\d+/, 'the flow is not in Shadow after Approve');
  return 'Shadow';
});

// ---------------------------------------------------------------- 6
await step('6 Canary: the maker is refused with the reason, the approver starts FR at 20 %', async () => {
  const p = await as('planner-a');
  await p.reload();
  await waitText(p, /Shadow · v\d+/, 'planner.a does not see Shadow', FIRST);
  await stepper(p, 'Canary').click();
  const mine = p.locator('[data-rollout-start]').getByRole('button', { name: 'Start canary' });
  await mine.waitFor();
  const title = (await mine.getAttribute('title')) || '';
  if (!/Maker-checker: you made these changes, so you cannot widen their rollout\./.test(title)) {
    throw new Error(`planner.a's Start canary does not say Maker-checker: title "${title}"`);
  }
  const ap = await as('approver');
  await ap.reload();
  await waitText(ap, /Shadow · v\d+/, 'the approver does not see Shadow', FIRST);
  await stepper(ap, 'Canary').click();
  await ap.locator('#mdl-ro-region').fill('FR');
  await ap.locator('#mdl-ro-share').fill('20');
  await ap.locator('[data-rollout-start]').getByRole('button', { name: 'Start canary' }).click();
  await waitText(ap, /Canary: FR at 20 % of volume/, 'the panel does not read "Canary: FR at 20 % of volume"');
  return 'Canary: FR at 20 % of volume';
});

// ---------------------------------------------------------------- 7
await step('7 exec: Analytics, Back-test, the waterfall, the method note and a PDF over 10 kB', async () => {
  const p = await as('exec');
  await p.goto(`${base}/#/analytics`);
  await p.reload();
  const tab = p.getByRole('tab', { name: 'Back-test' }).or(p.getByRole('button', { name: 'Back-test', exact: true }));
  await tab.first().waitFor({ timeout: FIRST });
  await tab.first().click();
  await p.locator('[data-bt-report]').waitFor({ timeout: UI });
  await p.locator('[data-bt-waterfall]').waitFor({ timeout: UI });
  const method = await p.locator('[data-bt-method]').innerText();
  if (method.trim().length < 40) throw new Error(`the method note is empty: "${method}"`);
  await p.emulateMedia({ media: 'print' });
  const pdf = await p.pdf({ printBackground: true });
  await p.emulateMedia({ media: 'screen' });
  if (pdf.length <= 10 * 1024) throw new Error(`the PDF of the print view is ${pdf.length} bytes, not over 10 kB`);
  return `PDF ${Math.round(pdf.length / 1024)} kB`;
});

// ---------------------------------------------------------------- 8
await step('8 approver: the FR tables canary at 20 %, Canary against Standard quote', async () => {
  const ap = await as('approver');
  await openModeler(ap);
  await stepper(ap, 'Canary').click();
  const sec = ap.locator('.mdl-rollout').filter({ has: ap.locator('[data-rollout-subject]') });
  await sec.waitFor({ timeout: UI });
  await sec.locator('#mdl-rt-market').selectOption('FR');
  await sec.locator('#mdl-rt-share').fill('20');
  await sec.getByRole('button', { name: 'Start tables canary' }).click();
  await waitText(ap, /FR tables at 20 % of FR tickets/, 'the tables canary line is not shown');
  const table = sec.locator('[data-rollout-table-report]');
  await table.waitFor({ timeout: UI });
  const t = await table.innerText();
  if (!/Canary/.test(t) || !/Standard quote/.test(t)) throw new Error(`the report lacks the arms Canary and Standard quote: ${t.replace(/\s+/g, ' ')}`);
  if (!/Decision tables · FR/.test(await sec.innerText())) throw new Error('the subject does not read "Decision tables · FR"');
  return 'Canary vs Standard quote';
});

await browser.close();
if (errors.length) {
  say('page errors (not failures):', JSON.stringify(errors.slice(0, 5)));
}
say(`smoke-p9-7: all ${stepsRun} steps passed`);
