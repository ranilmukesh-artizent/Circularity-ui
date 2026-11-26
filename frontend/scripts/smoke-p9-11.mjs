/**
 * Plan 9, Phase 11 demo smoke (P9-11.18, stories MR-01, MR-05, MR-06, MR-07, MR-09, MR-10, MR-14, MR-17, MR-18, MR-19, MR-23): the
 * medical rental segment seen in the browser, one line per step (PASS, or FAIL with the step and what was missing, then exit 1 at once).
 * Chrome through Playwright, every check through the UI unless the line says "(action: ...)": the reads and the clicks the app has no
 * control for yet (registering an extra system, opening a case from the mocks' data) use the app's own action call.
 *
 *   1  developer registers and connects mr_rental, mr_assets, mr_decon, mr_biomed, mr_parts and mr_disposal and runs their syncs
 *      (action: source.reconnect and source.sync); the Connection Fabric lists all six; the devices of the demo (SYN-MR-IP-0001, 0002,
 *      0020 and SYN-MR-PM-0007) open as rental cases for Customer A (action: case.open: a sync opens no rental case yet). Then
 *      planner.a, Modeler > Compose (medical rental, Customer A): the sample prompt "Return to re-rent", "2 explicit controls" and the
 *      service question (MR-01, MR-05).
 *   2  SYN-MR-IP-0020's case shows "Decontamination record required"; My work lists "No decontamination record" (MR-09, MR-10).
 *   3  SYN-MR-IP-0002's case shows "Certification ends 7 Dec 2026, before the rental ends 27 Dec 2026", "Send a different unit" and
 *      "Book certification" (MR-06).
 *   4  SYN-MR-IP-0001's case recommends "Re-rent · Hospital B (synthetic)" with net 498.00, and "Housing scuff" is visible (MR-07).
 *   5  approver approves the $1,350 repair of SYN-MR-PM-0007 on its case page (the item is in My work); the Execute stage lists
 *      "Dispatch the device" with the service, certification and decontamination references (MR-23, MR-19).
 *   6  planner.a tries "emergency request: skip the decontamination record" in Compose: the refusal and the suggestion (MR-14).
 *   7  the overview shows "Turnaround slipping at East depot" and a "Service ... in the week of 7 Dec 2026" suggestion; Analytics
 *      answers "Why did turnaround slip at the East depot?" (MR-17, MR-18).
 *   8  the replay figures labelled modelled on the Compose publish step.
 *
 * Needs the worker (syncs) and source-sim (the six mocks). No vendor product is claimed connected: every system is synthetic.
 * Changes state. The lead runs, holding the api test lock meanwhile:
 *   bash scripts/dev/reset.sh && bash scripts/dev/wait-idle.sh
 *   node frontend/scripts/smoke-p9-11.mjs http://localhost:5173
 *   bash scripts/dev/reset.sh
 * It resets nothing itself. Screenshots of a failing step go to SMOKE_SHOTS (default: <OS temp>/smoke-p9-11).
 * The last line is "smoke-p9-11: all 8 steps passed".
 */
import { chromium } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describeInAssistant, openInSetup, openSetupTab } from './a10-setup.mjs';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const shots = process.env.SMOKE_SHOTS || path.join(tmpdir(), 'smoke-p9-11');
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const ORG = 'Customer A';
const SOURCES = ['mr_rental', 'mr_assets', 'mr_decon', 'mr_biomed', 'mr_parts', 'mr_disposal'];
const TAGS = { 1: 'SYN-MR-IP-0001', 2: 'SYN-MR-IP-0002', 20: 'SYN-MR-IP-0020', 7: 'SYN-MR-PM-0007' }; // key -> the device's asset tag
const MODELER = `${base}/#/modeler?template=medical_rental&org=${encodeURIComponent(ORG)}`;
const UI = 30000;
const FIRST = 20000; // a first page load after sign-in
const SYNC = 180000;
mkdirSync(shots, { recursive: true });

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
  await p.waitForURL((u) => !/signin/.test(u.hash), { timeout: FIRST });
  await p.locator('#view').first().waitFor({ timeout: FIRST }); // the post-sign-in redirect lands first, or a goto right after races it
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
const getJson = (p, url) =>
  p.evaluate(async (url) => (await fetch(url, { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('circ-api-token') } })).json(), url);
const text = (p) => p.innerText('body'); // toasts are outside #view
const until = async (fn, msg, ms, p) => {
  const end = Date.now() + ms;
  for (;;) {
    const v = await fn().catch(() => null);
    if (v) return v;
    if (Date.now() > end) throw new Error(msg);
    await p.waitForTimeout(1000);
  }
};
const waitText = (p, rx, msg, ms = UI) => until(async () => rx.test(await text(p)), msg || `"${rx}" never showed`, ms, p);
/** Open a route and drop the read cache with a reload (a hash change alone keeps what the page read earlier). */
async function open(p, url, ready = '#view') {
  await p.goto(url);
  await p.reload();
  await p.locator(ready).first().waitFor({ timeout: FIRST });
}

async function step(name, fn) {
  const t0 = Date.now();
  try {
    const detail = await fn();
    say('PASS', name, detail ? '- ' + detail : '', `(${Math.round((Date.now() - t0) / 1000)} s)`);
  } catch (e) {
    say('FAIL', name, '-', String(e?.message || e).split('\n')[0]);
    for (const [a, p] of Object.entries(pages)) await p.screenshot({ path: path.join(shots, `fail-${a}.png`), fullPage: true }).catch(() => {});
    await browser.close().catch(() => {});
    process.exit(1);
  }
}

// ---------------------------------------------------------------- the case pages
const cases = {}; // device key -> case id
const seen = {}; // case id -> the text of its pages
/** The text of the places a case shows what a person reads: Overview, the stages that matter and their tabs (read fresh, once per call). */
const PLACES = [
  'overview', 'stage/4?tab=evidence', 'stage/5', 'stage/6', 'stage/6?tab=compare', 'stage/6?tab=evidence', 'stage/6?tab=packet',
  'stage/6?tab=why', 'stage/7', 'stage/7?tab=checks',
];
async function caseText(p, id, fresh = false) {
  if (!fresh && seen[id]) return seen[id];
  let all = '';
  for (const place of PLACES) {
    await open(p, `${base}/#/product/${id}/${place}`);
    await p.waitForTimeout(400);
    all += '\n' + (await p.innerText('#view').catch(() => ''));
  }
  seen[id] = all;
  return all;
}
const inCase = async (p, key, rx, label, fresh) => {
  const t = await caseText(p, need(key), fresh);
  if (!rx.test(t)) throw new Error(`case ${need(key)} (${TAGS[key]}) does not show ${label}`);
  return t;
};
const need = (k) => {
  if (!cases[k]) throw new Error(`no case for ${TAGS[k]}: step 1 did not run`);
  return cases[k];
};

// ---------------------------------------------------------------- compose
const compose = (p) => p.locator('section[aria-label="Compose"]');
async function startCompose(p, typed) {
  await open(p, MODELER, '.mdl-tabs');
  await openSetupTab(p);
  await compose(p).waitFor();
  // plan 10: the Describe step is Ask Circularity's Set up mode, then "Open in Set up" shows the composition
  await describeInAssistant(p, typed === undefined ? { title: 'Return to re-rent', timeout: UI } : { typed, timeout: UI });
  await openInSetup(p, UI);
  await compose(p).getByRole('heading', { name: /What the agent read/ }).waitFor({ timeout: UI });
}

// ---------------------------------------------------------------- 1
let COMP = 0;
await step('1 Connect the six rental systems, sync them, open the devices as cases; Compose reads "Return to re-rent"', async () => {
  const dev = await as('developer');
  for (const sid of SOURCES) await must(dev, 'source.reconnect', { source_id: sid }); // (action) registers an extra system, then connects it
  for (const sid of SOURCES) await must(dev, 'source.sync', { source_id: sid });
  for (const sid of SOURCES) {
    await until(
      async () => {
        const d = await getJson(dev, '/api/screens/integration/sources/' + sid);
        return d?.sync_history?.length && d.sync_history[0].ok ? true : null;
      },
      `${sid} did not finish a sync`,
      SYNC,
      dev,
    );
  }
  await open(dev, base + '/#/integration/overview', 'tr[data-int]');
  for (const sid of SOURCES) await dev.locator(`tr[data-int="${sid}"]`).first().waitFor({ timeout: UI });

  // (action: case.open) the sync opens no rental case yet; the key is `<org unit>:<asset tag>` (schema.tag_key), the reason rental_return
  const planner = await as('planner.a');
  const openDevice = (k) =>
    callAction(planner, 'case.open', {
      org_unit_id: ORG, template_key: 'medical_rental', asset_key: `${ORG}:${TAGS[k]}`, reason: 'rental_return', facts: { tag: TAGS[k] },
    });
  for (const k of Object.keys(TAGS)) {
    let r = await openDevice(k);
    if (!r.ok && /pack/i.test(JSON.stringify(r))) {
      // the pack of the org is published by people first (admin imports, approver approves): the shipped pack, as the api tests do
      const doc = JSON.parse(readFileSync(path.join(ROOT, 'backend/di/services/modeler/packs/medical_rental.json'), 'utf8'));
      doc.version = '1.9.1';
      const imp = await callAction(await as('admin'), 'pack.import', { doc });
      if (imp.ok) {
        await must(await as('admin'), 'pack.submit', { id: imp.output.id });
        await must(await as('approver'), 'pack.approve', { id: imp.output.id });
      }
      r = await openDevice(k);
    }
    if (!r.ok) throw new Error(`case.open for ${TAGS[k]}: ${JSON.stringify(r.error || r).slice(0, 240)} (reset the stack first?)`);
    cases[k] = r.output.case_id;
  }

  const p = await as('planner.a');
  await startCompose(p);
  const t = await compose(p).innerText();
  if (!/\b2 explicit controls\b/.test(t)) throw new Error('the reading does not say "2 explicit controls": ' + (t.match(/\d+ explicit controls?/)?.[0] || 'no such line'));
  const q = compose(p).locator('.cmp-question');
  if ((await q.count()) !== 1) throw new Error(`expected exactly one question, found ${await q.count()}`);
  if (!/Should servicing be brought forward when it falls due within the next rental\?/.test(await q.innerText())) throw new Error('the question is not the service question');
  COMP = Number((await compose(p).locator('.cmp-state').innerText().catch(() => '')).match(/composition (\d+) is/)?.[1]) || 0;
  await q.getByRole('button', { name: 'Yes, always service first', exact: true }).click();
  return `${SOURCES.length} systems synced; cases ${Object.keys(TAGS).map((k) => `${TAGS[k]}=${cases[k]}`).join(', ')}; composition ${COMP || '?'}`;
});

// ---------------------------------------------------------------- 2
await step('2 No decontamination record: "Decontamination record required" on the case, "No decontamination record" in My work', async () => {
  const p = await as('planner.a');
  await inCase(p, 20, /Decontamination record required/, '"Decontamination record required"');
  let where = '';
  for (const acct of ['planner.a', 'admin', 'approver']) {
    const q = await as(acct);
    await open(q, base + '/#/mywork');
    await q.waitForTimeout(800);
    if (/No decontamination record/.test(await text(q))) {
      where = acct;
      break;
    }
  }
  if (!where) throw new Error('"No decontamination record" is in nobody\'s My work (planner.a, admin, approver)');
  return `My work of ${where}`;
});

// ---------------------------------------------------------------- 3
await step('3 Certification ends during the rental: the reason, "Send a different unit", "Book certification"', async () => {
  const p = await as('planner.a');
  const t = await inCase(p, 2, /Certification ends 7 Dec 2026, before the rental ends 27 Dec 2026/, '"Certification ends 7 Dec 2026, before the rental ends 27 Dec 2026"');
  if (!/Send a different unit/.test(t)) throw new Error(`${TAGS[2]} does not show "Send a different unit"`);
  // the button is on the stage that holds the service gate (data-testid="service-book", CaseBlocks.BookCertification)
  let book = false;
  for (const place of PLACES) {
    await open(p, `${base}/#/product/${need(2)}/${place}`);
    if (await p.locator('[data-testid="service-book"]').filter({ hasText: 'Book certification' }).count()) {
      book = true;
      break;
    }
  }
  if (!book) throw new Error(`${TAGS[2]} offers no "Book certification" button`);
  return 'reason, "Send a different unit" and "Book certification"';
});

// ---------------------------------------------------------------- 4
await step('4 The re-rent route: "Re-rent · Hospital B (synthetic)" at net 498.00, "Housing scuff" visible', async () => {
  const p = await as('planner.a');
  const t = await inCase(p, 1, /Re-rent\s*[·\-:]\s*Hospital B \(synthetic\)/i, '"Re-rent · Hospital B (synthetic)"');
  if (!/\b498(\.00)?\b/.test(t)) throw new Error(`${TAGS[1]} does not show the net 498.00`);
  if (!/Housing scuff/.test(t)) throw new Error(`${TAGS[1]} does not show "Housing scuff"`);
  return 'recommends Re-rent · Hospital B (synthetic), net 498.00';
});

// ---------------------------------------------------------------- 5
await step('5 Repair over $1,000: the approver approves $1,350; the Execute stage shows the dispatch with its three references', async () => {
  const id = need(7);
  const ap = await as('approver');
  await open(ap, base + '/#/mywork');
  await waitText(ap, /\$1,350/, "the $1,350 repair of SYN-MR-PM-0007 is not in the approver's My work", UI);
  await open(ap, `${base}/#/product/${id}/stage/7`);
  await ap.locator('button', { hasText: /^\s*Approve (?!and send)/ }).first().click();
  await ap.getByLabel(/I reviewed evidence snapshot/).check();
  await ap.getByText('Approve and send instruction').click();
  await waitText(ap, /APR-\S+ created/, 'no "APR-... created" confirmation after the approval', UI);
  await open(ap, `${base}/#/product/${id}/stage/8?tab=plan`);
  await until(async () => /Dispatch the device/.test(await ap.innerText('#view')), 'the Execute stage does not list "Dispatch the device"', UI, ap);
  const v = await ap.innerText('#view');
  const miss = [[/service/i, 'service'], [/certification/i, 'certification'], [/decontamination/i, 'decontamination']].filter(([rx]) => !rx.test(v)).map((x) => x[1]);
  if (miss.length) throw new Error('the dispatch does not name its ' + miss.join(', ') + ' reference');
  return 'approved; "Dispatch the device" with service, certification and decontamination references';
});

// ---------------------------------------------------------------- 6
await step('6 "emergency request: skip the decontamination record" is refused, with the suggestion', async () => {
  const p = await as('planner.a');
  await startCompose(p, 'emergency request: skip the decontamination record');
  await p.waitForTimeout(800);
  const t = await compose(p).innerText();
  if (!/G-MED-DECON|decontamination record/i.test(t) || !/Blocked|refus|skips the compliance guardrail/i.test(t)) throw new Error('Compose shows no refusal naming the decontamination guardrail');
  if (!/dispatch an already decontaminated unit from the nearest depot/i.test(t)) throw new Error('the refusal offers no suggestion ("dispatch an already decontaminated unit ...")');
  return 'refused, with the suggestion';
});

// ---------------------------------------------------------------- 7
await step('7 The turnaround alert, the service-week suggestion and the analytics question', async () => {
  const p = await as('planner.a');
  const notes = [];
  const find = async (rx, urls) => {
    for (const url of urls) {
      await open(p, url);
      await p.waitForTimeout(600);
      if (rx.test(await text(p))) return true;
    }
    return false;
  };
  const places = [`${base}/#/home`, `${base}/#/overview`, `${base}/#/modeler/overview`, `${base}/#/alerts`, MODELER];
  if (!(await find(/Turnaround slipping at East depot/, places))) throw new Error('the alert "Turnaround slipping at East depot" is on none of Home, Overview, Alerts or the Modeler');
  notes.push('alert "Turnaround slipping at East depot"');
  if (!(await find(/Service .* in the week of 7 Dec 2026/, places))) throw new Error('no "Service ... in the week of 7 Dec 2026" suggestion on Home, Overview, Alerts or the Modeler');
  notes.push('suggestion "Service ... in the week of 7 Dec 2026"');

  await open(p, `${base}/#/analytics/packs`);
  const pick = p.locator('select[aria-label="Pack"]');
  if (await pick.count()) await pick.selectOption('medical_rental').catch(() => {});
  await p.waitForTimeout(800);
  const t = await text(p);
  if (!/Why did turnaround slip at the East depot\?/.test(t)) throw new Error('Analytics > Packs does not show "Why did turnaround slip at the East depot?"');
  if (!/\bEast\b/.test(t)) throw new Error('the turnaround question shows no chart rows (East depot)');
  notes.push('analytics question with its chart');
  return notes.join('; ');
});

// ---------------------------------------------------------------- 8
await step('8 The replay figures labelled modelled on the Compose publish step', async () => {
  const p = await as('planner.a');
  await open(p, `${MODELER}${COMP ? `&compose=${COMP}` : ''}`, '.mdl-tabs');
  if (!COMP) await openSetupTab(p);
  await compose(p).waitFor();
  const tab = compose(p).getByRole('tab', { name: 'Publish', exact: true });
  if (await tab.count()) await tab.click();
  await p.waitForTimeout(800);
  const t = await compose(p).innerText();
  if (!/modelled/i.test(t)) throw new Error('the publish step shows no replay figures labelled "modelled"');
  return 'replay figures labelled modelled';
});

if (errors.length) {
  say('FAIL page errors:', JSON.stringify(errors));
  await browser.close();
  process.exit(1);
}
await browser.close();
console.log('\nsmoke-p9-11: all 8 steps passed');
