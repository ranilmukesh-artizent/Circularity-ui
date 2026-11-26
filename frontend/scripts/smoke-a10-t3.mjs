/**
 * Plan 10, T3 (Set up mode and the Compose launcher). WRITES a draft composition: reset before and after
 * (`bash scripts/dev/reset.sh`). Needs the dock (T1) and the Set up tab (T4) merged.
 *
 *   node frontend/scripts/smoke-a10-t3.mjs http://localhost:5173
 *
 * As `admin`: Modeler (tool_fleet, Customer A) > Set up tab > the launcher "Describe the business in Ask Circularity" opens the
 * assistant in Set up > the first sample prompt > the reading and the match lines > answer the one question > "Drafted N changes"
 * as plain sentences (no JSON) > "Open in Set up" shows composition N on the Describe step. Also: the old "Describe your business"
 * button and dialog are gone.
 */
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { describeInAssistant, openInSetup } from './a10-setup.mjs';

const base = process.argv[2] || `http://localhost:${process.env.WEB_PORT || 5173}`;
const out = process.env.SMOKE_OUT || path.join(tmpdir(), 'smoke-a10-t3');
const UI = 120000;
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const p = await ctx.newPage();
p.setDefaultTimeout(UI);
const errors = [];
p.on('pageerror', (e) => errors.push(e.message));
const fail = async (msg) => {
  await p.screenshot({ path: path.join(out, 'fail.png'), fullPage: true }).catch(() => {});
  console.error('FAIL', msg);
  await browser.close();
  process.exit(1);
};
const check = async (ok, msg) => {
  if (!ok) await fail(msg);
};

try {
  await p.goto(base + '/#/signin');
  await p.fill('#si-id', 'admin');
  await p.fill('#si-pw', 'demo');
  await p.click('button[type=submit]');
  await p.waitForURL((u) => !/signin/.test(u.hash), { timeout: UI });
  await p.goto(`${base}/#/modeler?template=tool_fleet&org=${encodeURIComponent('Customer A')}`);
  await p.locator('#modeler').waitFor();

  await check((await p.getByRole('button', { name: 'Describe your business' }).count()) === 0, 'the "Describe your business" button is still on the Modeler');
  await p.getByRole('tab', { name: 'Set up', exact: true }).or(p.getByRole('button', { name: 'Compose', exact: true })).first().click();
  await p.locator('section[aria-label="Compose"]').waitFor();
  await check((await p.locator('section[aria-label="Compose"] textarea').count()) === 0, 'the Describe step still has its own text box');

  const id = await describeInAssistant(p, { timeout: UI });
  const turn = p.locator('.st-turn').last();
  const t0 = await turn.innerText();
  await check(/Read \d+ words?/.test(t0), 'no reading line: ' + t0.slice(0, 200));
  await check(/(Matched|Nearest) pack: tool_fleet/.test(t0), 'no pack line');
  const skip = turn.getByRole('button', { name: 'Skip', exact: true });
  await skip.waitFor();
  await skip.locator('xpath=..').locator('button').first().click();
  await turn.getByRole('heading', { name: /Drafted (\d+ changes?|no changes)/ }).waitFor();
  const t1 = await turn.innerText();
  await check(!/[{}]/.test(t1), 'JSON braces in the drafted changes: ' + t1.slice(0, 300));
  await check(!/\bop: |"field"/.test(t1), 'raw operation text in the drafted changes');
  await p.screenshot({ path: path.join(out, 'set-up-drafted.png') });

  await openInSetup(p, UI);
  const state = await p.locator('section[aria-label="Compose"] .cmp-state').innerText();
  await check(new RegExp(`composition ${id} is`).test(state), `Open in Set up shows another composition: ${state}`);
  await check(/Describe: /.test(state), 'not on the Describe step: ' + state);
  await check((await p.getByRole('heading', { name: /What the agent read/ }).count()) > 0, 'the Describe step shows no review');
  await check(errors.length === 0, 'page errors: ' + errors.join(' | ').slice(0, 300));
  console.log(`smoke-a10-t3: composition ${id}: ${(t1.match(/Drafted [^\n]*/) || [''])[0]}`);
} catch (e) {
  await fail(String(e?.message || e).split('\n')[0]);
}
await browser.close();
