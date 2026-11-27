/**
 * The replay a person runs before Compose's Publish step shows figures (owner decision, 28 Nov 2026: the step shows replay
 * figures only from a real replay run of the draft; "No replay report yet" otherwise). Helper for smoke-p9-9, p9-10 and p9-11.
 *
 *   await replayTheDraft(p, { modeler: MODELER, csv: path to fixtures/replay/<pack>.csv, open, sim: SIM_URL, timeout })
 *
 * In the Modeler of the pack and org (planner.a): gives the org its own flow when it reads the workspace's, makes a draft when
 * the flow is published (Add rule: a rule without a path compiles to nothing, so the draft decides as the published flow does),
 * opens the Replay step of the lifecycle bar, imports the history and replays the draft until its report shows. The publish
 * step reads the report of the run on the draft as it is now (`rollout_repo.done_replay`: same draft version and content).
 *
 * The packs' history files run to late November 2026, after the demo's clock (7 Oct 2026), and the import holds a decision
 * dated after now ("No valid decision date."): the simulated clock is first advanced past the file's last decision (action:
 * source-sim's /_sim/clock/advance, as smoke-p9-6 and p9-12 do). Call it as a smoke's last step: the clock stays advanced.
 * `open(p, url, ready)` is the smoke's own: goto, reload, wait for `ready`.
 */
import { readFileSync } from 'node:fs';

/** Advance the simulated clock past the last decided_at of the CSV; returns the days advanced (0: the clock is past it). */
async function clockPast(csv, sim) {
  const [head, ...rows] = readFileSync(csv, 'utf8').split(/\r?\n/).filter((l) => l && !l.startsWith('#'));
  const col = head.split(',').indexOf('decided_at');
  const last = Math.max(...rows.map((r) => Date.parse(r.split(',')[col])).filter((t) => !Number.isNaN(t)));
  const now = Date.parse((await (await fetch(sim + '/_sim/clock')).json()).now);
  if (last < now) return 0;
  const days = Math.ceil((last - now) / 86400000) + 1;
  const r = await fetch(sim + '/_sim/clock/advance', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ days }) });
  if (!r.ok) throw new Error(`source-sim refused to advance the clock: ${r.status}`);
  return days;
}

async function openReplay(p, modeler, open, timeout) {
  await open(p, modeler, '.mdl-life');
  const replay = p.locator('.mdl-life').getByRole('button', { name: 'Replay', exact: true });
  await replay.waitFor({ timeout });
  await replay.click();
  const panel = p.locator('.mdl-replay');
  await panel.waitFor({ timeout });
  return panel;
}

export async function replayTheDraft(p, { modeler, csv, open, sim, timeout = 180000 }) {
  const days = await clockPast(csv, sim);
  await open(p, modeler, '.mdl-life');
  const status = p.locator('.mdl-life [data-status]').first();
  const fork = p.getByRole('button', { name: /^Give .* its own flow$/ });
  if (await fork.waitFor({ timeout: 8000 }).then(() => true, () => false)) {
    await fork.click();
    await fork.waitFor({ state: 'detached', timeout });
  }
  if ((await status.getAttribute('data-status')) === 'pub') {
    await p.getByRole('button', { name: 'Add rule', exact: true }).click();
    // the 2 s autosave writes the draft; the bar then reads "Draft · v<n>"
    await p.locator('.mdl-life [data-status="draft"]').waitFor({ timeout });
  }
  let panel = await openReplay(p, modeler, open, timeout); // read afresh: the drawer's versions are those of the screen it opened on
  const batches = () => panel.locator('[data-replay-batch]').evaluateAll((xs) => xs.map((x) => x.getAttribute('data-replay-batch')));
  // the batches there are before the import (read action replay.batches: the drawer reads its list a moment after it opens)
  const q = new URLSearchParams(modeler.split('?')[1] || '');
  const listed = await p.evaluate(async ([pack, org]) => {
    const r = await fetch('/api/actions/replay.batches', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + sessionStorage.getItem('circ-api-token') },
      body: JSON.stringify({ pack, org_unit_id: org }),
    });
    return r.json();
  }, [q.get('template'), q.get('org')]);
  if (!listed.ok) throw new Error('replay.batches: ' + JSON.stringify(listed.error || listed).slice(0, 200));
  const had = new Set(listed.output.batches.map((b) => String(b.id)));
  await panel.locator('#mdl-rp-file').setInputFiles(csv);
  let batch = null;
  const end0 = Date.now() + timeout;
  while (!batch) {
    const refused = panel.locator('[data-replay-refusal]');
    if (await refused.count()) throw new Error('the history import was refused: ' + (await refused.first().innerText()));
    batch = (await batches()).find((id) => !had.has(id)) ?? null;
    if (!batch && Date.now() > end0) throw new Error('the imported history shows no new batch');
    if (!batch) await p.waitForTimeout(1500);
  }
  const row = panel.locator(`[data-replay-batch="${batch}"]`);
  const run = row.locator('[data-replay-run]');
  if (!(await run.waitFor({ timeout: 15000 }).then(() => true, () => false))) {
    throw new Error(`batch ${batch} has no row to replay: ${(await row.innerText()).split('\n').slice(0, 3).join(' | ')}`);
  }
  await run.locator('select').selectOption('draft');
  const reports = () => panel.locator('[data-replay-report]').evaluateAll((xs) => xs.map((x) => x.getAttribute('data-replay-report')));
  const before = new Set(await reports()); // an earlier run's report shows when the drawer opens: wait for this run's
  await run.getByRole('button', { name: 'Replay the draft', exact: true }).click();
  const end = Date.now() + 2 * timeout;
  for (let k = 0; ; k++) {
    const refused = panel.locator('[data-replay-refusal]');
    if (await refused.count()) throw new Error('the replay was refused: ' + (await refused.first().innerText()));
    if ((await reports()).some((id) => !before.has(id))) break;
    if (Date.now() > end) throw new Error('the replay of the draft showed no report');
    // the panel follows a run for about 3 minutes; a slower run shows its report when the drawer opens again
    if (k > 10 && !(await panel.locator('[data-replay-waiting]').count())) {
      panel = await openReplay(p, modeler, open, timeout);
      k = 0;
    }
    await p.waitForTimeout(2000);
  }
  const st = (await status.innerText().catch(() => '')).trim();
  return days ? `${st}; clock advanced ${days} days past the history` : st;
}
