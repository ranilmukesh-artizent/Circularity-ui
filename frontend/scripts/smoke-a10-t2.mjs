/**
 * Plan 10, T2 browser check: Change flow mode and the agent-first sections of the pinned column on the Modeler.
 * WRITES (it applies a rule to the draft and undoes it): run `bash scripts/dev/reset.sh` before and after.
 *
 *   node scripts/smoke-a10-t2.mjs [baseUrl]
 *
 * As admin on Modeler > Industrial returns: "What I see" is there (and a blocking sentence selects its node when the
 * flow has one); the sentence "Never send grade D motors to resale" becomes a preview card; Apply to draft saves it
 * ("Saved ... to draft"); Undo restores the draft; History shows both journal notes; Last simulation shows after
 * Run again (or Simulate). Needs the pinned column (T1 + T4 merged): the column is `.mdl-agent`.
 */
import { chromium } from '@playwright/test';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const SENTENCE = 'Never send grade D motors to resale';
const fails = [];
const check = (ok, what) => {
  console.log((ok ? 'ok   ' : 'FAIL ') + what);
  if (!ok) fails.push(what);
};

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
const errors = [];
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
page.on('console', (m) => {
  if (m.type() === 'error' && !/favicon|DevTools/.test(m.text())) errors.push('console: ' + m.text().slice(0, 300));
});
const seen = (re, ms = 20000) => page.getByText(re).first().waitFor({ timeout: ms }).then(() => true, () => false);

await page.goto(base + '/#/signin');
await page.fill('#si-id', 'admin');
await page.fill('#si-pw', 'demo');
await page.click('button[type=submit]');
await page.waitForSelector('#view', { timeout: 15000 });
await page.goto(base + '/#/modeler?template=industrial&org=workspace');
const col = page.locator('.mdl-agent');

check(await seen(/What I see/), 'the column shows "What I see"');
check(await seen(/Last simulation/, 5000), 'the column shows "Last simulation"');
check((await col.getByText(/locked guardrails?, \d+ business rules?, \d+ outcomes?\./).count()) === 1, 'the first sentence counts guardrails, rules and outcomes');

// a blocking check, when the flow has one, is a sentence that selects its node
const blocking = col.locator('.as-row:has(.as-ic) >> text=/blocks submit|no path|not connected/i').first();
if (await blocking.count()) {
  await col.locator('.as-row', { has: blocking }).getByRole('button', { name: 'Select' }).click();
  check((await page.locator('.mdl-node.sel, .mdl-node.selected, .react-flow__node.selected').count()) >= 1, 'a blocking sentence selects its node on the canvas');
} else console.log('info: no blocking check on this flow; the select-by-sentence check is skipped');

// the sentence becomes a preview card
const box = col.locator('textarea');
await box.fill(SENTENCE);
await box.press('Enter');
check(await seen(/Proposed: /, 30000), 'the sentence becomes a card: "Proposed: ..."');
const card = col.locator('.as-card').first();
check((await card.getByText('What changes').count()) === 1, 'the card has "What changes"');
check((await card.getByText(/Read by (the rules|a language model)/).count()) === 1, 'the card says how it was read');
check((await card.getByText(/Not published\. A different person approves it after you submit\./).count()) === 1, 'the card says what Apply does not do');
check((await card.getByRole('button', { name: 'Apply to draft' }).count()) === 1, 'Apply to draft is offered to the person');
check((await col.getByRole('button', { name: /approve|publish/i }).count()) === 0, 'the assistant offers no Approve or Publish');

await card.getByRole('button', { name: 'Apply to draft' }).click();
check(await seen(/Saved .* to (draft v\d+|the draft)/, 20000), 'Apply to draft says "Saved ... to draft"');
const undo = col.getByRole('button', { name: 'Undo' }).first();
check((await undo.count()) === 1, 'Undo is offered while the draft is unchanged');
await undo.click();
check(await seen(/Undone\. The draft is as it was before\./, 20000), 'Undo restores the draft');

// History shows both notes
await page.getByRole('tab', { name: 'History' }).or(page.getByLabel('History')).first().click();
check(await seen(new RegExp('Proposed by the assistant: ' + SENTENCE), 10000), 'History shows "Proposed by the assistant: ..."');
check(await seen(/Undid the assistant's change/, 10000), 'History shows "Undid the assistant\'s change: ..."');

// Last simulation after Run again
const again = col.getByRole('button', { name: /Run again|Simulate/ }).first();
await again.click();
check(await seen(/Draft v\d+ on \d+ open (decisions|lots), (just now|\d+ min ago)|The flow on \d+ open (decisions|lots)/, 30000), 'Last simulation shows the run and its age');

check(errors.length === 0, 'no page errors ' + JSON.stringify(errors.slice(0, 3)));
await browser.close();
if (fails.length) {
  console.log(`\n${fails.length} check(s) failed`);
  process.exit(1);
}
console.log('\nsmoke-a10-t2: all checks passed');
