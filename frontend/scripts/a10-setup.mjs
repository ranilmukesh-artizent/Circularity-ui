/**
 * Plan 10, T3 and the Set up page (28 Nov 2026): helpers for the plan-9 smokes and smoke-a10-t3.
 *
 * Set up is its own page, `#/setup` (`#/setup?compose=12&step=mapping`; `?new=1` starts another). The Modeler's old Set up
 * tab redirects to it. Step 1 before a draft exists is a form: the description goes into `#sup-text`, "Draft my setup" hands
 * it to the assistant's Set up mode, which reads it, asks its one question and drafts. The five steps are the stops of the
 * route line (`.rl li[data-stop=describe|mapping|agents|approve|publish] a`); the step is the `section.sup-step`, its state
 * line is `.sup-state` ("Not done. Setup 12, Tool fleet for Customer A, draft.").
 *
 *   await openSetupTab(p, 60000, { fresh: true });                                   // the page, on the form (org from the Modeler URL if p is there)
 *   await describeInAssistant(p, { title: 'Lease returns to best channel', template: 'used_cars' });  // a sample, by the start of its title
 *   await describeInAssistant(p, { typed: 'We return motors ...' });                 // or typed text
 *   await openInSetup(p);                                                            // "Open in Set up": the composition on its Describe step
 *   const id = await setupId(p);  await openSetupStep(p, 'mapping');                // the composition id; a step by the route line
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

export const SETUP_PLACEHOLDER = 'Describe how your returns work…';

/** The step panel of the Set up page (the old Compose section). */
export const setupPanel = (p) => p.locator('section.sup-step');
/** The step names of the old Compose tabs, as the route line's stop ids. */
export const STEP_IDS = { Describe: 'describe', 'Adapter mapping': 'mapping', 'Connect systems': 'mapping', Agents: 'agents', Approve: 'approve', Publish: 'publish' };

/** The Set up page of `org` (else the org of the Modeler URL `p` is on, else the default). `base` is the app's origin when `p` is not on it yet. `fresh`: the form, not the newest setup. */
export async function openSetupTab(p, timeout = 60000, { fresh = false, compose = null, org = null, base = null, pack = null } = {}) {
  const u = p.url();
  const origin = base ?? (u.startsWith('http') ? new URL(u).origin : '');
  const q = new URLSearchParams();
  const inUrl = new URLSearchParams(u.split('#')[1]?.split('?')[1] ?? '');
  const o = org ?? inUrl.get('org');
  if (o) q.set('org', o);
  const t = pack ?? inUrl.get('template'); // the template the page starts from (the Modeler's `template` when p is on it); else the organisation's default
  if (t) q.set('pack', t);
  if (fresh) q.set('new', '1');
  if (compose) q.set('compose', String(compose));
  const url = `${origin}/#/setup${q.toString() ? '?' + q : ''}`;
  if (origin) await p.goto(url);
  else throw new Error('openSetupTab needs { base } or a page already on the app (url ' + u + ')');
  await p.locator('#setup').waitFor({ timeout });
  await setupPanel(p).waitFor({ timeout });
}

/** The sample description of a pack that starts with `title`, read from the pack file (the page offers only the default pack's samples). */
function packSample(template, title) {
  const file = fileURLToPath(new URL(`../../backend/di/services/modeler/packs/${template}.json`, import.meta.url));
  const found = (JSON.parse(readFileSync(file, 'utf8')).prompts ?? []).find((t) => t.startsWith(title));
  if (!found) throw new Error(`pack ${template} has no sample starting "${title}"`);
  return found;
}

/**
 * From the Set up page on its form (`openSetupTab(p, t, { fresh: true, pack })`): pick a sample or type, press "Draft my setup",
 * wait for the assistant's drafted turn and return the composition id. `template` is the pack of a `title` that the form
 * does not offer.
 */
export async function describeInAssistant(p, { title, typed, template, timeout = 180000 } = {}) {
  const box = p.locator('#sup-text');
  await box.waitFor({ timeout });
  let text = typed;
  if (text === undefined) {
    const sample = title ? p.locator('.sup-sample', { hasText: title }) : p.locator('.sup-sample');
    await p.locator('.sup-sample').first().waitFor({ timeout: 15000 }).catch(() => {});
    if (await sample.count()) {
      await sample.first().click();
      text = await box.inputValue();
    } else if (template && title) {
      text = packSample(template, title);
    } else {
      throw new Error('the form offers no sample' + (title ? ` "${title}"` : '') + ' (pass { template } for another pack, or { typed })');
    }
  }
  await box.fill(text);
  const before = await p.locator('.st-turn').count();
  await p.getByRole('button', { name: 'Draft my setup' }).click();
  const turn = p.locator('.st-turn').nth(before);
  await turn.waitFor({ timeout });
  let foot = await turn.locator('.st-foot').innerText({ timeout });
  // a description no pack matches well (e.g. a diversion typed on its own) asks first: draft against the picked pack anyway
  // the assistant asks which pack to start from when the words read like another one ("Start from <matched>" / "Keep <picked>")
  // or like none ("Draft against <picked> anyway"): take the matched pack, else draft anyway
  const anyway = turn.locator('.st-foot button', { hasText: /^(Start from .*|Draft against .* anyway)$/ });
  if (!/Composition \d+/.test(foot) && (await anyway.count())) {
    const feet = p.locator('.st-turn .st-foot', { hasText: /Composition \d+/ });
    const had = await feet.count();
    await anyway.first().click();
    await p.waitForFunction(([n]) => [...document.querySelectorAll('.st-turn .st-foot')].filter((x) => /Composition \d+/.test(x.textContent || '')).length > n, [had], { timeout });
    foot = await feet.last().innerText({ timeout });
  }
  const id = Number(foot.match(/Composition (\d+)/)?.[1]);
  if (!id) throw new Error('the Set up turn names no composition: ' + foot);
  return id;
}

/** The composition id in the page's state line ("Setup 12, ..."), 0 when none shows. */
export async function setupId(p) {
  return Number((await setupPanel(p).locator('.sup-state').innerText().catch(() => '')).match(/Setup (\d+),/)?.[1]) || 0;
}

/** A step of the open composition by its route-line stop (a name of the old Compose tabs also works). */
export async function openSetupStep(p, step, timeout = 60000) {
  const id = STEP_IDS[step] ?? step;
  await p.locator(`.rl li[data-stop="${id}"] a.rl-stop`).click({ timeout });
}

/** Follow "Open in Set up" of the last Set up turn; the page then shows the composition on its Describe step. */
export async function openInSetup(p, timeout = 180000) {
  await p.locator('.st-turn a', { hasText: 'Open in Set up' }).last().click();
  await setupPanel(p).locator('.sup-state').waitFor({ timeout });
}
