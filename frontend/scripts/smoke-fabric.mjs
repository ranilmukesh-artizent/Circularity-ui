/**
 * The Connection Fabric in the browser, against the running stack (plan 6 D2). As Developer it connects a catalogue
 * system (PostgreSQL) through its five steps and waits for the first sync, rotates its credential and syncs again,
 * edits a mapping rule on a demo source (Preview, Save, Revert), resolves a conflict, runs a Manual Import, builds a
 * Salesforce ingest workflow in Workflow Studio (Convert currency to EUR, Order late events, an error handler, a
 * validation rule; Validate, Test run, Save, Publish, Run now, History, Reprocess the records the rule held), then
 * deletes the workflow and the source it created. One line per step; exit code 0 only when every step passed and the
 * page threw no error. SMOKE_SHOTS=<dir> saves a full-page screenshot of each failed step there.
 *
 * Changes state (a mapping version, a resolved conflict, imported rows, a run of the new workflow): run
 * scripts/dev/reset.sh and scripts/dev/wait-idle.sh before (the conflicts exist only once the post-reset syncs have
 * run) and reset.sh after. The worker must be running (it runs the syncs and the workflow runs). Hold the api test
 * lock while it runs, so no test resets the data mid-run (docs/agents/testing.md).
 *   node scripts/smoke-fabric.mjs http://localhost:5173
 */
import { chromium } from '@playwright/test';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const shots = process.env.SMOKE_SHOTS || ''; // a folder: a screenshot of the page is saved there when a step fails
const CAT = 'postgres'; // the catalogue system: row data-int "cat:postgres" while available, "postgres" once connected
const DEMO = 'insp'; // SafetyCulture: the demo source whose mapping is edited
// The workflow's source and the key its Order late events step de-duplicates on. A demo source (a catalogue source can
// have a workflow too, tests/test_fabric_followups.py). The run writes the CRM's canonical data (amounts in EUR) until
// the next sync or reset.
const WF_SRC = 'crm', WF_KEY = 'Id'; // a field the CRM's records carry (the server checks it)
const WF_RULE = 'StageName'; // Validation & enrichment: "present"; only opportunities carry it, so the run holds the rest
// the credential source-sim's synthetic mock of the catalogue system accepts (di/connectors/catalog.py _demo_secret);
// rotating to any other value makes the next sync fail with 401, as it should
const CAT_SECRET = `${CAT}-demo-key`;
const WF_NAME = 'Smoke fabric ' + Date.now().toString(36);
const T = { ui: 45000, sync: 180000, run: 180000 };

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
// every toast the page shows, in order (they disappear after a few seconds)
await ctx.addInitScript(() => {
  window.__toasts = [];
  new MutationObserver((ms) => {
    for (const m of ms)
      for (const n of m.addedNodes) {
        if (n.nodeType !== 1) continue;
        // a toast, or a container mounted with its first toast inside (the Undo toasts)
        for (const t of n.classList.contains('toast') ? [n] : n.querySelectorAll('.toast')) window.__toasts.push(t.textContent || '');
      }
  }).observe(document, { childList: true, subtree: true });
});
const page = await ctx.newPage();
page.setDefaultTimeout(T.ui);
const errors = [];
page.on('pageerror', (e) => errors.push(e.message + ' @ ' + (e.stack || '').split('\n').slice(1, 3).join(' | ').replace(/\s+/g, ' ')));

const say = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);
const results = [];
const state = { connected: false, wfId: null, runRow: null };

async function step(name, fn) {
  const t0 = Date.now();
  try {
    const detail = await fn();
    results.push({ name, ok: true });
    say('PASS', name, detail ? '· ' + detail : '', `(${Math.round((Date.now() - t0) / 1000)} s)`);
  } catch (e) {
    results.push({ name, ok: false });
    say('FAIL', name, '·', String(e?.message || e).split('\n')[0], `(${Math.round((Date.now() - t0) / 1000)} s)`);
    if (shots) await page.screenshot({ path: `${shots}/fail-${results.length}.png`, fullPage: true }).catch(() => {});
  }
}
const check = (c, msg) => { if (!c) throw new Error(msg); };

// ---- toasts
const toastMark = () => page.evaluate(() => window.__toasts.length);
async function waitToast(re, mark, timeout = T.ui) {
  const end = Date.now() + timeout;
  for (;;) {
    const all = await page.evaluate(() => window.__toasts);
    const hit = all.slice(mark).find((t) => re.test(t));
    if (hit) return hit;
    if (Date.now() > end) throw new Error(`no toast ${re} (saw: ${JSON.stringify(all.slice(mark)).slice(0, 300)})`);
    await page.waitForTimeout(250);
  }
}
/** Click, then wait for a toast matching `re`. */
async function clickToast(loc, re, timeout) {
  const m = await toastMark();
  await loc.click();
  return waitToast(re, m, timeout);
}
/** Poll `fn` until it returns a truthy value (or throw `msg` after `timeout`). */
async function until(fn, msg, timeout = T.ui, every = 1000) {
  const end = Date.now() + timeout;
  for (;;) {
    const v = await fn().catch(() => null);
    if (v) return v;
    if (Date.now() > end) throw new Error(msg);
    await page.waitForTimeout(every);
  }
}

// ---- navigation
const go = async (route) => {
  await closeDrawer();
  await page.goto(`${base}/#/${route}`);
  await page.locator('#view').waitFor();
};
const dlg = () => page.locator('[role=dialog]').last();
const drawer = () => page.locator('aside.drawer.on');
async function closeDrawer() {
  for (let i = 0; i < 4 && (await page.locator('[role=dialog]').count()); i++) {
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
  }
}
async function openSource(id, tab) {
  await closeDrawer();
  await go('integration/overview');
  // the row's ⋯ menu renders once the source itself has loaded; clicking the name before that throws in the app
  // (FabricOverview IntRow: a row with neither src nor c, just after a connect)
  await page.locator(`tr[data-int="${id}"] summary[aria-label^="Actions for"]`).waitFor();
  await page.locator(`tr[data-int="${id}"] button.frintn`).click();
  await drawer().getByRole('tab').first().waitFor();
  if (tab) await drawer().getByRole('tab', { name: tab }).click();
}
const drawerText = () => drawer().innerText();

async function signIn(acct) {
  await page.goto(base + '/#/signin');
  await page.fill('#si-id', acct);
  await page.fill('#si-pw', 'demo');
  await page.click('button[type=submit]');
  await page.waitForURL((u) => !/signin/.test(u.hash), { timeout: T.ui });
}

/** Delete the connected catalogue source through its drawer (type the name, Delete source). */
async function deleteSource() {
  await openSource(CAT, 'Configuration'); // the edit footer holds Delete
  await drawer().getByRole('button', { name: 'Delete', exact: true }).click();
  const name = (await dlg().locator('label[for=delType] b').innerText()).trim();
  await dlg().locator('#delType').fill(name);
  const m = await toastMark();
  await dlg().locator('#delBtn').click();
  await waitToast(/deleted\./, m);
  await closeDrawer();
  await go('integration/overview');
  await until(async () => (await page.locator(`tr[data-int="cat:${CAT}"]`).count()) > 0, 'the catalogue row did not come back as Available');
  return name;
}

// ---------------------------------------------------------------- the run
await signIn('developer');
say('signed in as developer at', base);

// a leftover from an earlier run that did not clean up
await go('integration/overview');
await page.locator(`tr[data-int="${CAT}"], tr[data-int="cat:${CAT}"]`).first().waitFor();
if (await page.locator(`tr[data-int="${CAT}"]`).count()) {
  say('note: PostgreSQL is already connected (an earlier run did not clean up); deleting it first');
  await deleteSource();
}

// 1. connect PostgreSQL from the catalogue, through its five steps, and wait for the first sync
await step('1 Connect PostgreSQL from the catalogue (5 steps, first sync)', async () => {
  await go('integration/overview');
  await page.getByRole('button', { name: 'New integration' }).click();
  await dlg().getByText('PostgreSQL', { exact: true }).click();
  await dlg().getByRole('heading', { name: 'Connect PostgreSQL' }).waitFor();
  // 1 Authentication: an API key, prefilled with the simulated system's sandbox key (another key fails at Auth)
  await dlg().locator('input[name=frAuth][value=key]').check();
  await until(async () => (await dlg().locator('#frKey').inputValue()) === CAT_SECRET, 'the API key is not prefilled with the sandbox key');
  await dlg().getByText('This is the sandbox key of the simulated system.').waitFor();
  await dlg().getByRole('button', { name: 'Continue' }).click();
  // 2 Scopes: read only
  await dlg().getByText('Grant only what Circularity needs').waitFor();
  await dlg().getByRole('button', { name: 'Continue' }).click();
  // 3 Test connection: the server's probe
  await dlg().getByRole('button', { name: 'Test connection' }).click();
  await until(async () => /Connection test passed/.test(await dlg().innerText()), 'Test connection did not pass: ' + (await dlg().innerText().catch(() => '')).slice(-200), 60000);
  await dlg().getByRole('button', { name: 'Continue' }).click();
  // 4 Field mapping: Suggest mappings returns the fields the records really carry
  await dlg().getByRole('button', { name: 'Suggest mappings' }).click();
  const rows = dlg().locator('tbody tr');
  await until(async () => (await rows.count()) > 0, 'Suggest mappings returned no rows', 60000, 500);
  const fields = await rows.locator('td.mono:nth-child(2)').allInnerTexts();
  check(fields.includes('asset_id'), 'suggested fields lack asset_id: ' + fields.join(', '));
  await dlg().getByRole('button', { name: 'Accept all high' }).click();
  const acc = await dlg().getByText(/\d+ of \d+ accepted/).innerText();
  check(!/^0 of/.test(acc), 'Accept all high accepted nothing');
  await dlg().getByRole('button', { name: 'Continue' }).click();
  // 5 First sync
  await until(async () => /Connected · first sync queued/.test(await dlg().innerText()), 'the connection was not made', T.sync, 500);
  state.connected = true;
  await dlg().getByRole('button', { name: 'Done' }).click();
  // the first sync runs in the worker; Sync now if it has not run after a minute
  await openSource(CAT, 'Sync & History');
  // the newest sync run (the first row; a source connected again under the same id starts with no runs)
  const newest = () => drawer().locator('table tbody tr').first().innerText();
  const synced = async () => {
    const m = (await newest()).match(/SYNC-\S+\s+\S+\s+\S+\s+([\d,]+)\s+[\d.]+ s\s+Success/);
    return m && +m[1].replace(/,/g, '') > 0 ? m[1] : null;
  };
  let n = await until(synced, '', 60000, 2000).catch(() => null);
  if (!n) {
    say('  the first sync has not run after 60 s: Sync now');
    await drawer().getByRole('button', { name: 'Sync now' }).first().click();
    n = await until(synced, 'no successful sync with records in Sync & History', T.sync, 2000);
  }
  await drawer().getByRole('tab', { name: 'Overview' }).click();
  const ov = await drawerText();
  check(/\b0 failed records\b/.test(ov), 'the Overview does not say 0 failed records');
  const rec = ov.match(/Records synced\s+([\d,]+)/)?.[1];
  check(rec && +rec.replace(/,/g, '') > 0, 'the Overview shows no records synced');
  return `${fields.length} fields suggested (${acc}), first sync ${n} records, Overview: ${rec} records synced, 0 failed records`;
});

// 2. rotate its credential; the Security tab shows the new version and last four; Sync now still works
await step('2 Rotate the credential (Security), then Sync now', async () => {
  check(state.connected, 'no source (step 1 failed)');
  await openSource(CAT, 'Security');
  const before = (await drawerText()).match(/version (\d+)/)?.[1];
  const last4 = CAT_SECRET.slice(-4);
  await drawer().getByRole('button', { name: 'Rotate secret' }).click();
  await dlg().locator('#rotSecret').fill(CAT_SECRET);
  await clickToast(dlg().getByRole('button', { name: 'Save credentials' }), /Credentials updated for /);
  const want = `Encrypted by Circularity · version ${+before + 1} · ends in ••••${last4}`;
  await until(async () => (await drawerText()).includes(want), `the Security tab does not show "${want}"`);
  await drawer().getByRole('tab', { name: 'Sync & History' }).click();
  const m = await toastMark();
  await drawer().getByRole('button', { name: 'Sync now' }).first().click();
  const t = await waitToast(/synced: [\d,]+ records updated|sync failed/, m, T.sync);
  check(/synced:/.test(t), t);
  return `"${want}"; ${t}`;
});

// 3. edit a mapping rule on a demo source, Preview it on a sample record, Save (a new version), Revert
await step('3 Edit a mapping rule on SafetyCulture: Preview, Save, Revert', async () => {
  await openSource(DEMO, /Data Mapping/);
  const bar = drawer().locator('.callout.info').first();
  const rule = drawer().locator('input[aria-label="Rule row 1"]');
  const was = await rule.inputValue();
  const target = await drawer().locator('input[aria-label="Canonical field row 1"]').inputValue();
  await rule.fill('upper');
  await drawer().getByRole('button', { name: 'Preview on a sample record' }).click();
  await until(async () => /Sample record \S+/.test(await bar.innerText()), 'Preview showed no sample record: ' + (await bar.innerText().catch(() => '')).slice(-200), 60000, 500);
  const pv = await bar.innerText();
  check(/Changed/.test(pv), 'the preview marks no fact as Changed');
  const sample = pv.match(/Sample record (\S+)/)[1];
  const saved = await clickToast(drawer().getByRole('button', { name: 'Save changes' }), /saved( \(\d+ rows?\))?\. Configuration is now v/); // "Field mapping saved (3 rows)." since P9-0.10
  const ver = await until(async () => (await bar.innerText()).match(/Mapping v(\d+) runs on every sync/)?.[1], 'the mapping version is not shown after Save');
  check(+ver >= 2, 'Save did not make a new mapping version (v' + ver + ')');
  const pick = drawer().locator('select[aria-label="Mapping version to revert to"]');
  const older = await pick.locator('option').allInnerTexts();
  const v1 = older.find((o) => /^v1\b/.test(o));
  check(v1, 'no v1 to revert to: ' + older.join(', '));
  await pick.selectOption({ label: v1 });
  const rv = await clickToast(drawer().getByRole('button', { name: 'Revert', exact: true }).first(), /Field mapping reverted to v1/);
  await until(async () => (await rule.inputValue()) === was, `the rule is "${await rule.inputValue()}" after Revert, expected "${was}"`);
  return `${target}: "${was}" → upper (preview on ${sample}), ${saved.replace(/^.*Configuration/, 'configuration')} mapping v${ver}; ${rv}`;
});

// 4. resolve a conflict choosing the other system's value, with a reason; it stays resolved after a reload
await step('4 Resolve a conflict in the Conflict Queue (another value, with a reason)', async () => {
  await closeDrawer();
  await go('integration/conflicts');
  const kpi = async () => +(await page.locator('.frkpis').first().innerText()).match(/(\d+)\s*Open conflicts/)[1];
  const open0 = await until(async () => { const n = await kpi(); return n > 0 ? n : null; }, 'no open conflict (did the post-reset syncs run? scripts/dev/wait-idle.sh)', 60000);
  const closed0 = +(await page.locator('.frkpis').first().innerText()).match(/(\d+)\s*Resolved or escalated/)[1];
  // the card by position: its "Choose another value" button goes away once the choice opens
  const cards = page.locator('.grid.g3 > .panel');
  const at = await cards.evaluateAll((l) => l.findIndex((c) => [...c.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Choose another value')));
  check(at >= 0, 'no open conflict card offers "Choose another value"');
  const card = cards.nth(at);
  const kind = (await card.locator('.ph h3').innerText()).trim(), asset = (await card.locator('.pb b').first().innerText()).trim();
  await card.getByRole('button', { name: 'Choose another value' }).click();
  const other = card.locator('label', { hasText: /^Keep / }).first();
  let how, t;
  if (await other.count()) {
    how = (await other.innerText()).trim();
    await other.locator('input[type=radio]').check();
    await card.locator('input[id^="cfr-"]').fill('Smoke test: the newer reading is right');
    t = await clickToast(card.getByRole('button', { name: 'Resolve', exact: true }), /resolved/);
  } else {
    how = 'the authority (no other value offered)';
    await card.getByRole('button', { name: 'Cancel' }).click();
    t = await clickToast(card.getByRole('button', { name: /^Accept / }), /resolved/);
  }
  const id = t.match(/CF-\d+/)?.[0];
  await page.reload();
  await page.locator('.frkpis').first().waitFor();
  const open1 = await until(async () => { const n = await kpi(); return n === open0 - 1 ? n : null; }, `open conflicts did not drop by one after a reload (${open0} before)`, 30000);
  // the queue shows open conflicts first, 60 at a time (Show more), so the resolved card is usually off the first page:
  // the "Resolved or escalated" figure must have gone up by one instead
  const closed1 = +(await page.locator('.frkpis').first().innerText()).match(/(\d+)\s*Resolved or escalated/)[1];
  check(closed1 === closed0 + 1, `"Resolved or escalated" is ${closed1} after a reload, expected ${closed0 + 1}`);
  const same = page.locator('.grid.g3 > .panel', { hasText: asset }).filter({ has: page.locator('.ph h3', { hasText: kind }) });
  const chips = await same.locator('.ph .chip').allInnerTexts();
  if (chips.length) check(chips.includes('Resolved'), `${kind} · ${asset} is still not Resolved after a reload (${chips.join(', ')})`);
  return `${id}: ${kind} · ${asset}, chose ${how}; "${t}"; open ${open0} → ${open1}, resolved ${closed0} → ${closed1} after a reload`;
});

// 5. Manual Import: Load sample file → Validate → Load rows
await step('5 Manual Import: Load sample file, Validate, Load rows', async () => {
  await go('integration/import');
  await page.getByRole('button', { name: 'Load sample file' }).click();
  check((await page.locator('#csvt').inputValue()).startsWith('asset_id'), 'the sample file did not load');
  await page.getByRole('button', { name: 'Validate', exact: true }).click();
  const chip = await page.getByText(/\d+ ready · \d+ rejected/).innerText();
  const load = page.getByRole('button', { name: /^Load \d+ rows for evaluation$/ });
  const t = await clickToast(load, /rows loaded for evaluation|already loaded/);
  check(/rows loaded for evaluation/.test(t), t + ' (reset the stack before running)');
  return `${chip}; "${t.slice(0, 90)}"`;
});

// 6. Workflow Studio: build, check, test, save, publish, run
const node = (label) => page.locator('.wfn', { has: page.locator('.lb', { hasText: new RegExp('^' + label.replace(/[.*+?^${}()|[\]\\&]/g, '\\$&') + '$') }) });
const insp = () => page.locator('#wfInsp');
async function addBlock(label) {
  await page.locator('#frPalQ').fill(label);
  const b = page.locator(`#wfPal button[aria-label="Add ${label}"]`).first();
  const m = await toastMark();
  await b.focus();
  await page.keyboard.press('Enter');
  await waitToast(new RegExp(label + ' added'), m);
  await page.locator('#frPalQ').fill('');
}
async function select(label) {
  await node(label).click();
  await insp().locator('h3', { hasText: label }).waitFor();
}
/** The blocks the selected block sends to (the inspector's Sends to list). */
const sendsTo = () => insp().evaluate((el) => [...el.querySelectorAll('div')].filter((d) => d.firstElementChild?.textContent === 'Sends to').flatMap((d) => [...d.querySelectorAll('li b')].map((b) => b.textContent)));
/** Link `from` → `to` in the inspector: Next step, or + Add another connection when it already sends somewhere. */
async function link(from, to) {
  await select(from);
  const add = insp().getByRole('button', { name: '+ Add another connection' });
  if (await add.count()) await add.click();
  await insp().locator('#wfTo').selectOption({ label: to });
  await select(from);
  await until(async () => (await sendsTo()).includes(to), `${from} does not send to ${to}`, 10000, 300);
}
async function moreActions(item) {
  await page.locator('summary', { hasText: 'More actions' }).click();
  await page.getByRole('menuitem', { name: item, exact: true }).click();
}

await step('6a Workflow Studio: + New workflow (ingest, Salesforce)', async () => {
  await closeDrawer();
  await go('integration/studio');
  await page.getByRole('button', { name: /New workflow/ }).first().click();
  await dlg().locator('#nwType').selectOption('ingest');
  await dlg().locator('#nwSrc').selectOption(WF_SRC);
  await dlg().locator('#nwName').fill(WF_NAME);
  const t = await clickToast(dlg().getByRole('button', { name: 'Create workflow' }), /created as a draft/);
  await page.waitForURL(/#\/integration\/studio\/WF-/);
  state.wfId = page.url().match(/WF-[\w-]+/)[0];
  await page.locator('#wfPal').waitFor();
  const n = await page.locator('.wfn').count();
  return `${state.wfId}, ${n} blocks; "${t.slice(0, 70)}…"`;
});

let mapLabel = '';
await step('6b Add Convert currency (EUR), Order late events (key fields) and an error handler, wire them, add a validation rule', async () => {
  check(state.wfId, 'no workflow (6a failed)');
  await select('Validation & enrichment');
  const sends = await sendsTo();
  check(sends.length === 1, 'Validation & enrichment should send to one block, sends to: ' + sends.join(', '));
  mapLabel = sends[0];
  await insp().getByRole('button', { name: 'Remove the connection to ' + mapLabel }).click();
  await addBlock('Order late events');
  await addBlock('Convert currency');
  await addBlock('Error handler');
  // the connector reads everything (a delta run after the post-reset syncs reads nothing new)
  await select('CRM');
  await insp().locator('select[id$="-mode"]').selectOption('full');
  await select('Convert currency');
  await insp().locator('select[id$="-currency"]').selectOption('EUR');
  await select('Order late events');
  const keys = insp().locator('input[id$="-keys"]');
  await keys.fill(WF_KEY);
  await keys.press('Enter');
  await link('Validation & enrichment', 'Order late events');
  await link('Order late events', 'Convert currency');
  await link('Convert currency', mapLabel);
  await link('Validation & enrichment', 'Error handler');
  // a validation rule some records break (only the opportunities carry it), so the run holds records to reprocess
  await select('Validation & enrichment');
  await insp().getByRole('button', { name: '+ Add rule' }).click();
  const rf = insp().locator('input[aria-label="Rule 1 field"]');
  await rf.fill(WF_RULE);
  await rf.press('Enter');
  await insp().locator('select[aria-label="Rule 1 check"]').selectOption('present');
  // the settings are kept on the blocks
  await select('Convert currency');
  check((await insp().locator('select[id$="-currency"]').inputValue()) === 'EUR', 'Convert currency lost EUR');
  await select('Order late events');
  check((await insp().locator('input[id$="-keys"]').inputValue()) === WF_KEY, 'Order late events lost its key');
  await select('Validation & enrichment');
  check((await insp().locator('input[aria-label="Rule 1 field"]').inputValue()) === WF_RULE, 'Validation & enrichment lost its rule');
  await page.getByRole('button', { name: 'Auto layout' }).click();
  return `Validation & enrichment (rule: ${WF_RULE} present) → Order late events (${WF_KEY}) → Convert currency (EUR) → ${mapLabel}; Validation & enrichment → Error handler; ${await page.locator('.wfn').count()} blocks`;
});

await step('6c Validate (0 errors), Test run (dry run, samples)', async () => {
  check(mapLabel, 'not built (6b failed)');
  const v = await clickToast(page.getByRole('button', { name: 'Validate', exact: true }), /error|No errors/);
  check(/^No errors/.test(v), v);
  check(/No errors/.test(await page.locator('#wfSum').innerText()), 'the Checks panel shows errors');
  const m = await toastMark();
  await page.getByRole('button', { name: 'Test run', exact: true }).click();
  const t = await waitToast(/Test run (finished|failed)|Fix \d+ error/, m, T.run);
  check(/finished/.test(t), t);
  const note = await page.locator('#wfDryNote').innerText();
  check(/Nothing was written/.test(note), 'no dry-run note: ' + note);
  // the before/after samples of a step
  const tasks = page.locator('.wfbot');
  const sb = tasks.getByRole('button', { name: 'Samples', exact: true }).first();
  check(await sb.count(), 'the task instances offer no samples');
  await sb.click();
  const samp = await until(async () => { const x = await tasks.innerText(); return (await tasks.locator('.frsamp').count()) ? x : null; }, 'the samples did not open', 10000, 300);
  return `"${v}"; "${t.slice(0, 80)}"; note "${note.slice(0, 70)}"; samples shown (${samp.length} chars)`;
});

let runRows = 0, held = 0;
await step('6d Save, Publish, Run now (a real run with real counts)', async () => {
  check(mapLabel, 'not built (6b failed)');
  const m1 = await toastMark();
  await moreActions('Save');
  const s = await waitToast(/saved as v[\d.]+/, m1);
  const m2 = await toastMark();
  await moreActions('Publish');
  const p = await waitToast(/published as v[\d.]+|Cannot publish/, m2);
  check(/published/.test(p), p);
  const m3 = await toastMark();
  await page.getByRole('button', { name: 'Run now', exact: true }).first().click();
  const r = await waitToast(/run finished, [\d,]+ records|run failed/, m3, T.run);
  check(/finished/.test(r), r);
  runRows = +r.match(/([\d,]+) records/)[1].replace(/,/g, '');
  check(runRows > 0, 'the run read no records: ' + r);
  // the Data quality panel follows once the page has the finished run (the toast comes first): wait for it to show the
  // run's held records (this workflow's validation rule holds some), up to 15 s
  const dq = await until(async () => { const x = await page.locator('#frDq').innerText(); return /View failed records \([1-9][\d,]*\)/.test(x) ? x : null; },
    'the Data quality panel never showed the run\'s held records', 15000, 500).catch(async (e) => { throw new Error(e.message + ': ' + (await page.locator('#frDq').innerText()).replace(/\s+/g, ' ').slice(0, 200)); });
  held = +(dq.match(/View failed records \(([\d,]+)\)/)?.[1] ?? '0').replace(/,/g, '');
  return `"${s}"; "${p}"; "${r}"; ${held} held`;
});

await step('6e History tab lists the version and the run', async () => {
  check(runRows, 'no run (6d failed)');
  await page.locator('[data-seg=wftab]').getByRole('tab', { name: 'History' }).click();
  const versions = page.locator('.panel', { has: page.locator('h3', { hasText: 'Versions' }) });
  const runs = page.locator('.panel', { has: page.locator('h3', { hasText: 'Runs' }) });
  const vt = await until(async () => { const x = await versions.innerText(); return /Runs use v[\d.]+/.test(x) ? x : null; }, 'the Versions panel does not say which version runs');
  const pub = vt.match(/Runs use v([\d.]+)/)[1];
  check(vt.includes('v' + pub), 'the version list lacks v' + pub);
  const n = runRows.toLocaleString('en-US');
  const row = await until(async () => (await runs.locator('tbody tr').allInnerTexts()).find((l) => /Success/.test(l) && l.includes(n)),
    `no successful run with ${n} records in the Runs table`, 30000).catch(async (e) => { throw new Error(e.message + ': ' + (await runs.innerText()).replace(/\s+/g, ' ').slice(0, 300)); });
  state.runRow = row.split(/\s/)[0];
  return `runs use v${pub}; run: ${row.replace(/\s+/g, ' ').trim()}`;
});

await step('6f Failed records of the run (held by the rule): Reprocess', async () => {
  check(state.runRow, 'no run in the History tab (6e failed)');
  // the run's View → View failed records (the records the error handler holds)
  const runs = page.locator('.panel', { has: page.locator('h3', { hasText: 'Runs' }) });
  await runs.locator('tbody tr', { hasText: state.runRow }).getByRole('button', { name: 'View' }).click();
  await dlg().getByRole('button', { name: 'View failed records' }).click();
  await dlg().getByRole('heading', { name: /Failed records/ }).waitFor();
  const txt = await dlg().innerText();
  const n = +(txt.match(/([\d,]+) records? from the latest run broke a validation rule/)?.[1] ?? '0').replace(/,/g, '');
  check(n > 0, `the run held no records (the ${WF_RULE} rule should hold some): ${txt.replace(/\s+/g, ' ').slice(0, 200)}`);
  check(n === held, `Data quality said ${held} held but the run's failed records list ${n}`);
  const rule = (await dlg().locator('tbody tr').first().innerText()).replace(/\s+/g, ' ');
  const t = await clickToast(dlg().getByRole('button', { name: 'Reprocess' }), /records sent back/, T.run);
  return `${state.runRow}: ${n} held (Data quality said ${held}; first: ${rule}); "${t}"`;
});

// 7. clean up: delete the workflow, then the catalogue source
await step('7 Clean up: delete the workflow and the PostgreSQL source', async () => {
  const done = [];
  if (state.wfId) {
    await closeDrawer();
    if (!/studio\/WF-/.test(page.url())) await go('integration/studio/' + state.wfId);
    await page.locator('[data-seg=wftab]').getByRole('tab', { name: 'Workflow studio' }).click();
    await page.locator('#wfPal').waitFor();
    await moreActions('Delete');
    const t = await clickToast(dlg().getByRole('button', { name: 'Delete workflow' }), /deleted\./);
    done.push(t);
    await go('integration/studio');
    await page.getByRole('button', { name: /New workflow/ }).first().waitFor();
    await until(async () => !(await page.locator('table tr', { hasText: WF_NAME }).count()), 'the workflow is still listed', 30000);
  }
  await go('integration/overview');
  await page.locator(`tr[data-int="${CAT}"], tr[data-int="cat:${CAT}"]`).first().waitFor();
  if (await page.locator(`tr[data-int="${CAT}"]`).count()) done.push(`source "${await deleteSource()}" deleted, PostgreSQL Available again`);
  return done.join('; ') || 'nothing to clean up';
});

const failed = results.filter((r) => !r.ok);
say('page errors:', errors.length ? errors.slice(0, 5) : 'none');
say(failed.length || errors.length ? `FAILED: ${failed.length} of ${results.length} steps` : `all ${results.length} steps passed`);
await browser.close();
process.exit(failed.length || errors.length ? 1 : 0);
