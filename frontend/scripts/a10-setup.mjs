/**
 * Plan 10, T3: the Describe step moved into the one assistant (Set up mode). Helpers for the plan-9 smokes and smoke-a10-t3.
 *
 *   await describeInAssistant(p, { title: 'Lease returns to best channel' });   // a sample description, by the start of its title
 *   await describeInAssistant(p, { typed: 'We return motors ...' });            // or typed text
 *   await openInSetup(p);                                                       // "Open in Set up": the Describe step of the composition
 *
 * `openSetupTab(p)` opens the Modeler's Set up tab (the old Compose button).
 *
 * `describeInAssistant` starts from the Compose panel's launcher (or, with `launch: false`, from an assistant already in Set up
 * mode), picks a sample or types, waits for the drafted turn and returns the composition id.
 */
export const SETUP_PLACEHOLDER = 'Describe how your returns work…';
const LAUNCH = 'Describe the business in Ask Circularity';

export async function describeInAssistant(p, { title, typed, timeout = 180000, launch = true } = {}) {
  if (launch) await p.getByRole('button', { name: LAUNCH }).click();
  const box = p.getByPlaceholder(SETUP_PLACEHOLDER);
  await box.waitFor({ timeout });
  const before = await p.locator('.st-turn').count();
  if (typed !== undefined) {
    await box.fill(typed);
    await box.press('Enter');
  } else {
    const start = title ? p.locator(`.st-start[title^="${title}"]`) : p.locator('.st-start');
    await start.first().waitFor({ timeout });
    await start.first().click();
  }
  const turn = p.locator('.st-turn').nth(before);
  await turn.waitFor({ timeout });
  let foot = await turn.locator('.st-foot').innerText({ timeout });
  // a description no pack matches well (e.g. a diversion typed on its own) asks first: draft against the picked pack anyway
  const anyway = turn.locator('.st-foot button', { hasText: /^Draft against .* anyway$/ });
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

/** The Modeler's "Set up" page tab (plan 10, 3.4; it replaced the bar's Compose button): the Compose panel shows. */
export async function openSetupTab(p, timeout = 60000) {
  await p.locator('.mdl-tabs a[data-tab="setup"]').click();
  await p.locator('section[aria-label="Compose"]').waitFor({ timeout });
}

/** Follow "Open in Set up" of the last Set up turn; the Compose panel then shows the composition on its Describe step. */
export async function openInSetup(p, timeout = 180000) {
  await p.locator('.st-turn a', { hasText: 'Open in Set up' }).last().click();
  await p.locator('section[aria-label="Compose"] .cmp-state').waitFor({ timeout });
}
